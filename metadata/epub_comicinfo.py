# metadata/epub_comicinfo.py
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Optional

from .wiki_client import WikiClient
from .wiki_models import WikiMangaInfo, WikiSeriesMetadata
from .wiki_scraper import build_series_metadata_from_page_data
from .wiki_to_comicinfo import wiki_series_to_comicinfo


SERIES_METADATA_CACHE_NAME = "series.meta.json"
SERIES_METADATA_CACHE_VERSION = 1


def load_exact_wiki_series_for_dir(
    series_dir: str | Path,
    *,
    client: Optional[WikiClient] = None,
    use_cache: bool = True,
) -> Optional[WikiSeriesMetadata]:
    """
    Try to load Wiki metadata for a series directory.

    This is intentionally conservative for main.py: only an exact Wiki title match
    enables ComicInfo injection. Any mismatch or network/parser failure returns None
    so EPUB -> CBZ conversion continues unchanged.

    Successful matches are cached once per series directory in series.meta.json.
    """
    path = Path(series_dir)
    series_name = path.name.strip()
    if not series_name:
        return None

    cache_path = path / SERIES_METADATA_CACHE_NAME
    if use_cache:
        cached = load_cached_wiki_series(cache_path, expected_series_name=series_name)
        if cached is not None:
            print(f"  - Wiki ComicInfo cache: {cache_path.name}")
            return cached

    wiki_client = client or WikiClient()

    try:
        page_data = wiki_client.page_data(series_name)
    except Exception as exc:
        print(f"  - skip Wiki ComicInfo: {series_name} lookup failed ({exc})")
        return None

    if not _is_exact_or_converted_title_match(series_name, page_data.title, page_data.converted_title):
        print(
            "  - skip Wiki ComicInfo: "
            f"directory title '{series_name}' != wiki title '{page_data.title}'"
        )
        return None

    try:
        series = build_series_metadata_from_page_data(page_data, query=series_name)
    except Exception as exc:
        print(f"  - skip Wiki ComicInfo: {series_name} metadata parse failed ({exc})")
        return None

    if use_cache:
        save_cached_wiki_series(cache_path, series_name=series_name, wiki_series=series)

    return series


def load_wiki_series_for_url(
    series_dir: str | Path,
    wiki_url: str,
    *,
    client: Optional[WikiClient] = None,
    use_cache: bool = True,
) -> Optional[WikiSeriesMetadata]:
    """
    Load Wiki metadata from an explicit page URL.

    Unlike load_exact_wiki_series_for_dir(), this does not require the Wiki title
    to match the directory name. The directory name still remains the ComicInfo
    Series later, so Kavita grouping follows local folder naming.
    """
    path = Path(series_dir)
    series_name = path.name.strip()
    if not series_name:
        return None

    wiki_client = client or WikiClient()

    try:
        page_data = wiki_client.page_data_for_url(wiki_url)
        series = build_series_metadata_from_page_data(page_data, query=series_name)
    except Exception as exc:
        print(f"  - skip Wiki ComicInfo URL: {wiki_url} failed ({exc})")
        return None

    if use_cache:
        save_cached_wiki_series(
            path / SERIES_METADATA_CACHE_NAME,
            series_name=series_name,
            wiki_series=series,
        )

    return series


def load_cached_wiki_series(
    cache_path: str | Path,
    *,
    expected_series_name: Optional[str] = None,
) -> Optional[WikiSeriesMetadata]:
    path = Path(cache_path)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SERIES_METADATA_CACHE_VERSION:
            return None

        series_name = payload.get("series_name")
        if expected_series_name and _title_key(str(series_name or "")) != _title_key(expected_series_name):
            return None

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return None

        return wiki_series_from_cache_dict(metadata)
    except Exception as exc:
        print(f"  - skip Wiki ComicInfo cache: {path.name} unreadable ({exc})")
        return None


def save_cached_wiki_series(
    cache_path: str | Path,
    *,
    series_name: str,
    wiki_series: WikiSeriesMetadata,
) -> None:
    path = Path(cache_path)
    payload = {
        "schema_version": SERIES_METADATA_CACHE_VERSION,
        "series_name": series_name,
        "metadata": asdict(wiki_series),
    }

    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  - Wiki ComicInfo cached: {path.name}")
    except Exception as exc:
        print(f"  - skip Wiki ComicInfo cache write: {path.name} ({exc})")


def wiki_series_from_cache_dict(data: dict) -> WikiSeriesMetadata:
    manga_data = data.get("main_manga")
    if not isinstance(manga_data, dict):
        raise ValueError("cache metadata missing main_manga")

    return WikiSeriesMetadata(
        page_title=str(data.get("page_title") or ""),
        pageid=int(data.get("pageid") or 0),
        page_url=data.get("page_url"),
        wikibase_item=data.get("wikibase_item"),
        summary=data.get("summary"),
        main_manga=WikiMangaInfo(
            title=manga_data.get("title"),
            original_title=manga_data.get("original_title"),
            english_title=manga_data.get("english_title"),
            author=list(manga_data.get("author") or []),
            publishers=list(manga_data.get("publishers") or []),
            taiwan_publishers=list(manga_data.get("taiwan_publishers") or []),
            hongkong_publishers=list(manga_data.get("hongkong_publishers") or []),
            japan_publishers=list(manga_data.get("japan_publishers") or []),
            magazine=list(manga_data.get("magazine") or []),
            label=manga_data.get("label"),
            start=manga_data.get("start"),
            end=manga_data.get("end"),
            volume_count=manga_data.get("volume_count"),
            chapter_count=manga_data.get("chapter_count"),
            genre=list(manga_data.get("genre") or []),
            tags=list(manga_data.get("tags") or []),
            raw_fields=dict(manga_data.get("raw_fields") or {}),
        ),
        series_sort=data.get("series_sort"),
        categories=list(data.get("categories") or []),
    )


def build_comicinfo_xml_for_epub(
    *,
    epub_path: str,
    output_cbz_name: str,
    page_count: int,
    wiki_series: Optional[WikiSeriesMetadata] = None,
) -> Optional[bytes]:
    if wiki_series is None:
        return None

    epub = Path(epub_path)
    series_name = epub.parent.name
    volume_number = infer_volume_number(epub.name) or infer_volume_number(output_cbz_name)

    if volume_number is None:
        print(f"  - skip ComicInfo: cannot infer volume number from {epub.name}")
        return None

    comicinfo = wiki_series_to_comicinfo(
        wiki_series,
        volume_number,
        series_title=series_name,
        page_count=page_count,
    )

    if comicinfo.count is None:
        comicinfo.count = count_epubs_in_dir(epub.parent)

    return comicinfo.to_xml_bytes()


def infer_volume_number(filename: str) -> Optional[int]:
    import re

    normalized = filename.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    patterns = (
        r"第\s*0*(\d+)\s*[卷冊册]",
        r"vol(?:ume)?\.?\s*0*(\d+)",
        r"[_\-\s]0*(\d{1,3})(?=\D*$)",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.I)
        if match:
            return int(match.group(1))

    return None


def count_epubs_in_dir(path: Path) -> Optional[int]:
    count = sum(1 for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".epub")
    return count or None


def _title_key(value: str) -> str:
    return " ".join(value.replace("_", " ").split()).casefold()


def _is_exact_or_converted_title_match(
    requested_title: str,
    page_title: str,
    converted_title: Optional[str],
) -> bool:
    requested_key = _title_key(requested_title)
    page_key = _title_key(page_title)
    if requested_key == page_key:
        return True

    return converted_title is not None and _title_key(converted_title) == page_key
