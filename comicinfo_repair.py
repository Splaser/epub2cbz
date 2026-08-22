# comicinfo_repair.py
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
from typing import Any, Optional

from utils.metadata_utils import clean_raw_name, extract_special_label

from metadata.comicinfo_archive import (
    find_comicinfo_entry_name,
    write_comicinfo_to_cbz,
)
from metadata.epub_comicinfo import (
    infer_volume_number as infer_shared_volume_number,
    load_exact_wiki_series_for_dir,
    load_wiki_series_for_url,
)
from metadata.wiki_models import WikiSeriesMetadata
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
        description="Inject ComicInfo.xml into CBZ files."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--cbz", help="Single CBZ file to process.")
    source.add_argument("--dir", help="Directory containing CBZ files. Defaults to the executable/current script directory.")

    metadata = parser.add_mutually_exclusive_group()
    metadata.add_argument("--probe-dir", help="Directory containing 02_summary.json/03_page_full.json/05_wikitext.txt.")
    metadata.add_argument("--wikitext", help="Local 05_wikitext.txt file.")
    metadata.add_argument("--wiki-url", help="Explicit zh.wikipedia page URL to use as metadata source.")

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
    parser.add_argument("--write", action="store_true", help="Actually write ComicInfo.xml. Default for explicit --cbz/--dir is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write. Useful for no-argument executable mode.")
    parser.add_argument("--backup", action="store_true", help="Before --write, copy file to .bak if it does not exist.")
    parser.add_argument("--backup-suffix", default=".bak")
    parser.add_argument("--print-xml", action="store_true", help="Print generated XML for each file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = get_base_dir()
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    os.chdir(base_dir)
    target_dir = resolve_target_dir(args, base_dir)
    cbz_paths = resolve_cbz_paths(args)
    effective_write = resolve_effective_write(args)

    if not cbz_paths:
        print(f"❌ No cbz files found in: {target_dir}")
        return

    wiki = resolve_wiki_metadata(args, target_dir)
    if wiki is None:
        print(f"  - skip ComicInfo repair: no exact Wiki metadata for {target_dir.name}")
        return

    for cbz_path in cbz_paths:
        process_cbz(cbz_path, args, wiki, effective_write)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_target_dir(args: argparse.Namespace, base_dir: Path) -> Path:
    if args.cbz:
        return Path(args.cbz).resolve().parent
    if args.dir:
        return Path(args.dir).resolve()
    return base_dir


def resolve_effective_write(args: argparse.Namespace) -> bool:
    default_exe_mode = args.cbz is None and args.dir is None
    if args.dry_run:
        return False
    return args.write or default_exe_mode


def resolve_wiki_metadata(args: argparse.Namespace, target_dir: Path) -> Optional[WikiSeriesMetadata]:
    if args.wiki_url:
        return load_wiki_series_for_url(target_dir, args.wiki_url)

    if args.probe_dir or args.wikitext:
        wikitext_path, probe_defaults = resolve_probe_inputs(args)
        return build_series_metadata_from_file(
            wikitext_path,
            page_title=args.page_title or probe_defaults.get("page_title") or wikitext_path.parent.name,
            pageid=args.pageid or probe_defaults.get("pageid") or 0,
            page_url=args.page_url or probe_defaults.get("page_url"),
            wikibase_item=args.wikibase_item or probe_defaults.get("wikibase_item"),
            summary=args.summary or probe_defaults.get("summary"),
            query=args.query or target_dir.name,
            series_sort=args.series_sort,
        )

    return load_exact_wiki_series_for_dir(target_dir)


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
        return [Path(args.cbz).resolve()]

    root = Path(args.dir).resolve() if args.dir else get_base_dir()
    return sorted(path for path in root.glob("*.cbz") if path.is_file())


def process_cbz(
    cbz_path: Path,
    args: argparse.Namespace,
    wiki: WikiSeriesMetadata,
    effective_write: bool,
) -> None:
    if not cbz_path.exists():
        raise FileNotFoundError(cbz_path)

    series_title = resolve_series_title(cbz_path, args)
    cleaned_title = clean_raw_name(cbz_path.stem)
    if series_title:
        series_prefix = f"{series_title} - "
        if cleaned_title.casefold().startswith(series_prefix.casefold()):
            cleaned_title = cleaned_title[len(series_prefix):].strip()

    is_special = extract_special_label(cleaned_title) is not None
    volume_number = infer_shared_volume_number(cbz_path.name)
    if volume_number is None and not is_special:
        print(f"  - skip ComicInfo: Cannot infer volume number from filename: {cbz_path.name}")
        return

    page_count = count_cbz_pages(cbz_path)
    existing_entry = find_existing_comicinfo(cbz_path)
    comicinfo = wiki_series_to_comicinfo(
        wiki,
        volume_number or 0,
        title=cleaned_title if is_special else None,
        series_title=series_title,
        series_sort=args.series_sort,
        write_number=args.write_number and volume_number is not None,
        write_volume=args.write_volume,
        language_iso=args.language_iso,
        manga=args.manga,
        age_rating=args.age_rating,
        page_count=page_count,
    )
    if is_special:
        comicinfo.format = "Special"

    print(
        f"{'[WRITE]' if effective_write else '[DRY-RUN]'} {cbz_path} "
        f"volume={volume_number if volume_number is not None else '-'} "
        f"pages={page_count} "
        f"existing={existing_entry or '-'}"
    )
    print(
        f"  Series={comicinfo.series} | Title={comicinfo.title} | "
        f"Count={comicinfo.count} | Year={comicinfo.year} | "
        f"Publisher={comicinfo.publisher}"
    )

    if args.print_xml:
        print(comicinfo.to_xml_string())

    if not effective_write:
        return

    if args.backup:
        create_backup(cbz_path, args.backup_suffix)

    write_comicinfo_to_cbz(str(cbz_path), comicinfo)


def resolve_series_title(cbz_path: Path, args: argparse.Namespace) -> Optional[str]:
    if args.series_title:
        return args.series_title

    use_dir_name = args.series_title_from_dir
    if use_dir_name is None:
        use_dir_name = args.cbz is None

    if use_dir_name:
        return cbz_path.parent.name
    return None


def infer_volume_number(filename: str) -> int:
    volume_number = infer_shared_volume_number(filename)
    if volume_number is not None:
        return volume_number

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
