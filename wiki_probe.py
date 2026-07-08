# wiki_probe.py
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


API = "https://zh.wikipedia.org/w/api.php"
REST_SUMMARY = "https://zh.wikipedia.org/api/rest_v1/page/summary/{}"

DEFAULT_UA = "epub2cbz-comicinfo-probe/0.1 (local metadata tool)"


@dataclass
class ProbeConfig:
    out_dir: Path
    limit: int = 5
    sleep: float = 0.7
    user_agent: str = DEFAULT_UA
    save_wikitext: bool = True


def safe_name(text: str, max_len: int = 80) -> str:
    text = text.strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    return text[:max_len] or "unknown"


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    print(f"saved: {path}")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"saved: {path}")


class WikiProbeClient:
    def __init__(self, config: ProbeConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # maxlag 是 Wikimedia 推荐的礼貌参数之一；服务器繁忙时可能返回 maxlag error。
        if params is not None:
            params = dict(params)
            params.setdefault("maxlag", 5)

        last_error: Exception | None = None

        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=20)

                # maxlag / 429 / 临时错误时退避一下
                if r.status_code in {429, 500, 502, 503, 504}:
                    time.sleep(2 + attempt * 2)
                    continue

                r.raise_for_status()
                data = r.json()

                if isinstance(data, dict) and data.get("error", {}).get("code") == "maxlag":
                    time.sleep(2 + attempt * 2)
                    continue

                return data

            except Exception as exc:
                last_error = exc
                time.sleep(1 + attempt)

        raise RuntimeError(f"request failed: {url}") from last_error

    def search(self, query: str) -> dict[str, Any]:
        return self.get_json(
            API,
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": self.config.limit,
                "utf8": 1,
            },
        )

    def summary(self, title: str) -> dict[str, Any]:
        # REST summary 不吃 maxlag 参数，所以这里直接 URL。
        return self.get_json(REST_SUMMARY.format(quote(title)))

    def page_full(self, title: str) -> dict[str, Any]:
        return self.get_json(
            API,
            params={
                "action": "query",
                "format": "json",
                "prop": "extracts|categories|pageprops|info|langlinks",
                "titles": title,
                "exintro": 1,
                "explaintext": 1,
                "cllimit": 100,
                "lllimit": 100,
                "lllang": "ja|en",
                "inprop": "url",
                "redirects": 1,
                "utf8": 1,
            },
        )

    def page_parse(self, title: str) -> dict[str, Any]:
        # 这个主要看 tocdata / templates / links / categories 的 shape。
        return self.get_json(
            API,
            params={
                "action": "parse",
                "format": "json",
                "page": title,
                "prop": "tocdata|templates|categories|links|properties|displaytitle",
                "redirects": 1,
                "utf8": 1,
            },
        )

    def page_wikitext(self, title: str) -> dict[str, Any]:
        # 用来观察繁中页面 infobox / 漫画模板到底长什么样。
        # 后续如果要抽作者、出版社、册数，wikitext 比 summary 更有价值。
        return self.get_json(
            API,
            params={
                "action": "query",
                "format": "json",
                "prop": "revisions|info",
                "titles": title,
                "rvprop": "content",
                "rvslots": "main",
                "inprop": "url",
                "redirects": 1,
                "utf8": 1,
            },
        )


def get_pages(query_result: dict[str, Any]) -> list[dict[str, Any]]:
    return query_result.get("query", {}).get("search", []) or []


def get_first_page_title(query_result: dict[str, Any]) -> str | None:
    pages = get_pages(query_result)
    if not pages:
        return None
    return pages[0].get("title")


def extract_page_record(page_full_result: dict[str, Any]) -> dict[str, Any] | None:
    pages = page_full_result.get("query", {}).get("pages", {})
    if not isinstance(pages, dict) or not pages:
        return None

    # MediaWiki pages 是 pageid -> page object。
    for _, page in pages.items():
        if isinstance(page, dict) and "missing" not in page:
            return page

    return None


def extract_wikitext(wikitext_result: dict[str, Any]) -> str | None:
    page = extract_page_record(wikitext_result)
    if not page:
        return None

    revisions = page.get("revisions") or []
    if not revisions:
        return None

    rev0 = revisions[0]

    # 新版 slots 格式
    slots = rev0.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main")
        if isinstance(main, dict):
            return main.get("*") or main.get("content")

    # 老格式兜底
    return rev0.get("*")


