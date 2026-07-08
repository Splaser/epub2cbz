# comicinfo_repair.py
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import zipfile
from typing import Any, Optional

from metadata.comicinfo import ComicInfo
from metadata.comicinfo_archive import (
    find_comicinfo_entry_name,
    write_comicinfo_to_cbz,
)
from metadata.wiki_scraper import build_series_metadata_from_file
from metadata.wiki_to_comicinfo import wiki_series_to_comicinfo


IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".avif",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject ComicInfo.xml into CBZ files from local Wiki probe output."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cbz", help="Single CBZ file to process.")
    source.add_argument("--dir", help="Directory containing CBZ files.")

    metadata = parser.add_mutually_exclusive_group()
    metadata.add_argument("--probe-dir", help="Directory containing 02_summary.json/03_page_full.json/05_wikitext.txt.")
    metadata.add_argument("--wikitext", help="Local 05_wikitext.txt file.")

    parser.add_argument("--query", help="Optional query hint for selecting a Manga block.")
    parser.add_argument("--page-title", help="Wiki page title override.")
    parser.add_argument("--pageid", type=int, default=0, help="Wiki pageid override.")
    parser.add_argument("--page-url", help="Wiki page URL override.")
    parser.add_argument("--wikibase-item", help="Wikidata Q-id override.")
    parser.add_argument("--summary", help="Summary override.")
    parser.add_argument("--series-title", help="Override ComicInfo Series/LocalizedSeries.")
    parser.add_argument(
        "--series-title-from-dir",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use parent directory name as ComicInfo Series. Defaults on for --dir.",
    )
    parser.add_argument("--series-sort", help="Override ComicInfo SeriesSort.")
    parser.add_argument(
        "--write-volume",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write ComicInfo Volume. Off by default; Kavita may split series by Volume.",
    )
    parser.add_argument(
        "--write-number",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write ComicInfo Number. Defaults on.",
    )
    parser.add_argument("--language-iso", default="zh-Hant-TW")
    parser.add_argument("--manga", default="Yes")
    parser.add_argument("--age-rating", default="Teen")
    parser.add_argument("--write", action="store_true", help="Actually write ComicInfo.xml. Default is dry-run.")
    parser.add_argument("--backup", action="store_true", help="Before --write, copy file to .bak if it does not exist.")
    parser.add_argument("--backup-suffix", default=".bak")
    parser.add_argument("--print-xml", action="store_true", help="Print generated XML for each file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wikitext_path, probe_defaults = resolve_probe_inputs(args)
    cbz_paths = resolve_cbz_paths(args)

    if not cbz_paths:
        raise FileNotFoundError("No CBZ files found")

    for cbz_path in cbz_paths:
        process_cbz(cbz_path, wikitext_path, probe_defaults, args)


def resolve_probe_inputs(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    if args.probe_dir:
        probe_dir = Path(args.probe_dir)
        wikitext_path = probe_dir / "05_wikitext.txt"
        defaults = read_probe_defaults(probe_dir)
    elif args.wikitext:
        wikitext_path = Path(args.wikitext)
        defaults = {}
    else:
        wikitext_path = find_default_wikitext()
        defaults = read_probe_defaults(wikitext_path.parent)

    if not wikitext_path.exists():
        raise FileNotFoundError(wikitext_path)

    return wikitext_path, defaults


def read_probe_defaults(probe_dir: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {}

    summary_json = read_json_if_exists(probe_dir / "02_summary.json")
    if summary_json:
        defaults["page_title"] = summary_json.get("title")
        defaults["summary"] = summary_json.get("extract")
        defaults["page_url"] = (
            summary_json.get("content_urls", {})
            .get("desktop", {})
            .get("page")
        )
        defaults["wikibase_item"] = summary_json.get("wikibase_item")

    page_full_json = read_json_if_exists(probe_dir / "03_page_full.json")
    page = extract_page_record(page_full_json) if page_full_json else None
    if page:
        defaults["page_title"] = page.get("title") or defaults.get("page_title")
        defaults["pageid"] = page.get("pageid") or defaults.get("pageid")
        defaults["page_url"] = page.get("fullurl") or defaults.get("page_url")
        defaults["summary"] = page.get("extract") or defaults.get("summary")
        defaults["wikibase_item"] = (
            (page.get("pageprops") or {}).get("wikibase_item")
            or defaults.get("wikibase_item")
        )

    return defaults


def read_json_if_exists(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def extract_page_record(page_full_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    pages = page_full_result.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None

    for page in pages.values():
        if isinstance(page, dict) and "missing" not in page:
            return page

    return None


def find_default_wikitext() -> Path:
    matches = sorted((Path.cwd() / "probe_output").glob("*/05_wikitext.txt"))
    if not matches:
        raise FileNotFoundError("No probe_output/*/05_wikitext.txt sample found")
    return matches[0]


def resolve_cbz_paths(args: argparse.Namespace) -> list[Path]:
    if args.cbz:
        return [Path(args.cbz)]

    root = Path(args.dir)
    return sorted(path for path in root.glob("*.cbz") if path.is_file())


def process_cbz(
    cbz_path: Path,
    wikitext_path: Path,
    probe_defaults: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    if not cbz_path.exists():
        raise FileNotFoundError(cbz_path)

    volume_number = infer_volume_number(cbz_path.name)
    page_count = count_cbz_pages(cbz_path)
    existing_entry = find_existing_comicinfo(cbz_path)
    wiki = build_series_metadata_from_file(
        wikitext_path,
        page_title=args.page_title or probe_defaults.get("page_title") or wikitext_path.parent.name,
        pageid=args.pageid or probe_defaults.get("pageid") or 0,
        page_url=args.page_url or probe_defaults.get("page_url"),
        wikibase_item=args.wikibase_item or probe_defaults.get("wikibase_item"),
        summary=args.summary or probe_defaults.get("summary"),
        query=args.query,
    )
    comicinfo = wiki_series_to_comicinfo(
        wiki,
        volume_number,
        series_title=resolve_series_title(cbz_path, args),
        series_sort=args.series_sort,
        write_number=args.write_number,
        write_volume=args.write_volume,
        language_iso=args.language_iso,
        manga=args.manga,
        age_rating=args.age_rating,
        page_count=page_count,
    )

    print(
        f"{'[WRITE]' if args.write else '[DRY-RUN]'} {cbz_path} "
        f"volume={volume_number} pages={page_count} "
        f"existing={existing_entry or '-'}"
    )
    print(
        f"  Series={comicinfo.series} | Title={comicinfo.title} | "
        f"Count={comicinfo.count} | Publisher={comicinfo.publisher}"
    )

    if args.print_xml:
        print(comicinfo.to_xml_string())

    if not args.write:
        return

    if args.backup:
        create_backup(cbz_path, args.backup_suffix)

    write_comicinfo_to_cbz(str(cbz_path), comicinfo)


def resolve_series_title(cbz_path: Path, args: argparse.Namespace) -> Optional[str]:
    if args.series_title:
        return args.series_title

    use_dir_name = args.series_title_from_dir
    if use_dir_name is None:
        use_dir_name = args.dir is not None

    if use_dir_name:
        return cbz_path.parent.name
    return None


def infer_volume_number(filename: str) -> int:
    normalized = filename.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    for pattern in (
        r"第\s*0*(\d+)\s*[卷冊册]",
        r"vol(?:ume)?\.?\s*0*(\d+)",
        r"0*(\d+)",
    ):
        match = re.search(pattern, normalized, flags=re.I)
        if match:
            return int(match.group(1))

    raise ValueError(f"Cannot infer volume number from filename: {filename}")


def count_cbz_pages(cbz_path: Path) -> int:
    with zipfile.ZipFile(cbz_path, "r") as archive:
        return sum(
            1
            for item in archive.infolist()
            if not item.is_dir() and Path(item.filename).suffix.lower() in IMAGE_EXTS
        )


def find_existing_comicinfo(cbz_path: Path) -> Optional[str]:
    with zipfile.ZipFile(cbz_path, "r") as archive:
        return find_comicinfo_entry_name(archive.namelist())


def create_backup(cbz_path: Path, suffix: str) -> Path:
    backup_path = Path(str(cbz_path) + suffix)
    if backup_path.exists():
        raise FileExistsError(f"Backup already exists: {backup_path}")

    shutil.copy2(cbz_path, backup_path)
    print(f"  backup={backup_path}")
    return backup_path


if __name__ == "__main__":
    main()
