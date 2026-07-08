# metadata/wiki_client.py
from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from metadata.wiki_models import WikiPageData, WikiPageSummary, WikiSearchItem
except ModuleNotFoundError:
    from wiki_models import WikiPageData, WikiPageSummary, WikiSearchItem


DEFAULT_API_URL = "https://zh.wikipedia.org/w/api.php"
DEFAULT_REST_SUMMARY_URL = "https://zh.wikipedia.org/api/rest_v1/page/summary/{}"
DEFAULT_USER_AGENT = "epub2cbz-comicinfo/0.1 (local metadata tool)"


class WikiClient:
    """
    Thin MediaWiki API client.

    This module intentionally returns Wiki DTOs/raw API-shaped metadata only.
    ComicInfo mapping and CBZ writing belong in higher layers.
    """

    def __init__(
        self,
        *,
        api_url: str = DEFAULT_API_URL,
        rest_summary_url: str = DEFAULT_REST_SUMMARY_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 20.0,
        max_retries: int = 3,
        sleep: float = 0.7,
    ) -> None:
        self.api_url = api_url
        self.rest_summary_url = rest_summary_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep

    def search(self, query: str, *, limit: int = 5) -> list[WikiSearchItem]:
        data = self._get_json(
            self.api_url,
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "utf8": 1,
            },
        )
        return [
            WikiSearchItem(
                title=str(item.get("title") or ""),
                pageid=int(item.get("pageid") or 0),
                snippet=item.get("snippet"),
                size=item.get("size"),
                wordcount=item.get("wordcount"),
            )
            for item in data.get("query", {}).get("search", []) or []
            if item.get("title") and item.get("pageid")
        ]

    def summary(self, title: str) -> WikiPageSummary:
        data = self._get_json(
            self.rest_summary_url.format(quote(title)),
            use_maxlag=False,
        )
        return _summary_from_json(data)

    def page_data(self, title: str) -> WikiPageData:
        page_json = self._query_page(title)
        page = extract_page_record(page_json)
        if page is None:
            raise ValueError(f"Wiki page not found: {title}")

        wikitext = extract_wikitext_from_page(page)
        if not wikitext:
            raise ValueError(f"Wiki page has no wikitext: {title}")

        page_title = str(page.get("title") or title)
        converted_title = extract_converted_title(page_json, title)
        summary = None
        try:
            if self.sleep:
                time.sleep(self.sleep)
            summary = self.summary(page_title)
        except Exception:
            summary = None

        pageprops = page.get("pageprops") or {}
        categories = [
            str(item.get("title", "")).replace("Category:", "", 1)
            for item in page.get("categories", []) or []
            if isinstance(item, dict) and item.get("title")
        ]

        return WikiPageData(
            requested_title=title,
            title=page_title,
            pageid=int(page.get("pageid") or 0),
            wikitext=wikitext,
            converted_title=converted_title,
            extract=(summary.extract if summary else None) or page.get("extract"),
            description=summary.description if summary else None,
            page_url=page.get("fullurl") or (summary.page_url if summary else None),
            thumbnail_url=summary.thumbnail_url if summary else None,
            wikibase_item=pageprops.get("wikibase_item") or (summary.wikibase_item if summary else None),
            defaultsort=pageprops.get("defaultsort"),
            categories=categories,
        )

    def page_data_for_query(self, query: str, *, limit: int = 5) -> WikiPageData:
        results = self.search(query, limit=limit)
        if not results:
            raise ValueError(f"No Wiki search results for: {query}")
        if self.sleep:
            time.sleep(self.sleep)
        return self.page_data(results[0].title)

    def page_data_for_url(self, url: str) -> WikiPageData:
        return self.page_data(wiki_title_from_url(url))

    def _query_page(self, title: str) -> dict[str, Any]:
        return self._get_json(
            self.api_url,
            params={
                "action": "query",
                "format": "json",
                "prop": "extracts|categories|pageprops|info|revisions",
                "titles": title,
                "exintro": 1,
                "explaintext": 1,
                "cllimit": "max",
                "rvprop": "content",
                "rvslots": "main",
                "inprop": "url",
                "redirects": 1,
                "converttitles": 1,
                "utf8": 1,
            },
        )

    def _get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        use_maxlag: bool = True,
    ) -> dict[str, Any]:
        if params is not None:
            params = dict(params)
            if use_maxlag:
                params.setdefault("maxlag", 5)
            url = f"{url}?{urlencode(params)}"

        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries):
            try:
                request = Request(url, headers={"User-Agent": self.user_agent})
                with urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))

                if isinstance(data, dict) and data.get("error", {}).get("code") == "maxlag":
                    time.sleep(2 + attempt * 2)
                    continue

                return data
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    break
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc

            time.sleep(1 + attempt)

        raise RuntimeError(f"Wiki request failed: {url}") from last_error


def extract_page_record(query_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    pages = query_result.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None

    for page in pages.values():
        if isinstance(page, dict) and "missing" not in page:
            return page

    return None


def extract_converted_title(query_result: dict[str, Any], source_title: str) -> Optional[str]:
    converted = query_result.get("query", {}).get("converted", []) or []
    for item in converted:
        if not isinstance(item, dict):
            continue
        if item.get("from") == source_title and item.get("to"):
            return str(item["to"])
    return None


def extract_wikitext_from_page(page: dict[str, Any]) -> Optional[str]:
    revisions = page.get("revisions") or []
    if not revisions:
        return None

    revision = revisions[0]
    slots = revision.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main")
        if isinstance(main, dict):
            return main.get("*") or main.get("content")

    return revision.get("*")


def wiki_title_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Not a Wiki URL: {url}")

    query = parse_qs(parsed.query)
    if query.get("title"):
        return unquote(query["title"][0]).replace("_", " ").strip()

    marker = "/wiki/"
    if marker in parsed.path:
        title = parsed.path.split(marker, 1)[1]
        title = title.split("#", 1)[0]
        if title:
            return unquote(title).replace("_", " ").strip()

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts and path_parts[0].casefold() in {
        "zh",
        "zh-cn",
        "zh-hans",
        "zh-hant",
        "zh-hk",
        "zh-mo",
        "zh-my",
        "zh-sg",
        "zh-tw",
    }:
        title = "/".join(path_parts[1:]).split("#", 1)[0]
        if title:
            return unquote(title).replace("_", " ").strip()

    raise ValueError(f"Cannot infer Wiki title from URL: {url}")


def _summary_from_json(data: dict[str, Any]) -> WikiPageSummary:
    content_urls = data.get("content_urls") or {}
    desktop = content_urls.get("desktop") or {}
    thumbnail = data.get("thumbnail") or {}
    return WikiPageSummary(
        title=str(data.get("title") or ""),
        extract=data.get("extract"),
        description=data.get("description"),
        page_url=desktop.get("page"),
        thumbnail_url=thumbnail.get("source"),
        wikibase_item=data.get("wikibase_item"),
    )
