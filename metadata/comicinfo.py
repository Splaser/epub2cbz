# metadata/comicinfo.py
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import ClassVar, Iterable, Optional
import xml.etree.ElementTree as ET

ANANSI_V21_FIELD_TAGS = (
    "Title",
    "Series",
    "Number",
    "Count",
    "Volume",
    "AlternateSeries",
    "AlternateNumber",
    "AlternateCount",
    "Summary",
    "Notes",
    "Year",
    "Month",
    "Day",
    "Writer",
    "Penciller",
    "Inker",
    "Colorist",
    "Letterer",
    "CoverArtist",
    "Editor",
    "Translator",
    "Publisher",
    "Imprint",
    "Genre",
    "Tags",
    "Web",
    "PageCount",
    "LanguageISO",
    "Format",
    "BlackAndWhite",
    "Manga",
    "Characters",
    "Teams",
    "Locations",
    "ScanInformation",
    "StoryArc",
    "StoryArcNumber",
    "SeriesGroup",
    "AgeRating",
    "Pages",
    "CommunityRating",
    "MainCharacterOrTeam",
    "Review",
    "GTIN",
)

KAVITA_EXTENSION_FIELD_TAGS = (
    "LocalizedSeries",
    "SeriesSort",
    "TitleSort",
    "Isbn",
    "UserRating",
)

YES_NO_VALUES = {"Unknown", "No", "Yes"}
MANGA_VALUES = {"Unknown", "No", "Yes", "YesAndRightToLeft"}
AGE_RATING_VALUES = {
    "Unknown",
    "Rating Pending",
    "Early Childhood",
    "Everyone",
    "G",
    "Everyone 10+",
    "PG",
    "Kids to Adults",
    "Teen",
    "MA15+",
    "Mature 17+",
    "M",
    "R18+",
    "Adults Only 18+",
    "X18+",
}
PAGE_TYPE_VALUES = {
    "FrontCover",
    "InnerCover",
    "Roundup",
    "Story",
    "Advertisement",
    "Editorial",
    "Letters",
    "Preview",
    "BackCover",
    "Other",
    "Deleted",
}


