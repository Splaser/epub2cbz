# metadata/epub_comicinfo.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .comicinfo import build_basic_comicinfo


def build_comicinfo_xml_for_epub(
    *,
    epub_path: str,
    output_cbz_name: str,
    page_count: int,
) -> Optional[bytes]:
    epub = Path(epub_path)
    series_name = epub.parent.name
    volume_number = infer_volume_number(epub.name)

    if volume_number is None:
        print(f"  - skip ComicInfo: cannot infer volume number from {epub.name}")
        return None

    # main 流程第一版先不要联网，不要强行 Wiki 匹配
    total_count = count_epubs_in_dir(epub.parent)

    comicinfo = build_basic_comicinfo(
        series=series_name,
        number=volume_number,
        count=total_count,
        page_count=page_count,
        language_iso="zh-Hant-TW",
        manga="Yes",
        age_rating="Teen",
    )

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