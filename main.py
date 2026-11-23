import argparse
import html
import os
import re
import sys
import tempfile
from typing import Callable, Optional
from builder.cbz_builder import make_cbz
from images.splitter import prepare_epub_page
from metadata.epub_comicinfo import (
    build_comicinfo_xml_for_epub,
    load_exact_wiki_series_for_dir,
    load_wiki_series_for_url,
)
from metadata.wiki_models import WikiSearchItem
from parser.html_parser import extract_image_references, is_image_file
from utils.epub_utils import extract_epub, get_html_files_by_spine, fallback_all_images
from utils.metadata_utils import build_output_cbz_name


_EPUB_AD_DOCUMENTS = {"createby", "createinfo", "endinfo", "theendinfo", "ad", "ads", "adv", "advertisement"}


def collect_epub_pages(epub_root: str) -> list[tuple[str, bool]]:
    spine_files, spine = get_html_files_by_spine(epub_root)
    if not spine:
        return [(path, False) for path in fallback_all_images(epub_root)]

    pages = []
    for path, item in zip(spine_files, spine):
        stem, ext = os.path.splitext(os.path.basename(path).lower())
        if is_image_file(path):
            pages.append((path, False))
        elif ext in {".html", ".htm", ".xhtml", ".svg"} or item["media_type"] in {
            "application/xhtml+xml", "text/html", "image/svg+xml",
        }:
            if stem not in _EPUB_AD_DOCUMENTS:
                pages.extend(extract_image_references(path, epub_root))
        else:
            raise ValueError(f"Unsupported EPUB spine document: {item['href']}")
    return pages


def epub_to_cbz_fixed(epub_path, wiki_series_metadata=None, *, series_title=None):
    epub_path = os.path.abspath(epub_path)
    if series_title is not None:
        series_title = series_title.strip()
        if not series_title or re.search(r'[<>:"/\\|?*\x00-\x1f]', series_title):
            raise ValueError("Series title must be a valid filename prefix")
    output_name = build_output_cbz_name(epub_path, series_name=series_title)
    output_cbz = os.path.join(os.path.dirname(epub_path), output_name)
    with tempfile.TemporaryDirectory(prefix="epub2cbz_") as temp_dir:
        epub_root = os.path.join(temp_dir, "epub")
        rotated_dir = os.path.join(temp_dir, "rotated")
        os.mkdir(epub_root)
        os.mkdir(rotated_dir)
        extract_epub(epub_path, epub_root)
        pages = collect_epub_pages(epub_root)
        if not pages:
            raise ValueError(f"EPUB has no image pages: {epub_path}")
        final_images = [
            prepare_epub_page(path, rotated_dir, rotate=rotate)
            for path, rotate in pages
        ]

        comicinfo_xml = build_comicinfo_xml_for_epub(
            epub_path=epub_path,
            output_cbz_name=output_name,
            page_count=len(final_images),
            wiki_series=wiki_series_metadata,
            series_title=series_title,
        )

        make_cbz(final_images, output_cbz, comicinfo_xml=comicinfo_xml)
        print(f"✅ CBZ created: {output_cbz}, total pages: {len(final_images)}")


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one EPUB or scan the executable's directory for EPUBs.")
    parser.add_argument("epub", nargs="?", help="Convert only this EPUB file.")
    parser.add_argument("--series-title", help="Use this series name for the CBZ filename and ComicInfo.")
    parser.add_argument(
        "--wiki-url",
        help="Explicit zh.wikipedia page URL to use as metadata source when the directory name is not the Wiki title.",
    )
    return parser.parse_args()


def choose_wiki_candidate(
    query: str,
    candidates: list[WikiSearchItem],
    *,
    input_func: Callable[[str], str] = input,
) -> Optional[str]:
    print(f"\n找到多个 Wiki 候选，请选择“{query}”对应的条目：")
    for index, candidate in enumerate(candidates, start=1):
        snippet = _plain_wiki_snippet(candidate.snippet)
        suffix = f" — {snippet}" if snippet else ""
        print(f"  {index}. {candidate.title}{suffix}")
    print("  0. 跳过 Wiki 元数据")

    while True:
        try:
            choice = input_func(f"请输入编号 [0-{len(candidates)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n未选择 Wiki 条目，跳过元数据。")
            return None

        if choice == "0":
            return None
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(candidates):
                return candidates[index - 1].title
        print("输入无效，请输入列表中的编号。")


def _plain_wiki_snippet(value: Optional[str]) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    text = " ".join(html.unescape(text).split())
    return text[:120]


def load_wiki_metadata_for_main(base_dir, wiki_url=None):
    if wiki_url:
        return load_wiki_series_for_url(base_dir, wiki_url)
    return load_exact_wiki_series_for_dir(
        base_dir,
        candidate_selector=choose_wiki_candidate,
    )


if __name__ == "__main__":
    args = parse_args()
    if args.epub:
        epub_path = os.path.abspath(args.epub)
        if not epub_path.lower().endswith(".epub") or not os.path.isfile(epub_path):
            print(f"❌ EPUB file not found: {epub_path}", file=sys.stderr)
            sys.exit(1)
        base_dir, epub_name = os.path.split(epub_path)
        epub_files = [epub_name]
    else:
        base_dir = get_base_dir()
        epub_files = sorted(f for f in os.listdir(base_dir) if f.lower().endswith(".epub"))

    if not epub_files:
        print(f"❌ No epub files found in: {base_dir}")

    wiki_series_metadata = None
    if epub_files:
        wiki_series_metadata = load_wiki_metadata_for_main(base_dir, args.wiki_url)

    failures = False
    for epub in epub_files:
        try:
            epub_to_cbz_fixed(
                os.path.join(base_dir, epub),
                wiki_series_metadata=wiki_series_metadata,
                series_title=args.series_title,
            )
        except Exception as exc:
            failures = True
            print(f"❌ EPUB conversion failed: {epub} ({exc})", file=sys.stderr)
    if failures:
        sys.exit(1)