def _clean_text(value: object) -> Optional[str]:
    """Normalize scalar values for XML output."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # XML 1.0 disallows part of the control character range.
    text = "".join(
        ch for ch in text
        if ch in ("\t", "\n", "\r") or ord(ch) >= 0x20
    )
    return text.strip() or None


def _clean_int(value: object) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None

    text = _clean_text(value)
    if text is None:
        return None

    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _clean_bool(value: object) -> Optional[bool]:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    text = _clean_text(value)
    if text is None:
        return None

    normalized = text.lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False

    return None


def _bool_to_text(value: object) -> Optional[str]:
    parsed = _clean_bool(value)
    if parsed is None:
        return None
    return "true" if parsed else "false"


def _clean_rating(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None

    text = _clean_text(value)
    if text is None:
        return None

    try:
        rating = Decimal(text).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None

    if rating < Decimal("0") or rating > Decimal("5"):
        return None

    return rating


def _rating_to_text(value: object) -> Optional[str]:
    rating = _clean_rating(value)
    if rating is None:
        return None
    return f"{rating:.1f}"


def _join_list(values: Optional[Iterable[str] | str]) -> Optional[str]:
    """ComicInfo convention: comma separated values."""
    if not values:
        return None

    if isinstance(values, str):
        values = _split_list(values)

    cleaned = []
    seen = set()

    for value in values:
        text = _clean_text(value)
        if not text:
            continue

        # Keep original casing, dedupe case-insensitively.
        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(text)

    return ", ".join(cleaned) if cleaned else None


def _split_list(value: Optional[str]) -> list[str]:
    if not value:
        return []

    result = []
    seen = set()

    for part in value.split(","):
        text = _clean_text(part)
        if not text:
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        result.append(text)

    return result


def _clean_comicinfo_list(values: Optional[Iterable[str] | str]) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        return _split_list(values)

    joined = _join_list(values)
    return _split_list(joined)


def _normalize_enum(value: object, allowed: set[str], default: Optional[str]) -> Optional[str]:
    text = _clean_text(value)
    if text is None:
        return None
    if text in allowed:
        return text

    lower_map = {item.lower(): item for item in allowed}
    return lower_map.get(text.lower(), default)


def _split_page_types(value: object) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        parts = value.split()
    else:
        parts = list(value)

    result = []
    seen = set()
    lower_map = {item.lower(): item for item in PAGE_TYPE_VALUES}
    for part in parts:
        text = _clean_text(part)
        if text is None:
            continue

        text = lower_map.get(text.lower())
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return result


def _indent_xml(elem: ET.Element, level: int = 0) -> None:
    """Pretty-print XML for Python versions where ET.indent may not exist."""
    current_indent = "\n" + level * "  "
    child_indent = "\n" + (level + 1) * "  "

    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = child_indent

        for child in elem:
            _indent_xml(child, level + 1)

        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = current_indent

    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = current_indent


@dataclass
class ComicPageInfo:
    """ComicInfo v2.1 Pages/Page entry."""

    image: int
    page_type: list[str] = field(default_factory=list)
    double_page: Optional[bool] = None
    image_size: Optional[int] = None
    key: Optional[str] = None
    bookmark: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None

    XML_ATTR_MAP: ClassVar[dict[str, str]] = {
        "image": "Image",
        "page_type": "Type",
        "double_page": "DoublePage",
        "image_size": "ImageSize",
        "key": "Key",
        "bookmark": "Bookmark",
        "image_width": "ImageWidth",
        "image_height": "ImageHeight",
    }

    INT_ATTRS: ClassVar[set[str]] = {
        "image",
        "image_size",
        "image_width",
        "image_height",
    }

    def normalize(self) -> "ComicPageInfo":
        image = _clean_int(self.image)
        if image is None:
            raise ValueError("ComicPageInfo.image is required")
        self.image = image

        self.page_type = _split_page_types(self.page_type)
        self.double_page = _clean_bool(self.double_page)
        self.image_size = _clean_int(self.image_size)
        self.key = _clean_text(self.key)
        self.bookmark = _clean_text(self.bookmark)
        self.image_width = _clean_int(self.image_width)
        self.image_height = _clean_int(self.image_height)

        return self

    def to_element(self) -> ET.Element:
        self.normalize()
        elem = ET.Element("Page")
        elem.set("Image", str(self.image))

        if self.page_type:
            elem.set("Type", " ".join(self.page_type))

        double_page = _bool_to_text(self.double_page)
        if double_page is not None:
            elem.set("DoublePage", double_page)

        for attr_name in ("image_size", "key", "bookmark", "image_width", "image_height"):
            value = getattr(self, attr_name)

            if attr_name in self.INT_ATTRS:
                normalized = _clean_int(value)
                text = str(normalized) if normalized is not None else None
            else:
                text = _clean_text(value)

            if text is not None:
                elem.set(self.XML_ATTR_MAP[attr_name], text)

        return elem

    @classmethod
    def from_element(cls, elem: ET.Element) -> "ComicPageInfo":
        if elem.tag != "Page":
            raise ValueError(f"Unexpected page tag: {elem.tag}")

        image = _clean_int(elem.get("Image"))
        if image is None:
            raise ValueError("Page is missing required Image attribute")

        return cls(
            image=image,
            page_type=_split_page_types(elem.get("Type")),
            double_page=_clean_bool(elem.get("DoublePage")),
            image_size=_clean_int(elem.get("ImageSize")),
            key=_clean_text(elem.get("Key")),
            bookmark=_clean_text(elem.get("Bookmark")),
            image_width=_clean_int(elem.get("ImageWidth")),
            image_height=_clean_int(elem.get("ImageHeight")),
        )

    def copy(self) -> "ComicPageInfo":
        return ComicPageInfo(
            image=self.image,
            page_type=list(self.page_type),
            double_page=self.double_page,
            image_size=self.image_size,
            key=self.key,
            bookmark=self.bookmark,
            image_width=self.image_width,
            image_height=self.image_height,
        )


@dataclass
class ComicInfo:
    # Kavita-facing display fields.
    title: Optional[str] = None
    series: Optional[str] = None
    localized_series: Optional[str] = None
    series_sort: Optional[str] = None
    title_sort: Optional[str] = None

    # Numbering.
    number: Optional[str] = None
    count: Optional[int] = None
    volume: Optional[int] = None
    alternate_series: Optional[str] = None
    alternate_number: Optional[str] = None
    alternate_count: Optional[int] = None

    # Description/date.
    summary: Optional[str] = None
    notes: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None

    # Credits.
    writer: list[str] = field(default_factory=list)
    penciller: list[str] = field(default_factory=list)
    inker: list[str] = field(default_factory=list)
    colorist: list[str] = field(default_factory=list)
    letterer: list[str] = field(default_factory=list)
    cover_artist: list[str] = field(default_factory=list)
    editor: list[str] = field(default_factory=list)
    translator: list[str] = field(default_factory=list)

    # Publisher/classification.
    publisher: Optional[str] = None
    imprint: Optional[str] = None
    genre: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    web: Optional[str] = None
    page_count: Optional[int] = None
    language_iso: Optional[str] = None
    format: Optional[str] = None
    black_and_white: Optional[str] = None
    manga: Optional[str] = None

    # Entities/reading lists/collections.
    characters: list[str] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    scan_information: Optional[str] = None
    story_arc: Optional[str] = None
    story_arc_number: Optional[str] = None
    series_group: list[str] = field(default_factory=list)

    # Ratings/review/identifiers.
    age_rating: Optional[str] = None
    pages: list[ComicPageInfo] = field(default_factory=list)
    community_rating: Optional[Decimal | float | str] = None
    main_character_or_team: Optional[str] = None
    review: Optional[str] = None
    gtin: Optional[str] = None
    isbn: Optional[str] = None
    user_rating: Optional[Decimal | float | str] = None

    # dataclass field name -> ComicInfo.xml tag name.
    XML_FIELD_MAP: ClassVar[dict[str, str]] = {
        "title": "Title",
        "series": "Series",
        "localized_series": "LocalizedSeries",
        "series_sort": "SeriesSort",
        "title_sort": "TitleSort",
        "number": "Number",
        "count": "Count",
        "volume": "Volume",
        "alternate_series": "AlternateSeries",
        "alternate_number": "AlternateNumber",
        "alternate_count": "AlternateCount",
        "summary": "Summary",
        "notes": "Notes",
        "year": "Year",
        "month": "Month",
        "day": "Day",
        "writer": "Writer",
        "penciller": "Penciller",
        "inker": "Inker",
        "colorist": "Colorist",
        "letterer": "Letterer",
        "cover_artist": "CoverArtist",
        "editor": "Editor",
        "translator": "Translator",
        "publisher": "Publisher",
        "imprint": "Imprint",
        "genre": "Genre",
        "tags": "Tags",
        "web": "Web",
        "page_count": "PageCount",
        "language_iso": "LanguageISO",
        "format": "Format",
        "black_and_white": "BlackAndWhite",
        "manga": "Manga",
        "characters": "Characters",
        "teams": "Teams",
        "locations": "Locations",
        "scan_information": "ScanInformation",
        "story_arc": "StoryArc",
        "story_arc_number": "StoryArcNumber",
        "series_group": "SeriesGroup",
        "age_rating": "AgeRating",
        "pages": "Pages",
        "community_rating": "CommunityRating",
        "main_character_or_team": "MainCharacterOrTeam",
        "review": "Review",
        "gtin": "GTIN",
        "isbn": "Isbn",
        "user_rating": "UserRating",
    }

    XML_FIELD_ALIASES: ClassVar[dict[str, str]] = {
        # Kavita wiki currently says Alternative*, while Anansi v2.1 defines Alternate*.
        "AlternativeSeries": "alternate_series",
        "AlternativeNumber": "alternate_number",
        "AlternativeCount": "alternate_count",
    }

    LIST_FIELDS: ClassVar[set[str]] = {
        "genre",
        "tags",
        "writer",
        "penciller",
        "inker",
        "colorist",
        "letterer",
        "cover_artist",
        "editor",
        "translator",
        "series_group",
        "characters",
        "teams",
        "locations",
    }

    INT_FIELDS: ClassVar[set[str]] = {
        "count",
        "volume",
        "alternate_count",
        "year",
        "month",
        "day",
        "page_count",
    }

    ENUM_FIELDS: ClassVar[dict[str, tuple[set[str], Optional[str]]]] = {
        "black_and_white": (YES_NO_VALUES, "Unknown"),
        "manga": (MANGA_VALUES, "Yes"),
        "age_rating": (AGE_RATING_VALUES, "Unknown"),
    }

    RATING_FIELDS: ClassVar[set[str]] = {
        "community_rating",
        "user_rating",
    }

    def normalize_for_kavita(self) -> "ComicInfo":
        """
        Light normalization only.
        Filename parsing, wiki scraping, and manual override logic should stay outside.
        """
        for attr_name in self.XML_FIELD_MAP:
            if attr_name == "pages":
                continue

            value = getattr(self, attr_name)
            if attr_name in self.LIST_FIELDS:
                setattr(self, attr_name, _clean_comicinfo_list(value))
            elif attr_name in self.INT_FIELDS:
                setattr(self, attr_name, _clean_int(value))
            elif attr_name in self.ENUM_FIELDS:
                allowed, default = self.ENUM_FIELDS[attr_name]
                setattr(self, attr_name, _normalize_enum(value, allowed, default))
            elif attr_name in self.RATING_FIELDS:
                setattr(self, attr_name, _clean_rating(value))
            else:
                setattr(self, attr_name, _clean_text(value))

        self.pages = [page.copy().normalize() for page in self.pages if page is not None]
        return self

    def to_element(self) -> ET.Element:
        normalized = self.copy().normalize_for_kavita()

        root = ET.Element("ComicInfo")

        for attr_name, tag_name in normalized.XML_FIELD_MAP.items():
            value = getattr(normalized, attr_name)

            if attr_name == "pages":
                if not value:
                    continue

                pages_elem = ET.SubElement(root, tag_name)
                for page in value:
                    pages_elem.append(page.to_element())
                continue

            if attr_name in self.LIST_FIELDS:
                text = _join_list(value)
            elif attr_name in self.INT_FIELDS:
                normalized_int = _clean_int(value)
                text = str(normalized_int) if normalized_int is not None else None
            elif attr_name in self.RATING_FIELDS:
                text = _rating_to_text(value)
            else:
                text = _clean_text(value)

            if text is None:
                continue

            child = ET.SubElement(root, tag_name)
            child.text = text

        _indent_xml(root)
        return root

    def to_xml_bytes(self) -> bytes:
        root = self.to_element()
        return ET.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=False,
        )

    def to_xml_string(self) -> str:
        return self.to_xml_bytes().decode("utf-8")

    def missing_v21_fields(self) -> list[str]:
        emitted = set(self.XML_FIELD_MAP.values())
        return [tag for tag in ANANSI_V21_FIELD_TAGS if tag not in emitted]

    def missing_kavita_extension_fields(self) -> list[str]:
        emitted = set(self.XML_FIELD_MAP.values())
        return [tag for tag in KAVITA_EXTENSION_FIELD_TAGS if tag not in emitted]

    @classmethod
    def from_element(cls, root: ET.Element) -> "ComicInfo":
        if root.tag != "ComicInfo":
            raise ValueError(f"Unexpected root tag: {root.tag}")

        reverse_map = {xml: attr for attr, xml in cls.XML_FIELD_MAP.items()}
        reverse_map.update(cls.XML_FIELD_ALIASES)
        kwargs = {}

        for child in root:
            attr_name = reverse_map.get(child.tag)
            if not attr_name:
                continue

            if attr_name == "pages":
                pages = []
                for page_elem in child.findall("Page"):
                    try:
                        pages.append(ComicPageInfo.from_element(page_elem))
                    except ValueError:
                        continue
                if pages:
                    kwargs[attr_name] = pages
                continue

            text = _clean_text(child.text)
            if text is None:
                continue

            if attr_name in cls.LIST_FIELDS:
                kwargs[attr_name] = _split_list(text)
            elif attr_name in cls.INT_FIELDS:
                kwargs[attr_name] = _clean_int(text)
            elif attr_name in cls.RATING_FIELDS:
                kwargs[attr_name] = _clean_rating(text)
            else:
                kwargs[attr_name] = text

        return cls(**kwargs).normalize_for_kavita()

    @classmethod
    def from_xml_bytes(cls, data: bytes) -> "ComicInfo":
        root = ET.fromstring(data)
        return cls.from_element(root)

    @classmethod
    def from_xml_string(cls, text: str) -> "ComicInfo":
        return cls.from_xml_bytes(text.encode("utf-8"))

    def merge_missing(self, other: "ComicInfo") -> "ComicInfo":
        """
        Fill empty fields from other.
        Existing values win. Use this for: existing ComicInfo.xml + scraper result.
        """
        for f in fields(self):
            name = f.name
            current = getattr(self, name)
            incoming = getattr(other, name)

            if name in self.LIST_FIELDS or name == "pages":
                if not current and incoming:
                    setattr(
                        self,
                        name,
                        [item.copy() if hasattr(item, "copy") else item for item in incoming],
                    )
                continue

            if current in (None, "") and incoming not in (None, ""):
                setattr(self, name, incoming)

        return self

    def copy(self) -> "ComicInfo":
        kwargs = {}

        for f in fields(self):
            name = f.name
            value = getattr(self, name)
            if isinstance(value, list):
                kwargs[name] = [
                    item.copy() if hasattr(item, "copy") else item
                    for item in value
                ]
            else:
                kwargs[name] = value

        return ComicInfo(**kwargs)


def build_basic_comicinfo(
    *,
    series: str,
    number: str | int,
    title: Optional[str] = None,
    localized_series: Optional[str] = None,
    series_sort: Optional[str] = None,
    count: Optional[int] = None,
    volume: Optional[int] = None,
    summary: Optional[str] = None,
    publisher: Optional[str] = None,
    year: Optional[int] = None,
    language_iso: Optional[str] = "zh-Hant-TW",
    manga: str = "Yes",
    age_rating: Optional[str] = "Teen",
    genre: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    writer: Optional[list[str]] = None,
    penciller: Optional[list[str]] = None,
    translator: Optional[list[str]] = None,
    web: Optional[str] = None,
    page_count: Optional[int] = None,
) -> ComicInfo:
    """
    Convenience builder for script entry points.
    More complex filename/wiki/override logic should not live here.
    """
    number_text = str(number).strip()

    if title is None:
        title = f"第 {number_text} 卷"

    if localized_series is None:
        localized_series = series

    if series_sort is None:
        series_sort = series

    return ComicInfo(
        title=title,
        series=series,
        localized_series=localized_series,
        series_sort=series_sort,
        number=number_text,
        count=count,
        volume=volume,
        summary=summary,
        year=year,
        writer=writer or [],
        penciller=penciller or [],
        publisher=publisher,
        genre=genre or [],
        tags=tags or [],
        web=web,
        page_count=page_count,
        language_iso=language_iso,
        manga=manga,
        translator=translator or [],
        age_rating=age_rating,
    )
