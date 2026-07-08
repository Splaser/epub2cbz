# metadata/wiki_to_comicinfo.py
from __future__ import annotations

import re
from typing import Optional

from metadata.comicinfo import ComicInfo
from metadata.wiki_models import WikiMangaInfo, WikiSeriesMetadata


DEFAULT_LANGUAGE_ISO = "zh-Hant-TW"
DEFAULT_MANGA_VALUE = "Yes"
DEFAULT_AGE_RATING = "Teen"


def wiki_series_to_comicinfo(
    wiki: WikiSeriesMetadata,
    volume_number: str | int,
    *,
    title: Optional[str] = None,
    series_title: Optional[str] = None,
    series_sort: Optional[str] = None,
    write_number: bool = True,
    write_volume: bool = False,
    language_iso: str = DEFAULT_LANGUAGE_ISO,
    manga: str = DEFAULT_MANGA_VALUE,
    age_rating: Optional[str] = DEFAULT_AGE_RATING,
    page_count: Optional[int] = None,
) -> ComicInfo:
    manga_info = wiki.main_manga
    number_text = str(volume_number).strip()
    volume = _parse_volume_number(volume_number)
    series_title = series_title or _series_title(wiki)
    issue_title = title or _volume_title(number_text)

    return ComicInfo(
        title=issue_title,
        series=series_title,
        localized_series=series_title,
        series_sort=series_sort or wiki.series_sort or series_title,
        number=number_text if write_number else None,
        count=manga_info.volume_count,
        volume=volume if write_volume else None,
        summary=wiki.summary,
        year=_extract_year(manga_info.start),
        writer=_display_list(manga_info.author),
        publisher=_display_text(_preferred_publisher(manga_info)),
        imprint=manga_info.label,
        genre=_genres_from_wiki(manga_info, wiki.categories),
        tags=_tags_from_wiki(manga_info, wiki.categories),
        web=wiki.page_url,
        page_count=page_count,
        language_iso=language_iso,
        manga=manga,
        age_rating=age_rating,
        gtin=None,
        notes=_build_notes(wiki),
    )


def _series_title(wiki: WikiSeriesMetadata) -> str:
    manga_info = wiki.main_manga
    return (
        manga_info.title
        or manga_info.original_title
        or manga_info.english_title
        or wiki.page_title
    )


def _volume_title(number_text: str) -> str:
    return f"第 {number_text} 卷"


def _parse_volume_number(value: str | int) -> Optional[int]:
    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"\d+", text.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    if not match:
        return None

    return int(match.group(0))


def _extract_year(value: Optional[str]) -> Optional[int]:
    if not value:
        return None

    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return None

    return int(match.group(0))


def _preferred_publisher(manga_info: WikiMangaInfo) -> Optional[str]:
    for candidates in (
        manga_info.taiwan_publishers,
        manga_info.hongkong_publishers,
        manga_info.japan_publishers,
        manga_info.publishers,
    ):
        if candidates:
            return candidates[0]

    return None


def _genres_from_wiki(manga_info: WikiMangaInfo, categories: list[str]) -> list[str]:
    genre_map = {
        "格鬥技漫畫": "Action",
        "格斗技漫画": "Action",
        "動作漫畫": "Action",
        "动作漫画": "Action",
    }
    genres = []

    for value in [*manga_info.genre, *categories]:
        mapped = genre_map.get(value)
        if mapped:
            genres.append(mapped)

    return _dedupe(genres)


def _tags_from_wiki(manga_info: WikiMangaInfo, categories: list[str]) -> list[str]:
    # Magazine/categories are useful for filtering, but should stay outside the wikitext DTO layer.
    ignored_categories = {
        "日本漫畫作品",
        "日本漫画作品",
        "2009年日本OVA",
        "含有日語的條目",
        "含有英语的条目",
        "含有英語的條目",
        "使用ISBN魔术链接的页面",
    }
    tags = [
        *manga_info.tags,
        *manga_info.genre,
        *manga_info.magazine,
        *(category for category in categories if category not in ignored_categories),
    ]
    return _dedupe(tags)


def _build_notes(wiki: WikiSeriesMetadata) -> Optional[str]:
    parts = []

    if wiki.wikibase_item:
        parts.append(f"Wikidata: {wiki.wikibase_item}")

    if wiki.page_url:
        parts.append(f"Source: {wiki.page_url}")

    if not parts:
        return None

    return "\n".join(parts)


def _display_list(values: list[str]) -> list[str]:
    result = []
    for value in values:
        text = _display_text(value)
        if text:
            result.append(text)
    return result


def _display_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    overrides = {
        "手代木史织": "手代木史織",
        "秋田书店": "秋田書店",
    }

    return overrides.get(value, value)


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        text = str(value).strip()
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        result.append(text)

    return result