def build_human_summary(
    *,
    query: str,
    selected_title: str,
    search_json: dict[str, Any],
    summary_json: dict[str, Any],
    page_full_json: dict[str, Any],
    parse_json: dict[str, Any],
) -> str:
    page = extract_page_record(page_full_json) or {}
    categories = [
        c.get("title", "").replace("Category:", "")
        for c in page.get("categories", []) or []
        if isinstance(c, dict)
    ]
    langlinks = page.get("langlinks", []) or []
    links = parse_json.get("parse", {}).get("links", []) or []
    templates = parse_json.get("parse", {}).get("templates", []) or []

    lines = []
    lines.append(f"# Wiki Probe: {query}")
    lines.append("")
    lines.append(f"- selected_title: {selected_title}")
    lines.append(f"- pageid: {page.get('pageid')}")
    lines.append(f"- fullurl: {page.get('fullurl')}")
    lines.append(f"- wikibase_item: {(page.get('pageprops') or {}).get('wikibase_item')}")
    lines.append(f"- summary_title: {summary_json.get('title')}")
    lines.append(f"- description: {summary_json.get('description')}")
    lines.append("")
    lines.append("## Extract")
    lines.append(summary_json.get("extract") or page.get("extract") or "")
    lines.append("")
    lines.append("## Search candidates")
    for i, item in enumerate(get_pages(search_json), start=1):
        lines.append(f"{i}. {item.get('title')} / pageid={item.get('pageid')}")
    lines.append("")
    lines.append("## Categories")
    for c in categories[:80]:
        lines.append(f"- {c}")
    lines.append("")
    lines.append("## Langlinks")
    for ll in langlinks[:20]:
        lines.append(f"- {ll.get('lang')}: {ll.get('*')}")
    lines.append("")
    lines.append("## Templates")
    for t in templates[:80]:
        lines.append(f"- {t.get('*')}")
    lines.append("")
    lines.append("## Links sample")
    for link in links[:80]:
        lines.append(f"- {link.get('*')}")
    lines.append("")

    return "\n".join(lines)


def probe_one(client: WikiProbeClient, query: str, explicit_title: str | None = None) -> None:
    base = client.config.out_dir / safe_name(query)
    base.mkdir(parents=True, exist_ok=True)

    search_json = client.search(query)
    dump_json(base / "01_search.json", search_json)

    selected_title = explicit_title or get_first_page_title(search_json)
    if not selected_title:
        print(f"[WARN] no search result for: {query}")
        return

    print(f"selected title: {selected_title}")

    time.sleep(client.config.sleep)
    summary_json = client.summary(selected_title)
    dump_json(base / "02_summary.json", summary_json)

    time.sleep(client.config.sleep)
    page_full_json = client.page_full(selected_title)
    dump_json(base / "03_page_full.json", page_full_json)

    time.sleep(client.config.sleep)
    parse_json = client.page_parse(selected_title)
    dump_json(base / "04_parse.json", parse_json)

    if client.config.save_wikitext:
        time.sleep(client.config.sleep)
        wikitext_json = client.page_wikitext(selected_title)
        dump_json(base / "05_wikitext_raw.json", wikitext_json)

        wikitext = extract_wikitext(wikitext_json)
        if wikitext:
            dump_text(base / "05_wikitext.txt", wikitext)

    human = build_human_summary(
        query=query,
        selected_title=selected_title,
        search_json=search_json,
        summary_json=summary_json,
        page_full_json=page_full_json,
        parse_json=parse_json,
    )
    dump_text(base / "00_human_summary.md", human)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe zh.wikipedia metadata API responses.")
    parser.add_argument(
        "queries",
        nargs="*",
        help="Search queries. Example: 鋼之鍊金術師 漫畫",
    )
    parser.add_argument(
        "--title",
        help="Skip automatic first search candidate and fetch this exact wiki page title.",
    )
    parser.add_argument(
        "--query-file",
        help="UTF-8 text file, one query per line.",
    )
    parser.add_argument(
        "--out",
        default="probe_output",
        help="Output directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Search result limit.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.7,
        help="Sleep seconds between requests.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_UA,
        help="HTTP User-Agent.",
    )
    parser.add_argument(
        "--no-wikitext",
        action="store_true",
        help="Do not fetch revision wikitext.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    queries = list(args.queries)

    if args.query_file:
        path = Path(args.query_file)
        queries.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if not queries:
        queries = ["聖鬥士星矢 THE LOST CANVAS 冥王神話 漫畫"]

    config = ProbeConfig(
        out_dir=Path(args.out),
        limit=args.limit,
        sleep=args.sleep,
        user_agent=args.user_agent,
        save_wikitext=not args.no_wikitext,
    )
    client = WikiProbeClient(config)

    for idx, query in enumerate(queries, start=1):
        if idx > 1:
            time.sleep(config.sleep)

        print(f"\n=== [{idx}/{len(queries)}] {query} ===")
        probe_one(client, query, explicit_title=args.title)


if __name__ == "__main__":
    main()
