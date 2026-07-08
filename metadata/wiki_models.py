# metadata/wiki_models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WikiSearchItem:
    title: str
    pageid: int
    snippet: Optional[str] = None
    size: Optional[int] = None
    wordcount: Optional[int] = None


@dataclass
class WikiPageSummary:
    title: str
    extract: Optional[str] = None
    description: Optional[str] = None
    page_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    wikibase_item: Optional[str] = None


@dataclass
class WikiPageData:
    title: str
    pageid: int
    wikitext: str
    extract: Optional[str] = None
    description: Optional[str] = None
    page_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    wikibase_item: Optional[str] = None
    defaultsort: Optional[str] = None
    categories: list[str] = field(default_factory=list)


@dataclass
class WikiAnimangaHeader:
    title: Optional[str] = None
    original_title: Optional[str] = None
    english_title: Optional[str] = None
    genre: list[str] = field(default_factory=list)
    raw_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class WikiMangaInfo:
    title: Optional[str] = None
    original_title: Optional[str] = None
    english_title: Optional[str] = None
    author: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    taiwan_publishers: list[str] = field(default_factory=list)
    hongkong_publishers: list[str] = field(default_factory=list)
    japan_publishers: list[str] = field(default_factory=list)
    magazine: list[str] = field(default_factory=list)
    label: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    volume_count: Optional[int] = None
    chapter_count: Optional[int] = None
    genre: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class WikiWikitextMetadata:
    header: Optional[WikiAnimangaHeader] = None
    manga_blocks: list[WikiMangaInfo] = field(default_factory=list)
    main_manga: Optional[WikiMangaInfo] = None
    categories: list[str] = field(default_factory=list)


@dataclass
class WikiSeriesMetadata:
    page_title: str
    pageid: int
    page_url: Optional[str]
    wikibase_item: Optional[str]
    summary: Optional[str]
    main_manga: WikiMangaInfo
    series_sort: Optional[str] = None
    categories: list[str] = field(default_factory=list)
