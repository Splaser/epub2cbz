import os
import re

from metadata.comicinfo import ComicInfo


_KAVITA_PERIODICAL_NAME_RE = re.compile(
    r"^(?P<series>.+?)\s+(?P<kind>v|SP)(?P<first>\d+)"
    r"(?:-(?P<last>\d+))?(?:\s+(?P<label>.+))?\.cbz$",
    flags=re.IGNORECASE,
)


def build_comicinfo_xml_for_pdf(
    *,
    pdf_path: str,
    output_cbz_name: str,
    page_count: int,
) -> bytes:
    """Build metadata without overriding Kavita's filename-based numbering."""
    series_name = os.path.basename(os.path.dirname(os.path.abspath(pdf_path))).strip()
    source_title = os.path.splitext(os.path.basename(pdf_path))[0].strip()
    match = _KAVITA_PERIODICAL_NAME_RE.match(output_cbz_name)

    title = source_title
    format_name = "Magazine"
    tags = []

    if match is not None:
        first_issue = int(match.group("first"))
        last_issue = int(match.group("last")) if match.group("last") else None
        label = (match.group("label") or "").strip()

        if last_issue is not None:
            title = f"第{first_issue:03d}-{last_issue:03d}期"
        else:
            title = f"第{first_issue:03d}期"

        if label:
            title = f"{title} {label}"
            tags.append(label)

        if match.group("kind").casefold() == "sp":
            format_name = "Special"

    comicinfo = ComicInfo(
        title=title,
        series=series_name or None,
        localized_series=series_name or None,
        series_sort=series_name or None,
        page_count=page_count,
        format=format_name,
        tags=tags,
    )
    return comicinfo.to_xml_bytes()
