# metadata/epub_comicinfo.py
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Optional

from utils.metadata_utils import clean_raw_name, extract_special_label

from .wiki_client import WikiClient
from .wiki_models import WikiMangaInfo, WikiSeriesMetadata
from .wiki_scraper import build_series_metadata_from_page_data
from .wiki_to_comicinfo import wiki_series_to_comicinfo


SERIES_METADATA_CACHE_NAME = "series.meta.json"
SERIES_METADATA_CACHE_VERSION = 4


# Local/publisher titles that resolve to an unrelated zh.wikipedia concept page.
# Use the canonical manga article title before attempting the normal lookup.
WIKI_TITLE_OVERRIDES = {
    "死神": "BLEACH",
}


def load_exact_wiki_series_for_dir(
    series_dir: str | Path,
    *,
    client: Optional[WikiClient] = None,
    use_cache: bool = True,
) -> Optional[WikiSeriesMetadata]:
    """
    Try to load Wiki metadata for a series directory.

    A Wiki redirect or alternate page title is accepted. The local directory name
    remains the ComicInfo Series later, while the available Wiki fields are kept.
    Network failures still return None so EPUB -> CBZ conversion can continue.

    Successful lookups are cached once per series directory in series.meta.json.
    """
    path = Path(series_dir)
    series_name = path.name.strip()
    if not series_name:
        return None

    lookup_title = WIKI_TITLE_OVERRIDES.get(_title_key(series_name), series_name)

    cache_path = path / SERIES_METADATA_CACHE_NAME
    if use_cache:
        cached = load_cached_wiki_series(cache_path, expected_series_name=series_name)
        if cached is not None:
            print(f"  - Wiki ComicInfo cache: {cache_path.name}")
            return cached

    wiki_client = client or WikiClient()

    try:
        page_data = wiki_client.page_data(lookup_title)
    except Exception as direct_exc:
        try:
            page_data = wiki_client.page_data_for_query(lookup_title, limit=5)
            print(
                "  - Wiki ComicInfo search fallback: "
                f"query '{lookup_title}' -> page '{page_data.title}'"
            )
        except Exception as search_exc:
            print(
                f"  - skip Wiki ComicInfo: {series_name} lookup failed "
                f"(direct: {direct_exc}; search: {search_exc})"
            )
            return None

    if not _is_exact_or_converted_title_match(series_name, page_data.title, page_data.converted_title):
        print(
            "  - Wiki ComicInfo title differs; keeping Wiki metadata: "
            f"directory '{series_name}' -> page '{page_data.title}'"
        )

    try:
        series = build_series_metadata_from_page_data(page_data, query=lookup_title)
    except Exception as exc:
        print(
            "  - Wiki ComicInfo infobox parse failed; keeping page metadata: "
            f"{series_name} ({exc})"
        )
        series = _partial_wiki_series_from_page_data(page_data)

    if use_cache:
        save_cached_wiki_series(cache_path, series_name=series_name, wiki_series=series)

    return series


def _partial_wiki_series_from_page_data(page_data) -> WikiSeriesMetadata:
    """Keep page-level Wiki fields when no usable manga infobox is available."""
    return WikiSeriesMetadata(
        page_title=page_data.title,
        pageid=page_data.pageid,
        page_url=page_data.page_url,
        wikibase_item=page_data.wikibase_item,
        summary=page_data.extract or page_data.description,
        main_manga=WikiMangaInfo(title=page_data.title),
        series_sort=page_data.defaultsort,
        categories=list(page_data.categories),
    )


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
    cleaned_title = clean_raw_name(epub.stem)
    series_prefix = f"{series_name} - "
    if cleaned_title.casefold().startswith(series_prefix.casefold()):
        cleaned_title = cleaned_title[len(series_prefix):].strip()
    is_special = extract_special_label(cleaned_title) is not None
    volume_number = infer_volume_number(epub.name) or infer_volume_number(output_cbz_name)

    if volume_number is None and not is_special:
        print(f"  - skip ComicInfo: cannot infer volume number from {epub.name}")
        return None

    comicinfo = wiki_series_to_comicinfo(
        wiki_series,
        volume_number or 0,
        title=cleaned_title if is_special else None,
        series_title=series_name,
        write_number=volume_number is not None,
        page_count=page_count,
    )
    if is_special:
        comicinfo.format = "Special"

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
            # A number describing an anniversary is not a volume number.  This
            # matters for both source names and renamed output such as
            # "Series - 20周年紀念短篇.cbz".
            following_text = normalized[match.end():]
            if re.match(r"\s*(?:週年|周年)", following_text):
                continue
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
