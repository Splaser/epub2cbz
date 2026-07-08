# metadata/wiki_scraper.py
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Optional

try:
    from metadata.wiki_client import WikiClient
    from metadata.wiki_models import WikiPageData, WikiSeriesMetadata
    from metadata.wiki_wikitext import clean_wiki_text, iter_templates, parse_wikitext
except ModuleNotFoundError:
    from wiki_client import WikiClient
    from wiki_models import WikiPageData, WikiSeriesMetadata
    from wiki_wikitext import clean_wiki_text, iter_templates, parse_wikitext


def build_series_metadata_from_wikitext(
    wikitext: str,
    *,
    page_title: str,
    pageid: int,
    page_url: Optional[str] = None,
    wikibase_item: Optional[str] = None,
    summary: Optional[str] = None,
    query: Optional[str] = None,
    categories: Optional[list[str]] = None,
    series_sort: Optional[str] = None,
) -> WikiSeriesMetadata:
    parsed = parse_wikitext(wikitext, query=query)
    if parsed.main_manga is None:
        raise ValueError("No Infobox animanga/Manga block found in wikitext")

    return WikiSeriesMetadata(
        page_title=page_title,
        pageid=pageid,
        page_url=page_url,
        wikibase_item=wikibase_item,
        summary=summary or extract_lead_summary(wikitext),
        main_manga=parsed.main_manga,
        series_sort=series_sort,
        categories=list(categories if categories is not None else parsed.categories),
    )


def build_series_metadata_from_page_data(
    page_data: WikiPageData,
    *,
    query: Optional[str] = None,
) -> WikiSeriesMetadata:
    return build_series_metadata_from_wikitext(
        page_data.wikitext,
        page_title=page_data.title,
        pageid=page_data.pageid,
        page_url=page_data.page_url,
        wikibase_item=page_data.wikibase_item,
        summary=page_data.extract,
        query=query,
        categories=page_data.categories,
        series_sort=page_data.defaultsort,
    )


def build_series_metadata_from_title(
    title: str,
    *,
    client: Optional[WikiClient] = None,
    query: Optional[str] = None,
) -> WikiSeriesMetadata:
    wiki_client = client or WikiClient()
    return build_series_metadata_from_page_data(
        wiki_client.page_data(title),
        query=query,
    )


def build_series_metadata_from_query(
    query: str,
    *,
    client: Optional[WikiClient] = None,
    limit: int = 5,
) -> WikiSeriesMetadata:
    wiki_client = client or WikiClient()
    return build_series_metadata_from_page_data(
        wiki_client.page_data_for_query(query, limit=limit),
        query=query,
    )


def build_series_metadata_from_file(
    wikitext_path: str | Path,
    *,
    page_title: Optional[str] = None,
    pageid: int = 0,
    page_url: Optional[str] = None,
    wikibase_item: Optional[str] = None,
    summary: Optional[str] = None,
    query: Optional[str] = None,
    categories: Optional[list[str]] = None,
    series_sort: Optional[str] = None,
) -> WikiSeriesMetadata:
    path = Path(wikitext_path)
    wikitext = path.read_text(encoding="utf-8")

    return build_series_metadata_from_wikitext(
        wikitext,
        page_title=page_title or path.parent.name,
        pageid=pageid,
        page_url=page_url,
        wikibase_item=wikibase_item,
        summary=summary,
        query=query,
        categories=categories,
        series_sort=series_sort,
    )


def extract_lead_summary(wikitext: str) -> Optional[str]:
    text = wikitext
    for template in iter_templates(wikitext):
        text = text.replace(template, "\n", 1)

    before_sections = text.split("\n==", 1)[0]
    for paragraph in before_sections.split("\n\n"):
        cleaned = clean_wiki_text(paragraph)
        if cleaned and not cleaned.startswith("[[Category:"):
            return cleaned

    return None


def _sample_wikitext_path() -> Path:
    root = Path.cwd() / "probe_output"
    matches = sorted(root.glob("*/05_wikitext.txt"))
    if not matches:
        raise FileNotFoundError("No probe_output/*/05_wikitext.txt sample found")
    return matches[0]


if __name__ == "__main__":
    sample_path = _sample_wikitext_path()
    series = build_series_metadata_from_file(
        sample_path,
        page_title=sample_path.parent.name,
        query="LC外傳",
    )
    print(json.dumps(asdict(series), ensure_ascii=False, indent=2))
