# metadata/wiki_to_comicinfo.py
from __future__ import annotations

import re
from typing import Optional

from metadata.comicinfo import ComicInfo
from metadata.wiki_models import WikiMangaInfo, WikiSeriesMetadata


DEFAULT_LANGUAGE_ISO = "zh-Hant-TW"
DEFAULT_MANGA_VALUE = "Yes"
DEFAULT_AGE_RATING = "Teen"


# Wikipedia mixes useful subject categories with categories used to maintain the
# encyclopedia itself.  None of the latter belong in a comic library's tags.
_NON_CONTENT_CATEGORY_PATTERNS = (
    # Citation/source/template tracking (CS1, language markers, subscriptions).
    re.compile(r"^CS1", re.I),
    re.compile(r"^(?:引文|引用)格式", re.I),
    re.compile(r"(?:錯誤|错误)"),
    re.compile(r"^含有.*(?:條目|条目|文本)"),
    re.compile(r"(?:需訂閱|需订阅).*(?:頁面|页面)"),
    re.compile(r"(?:條目|条目|頁面|页面)$"),
    # Wikipedia/Wikidata consistency and account tracking categories.
    re.compile(r"(?:維基|维基|Wikidata|维基数据|維基數據)", re.I),
    re.compile(r"(?:用戶名|用户名)", re.I),
)


# Kavita genres are free-form, but keeping a small stable vocabulary makes its
# filters useful across Traditional/Simplified Chinese and English Wiki pages.
_GENRE_PATTERNS = (
    ("Action", re.compile(
        r"(?:動作|动作|戰鬥|战斗|格鬥|格斗|武俠|武侠|action)",
        re.I,
    )),
    ("Adventure", re.compile(r"(?:冒險|冒险|adventure)", re.I)),
    ("Fantasy", re.compile(r"(?:奇幻|魔幻|魔法|fantasy)", re.I)),
    ("Science fiction", re.compile(r"(?:科幻|科學幻想|科学幻想|science[ -]?fiction|sci-fi)", re.I)),
    ("Mystery", re.compile(r"(?:推理|懸疑|悬疑|偵探|侦探|mystery|detective)", re.I)),
    ("Thriller", re.compile(r"(?:驚悚|惊悚|thriller)", re.I)),
    ("Horror", re.compile(r"(?:恐怖|獵奇|猎奇|horror)", re.I)),
    ("Romance", re.compile(r"(?:戀愛|恋爱|愛情|爱情|浪漫|romance)", re.I)),
    ("Comedy", re.compile(r"(?:喜劇|喜剧|搞笑|幽默|comedy)", re.I)),
    ("Drama", re.compile(r"(?:劇情|剧情|戲劇|戏剧|drama)", re.I)),
    ("Historical", re.compile(
        r"(?:歷史|历史|(?:時代|时代)(?:劇|剧|背景)|historical)",
        re.I,
    )),
    ("Sports", re.compile(r"(?:體育|体育|運動|运动|競技|竞技|sports?)", re.I)),
    ("Slice of life", re.compile(r"(?:日常|生活片段|slice of life)", re.I)),
    ("Supernatural", re.compile(r"(?:超自然|靈異|灵异|神怪|妖怪|supernatural)", re.I)),
    ("Mecha", re.compile(r"(?:機甲|机甲|機器人|机器人|mecha)", re.I)),
)


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
        publisher=_display_publisher(_preferred_publisher(manga_info)),
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
    # This collection targets Traditional Chinese editions. Do not fall back
    # to the original Japanese publisher, which describes a different release.
    for candidates in (
        manga_info.taiwan_publishers,
        manga_info.hongkong_publishers,
    ):
        if candidates:
            return candidates[0]

    return None


def _genres_from_wiki(manga_info: WikiMangaInfo, categories: list[str]) -> list[str]:
    genres = []

    for value in [*manga_info.genre, *categories]:
        text = str(value).strip()
        if not text or not _is_content_category(text):
            continue

        for genre, pattern in _GENRE_PATTERNS:
            if pattern.search(text):
                genres.append(genre)

    return _dedupe(genres)


def _tags_from_wiki(manga_info: WikiMangaInfo, categories: list[str]) -> list[str]:
    # Magazine/categories are useful for filtering, but should stay outside the wikitext DTO layer.
    tags = [
        *manga_info.tags,
        *manga_info.genre,
        *manga_info.magazine,
        *(category for category in categories if _is_content_category(category)),
    ]
    return _dedupe(tags)


def _is_content_category(value: str) -> bool:
    text = str(value).strip()
    if not text:
        return False

    return not any(pattern.search(text) for pattern in _NON_CONTENT_CATEGORY_PATTERNS)


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


def _display_publisher(value: Optional[str]) -> Optional[str]:
    text = _display_text(value)
    if not text:
        return None

    # Country/region labels describe which localized publisher Wiki listed;
    # Kavita's Publisher field should contain only the publisher's actual name.
    text = re.sub(
        r"^\s*(?:(?:"
        r"臺灣|台灣|台湾|日本|香港|中國大陸|中国大陆|中國|中国|新加坡|"
        r"韓國|韩国|美國|美国|加拿大|法國|法国|德國|德国|義大利|意大利|"
        r"西班牙|馬來西亞|马来西亚"
        r")\s*[：:]\s*)+",
        "",
        text,
        flags=re.I,
    ).strip()

    # Wiki may describe publisher succession as "old → current". Kavita has a
    # single Publisher field, so keep the rightmost/current publisher only.
    publisher_chain = re.split(r"\s*(?:→|⇒|➜|➝|⟶|-+>)\s*", text)
    return publisher_chain[-1].strip() or None


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
