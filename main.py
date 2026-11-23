import argparse
from collections import Counter
from filecmp import cmp
from hashlib import sha256
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
from utils.epub_utils import extract_epub, get_html_files_by_spine, fallback_all_images, read_epub_credit_fields
from utils.metadata_utils import build_output_cbz_name, group_epub_volumes, split_volume_part


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


def volume_output_name(epubs: tuple[str, ...], series_title: str | None = None) -> str:
    if series_title is not None:
        series_title = series_title.strip()
        if not series_title or re.search(r'[<>:"/\\|?*\x00-\x1f]', series_title):
            raise ValueError("Series title must be a valid filename prefix")
    epub_path = epubs[0]
    part = split_volume_part(epub_path)
    if part is None:
        return build_output_cbz_name(epub_path, series_name=series_title)
    stem, side = part
    base_epub = os.path.join(os.path.dirname(epub_path), stem + ".epub")
    output_name = build_output_cbz_name(base_epub, series_name=series_title)
    if len(epubs) == 1:
        return f"{os.path.splitext(output_name)[0]}（{side}）.cbz"
    return output_name


def prepare_epub_pages(epub_path: str, work_dir: str) -> tuple[list[str], str | None, str | None]:
    epub_root = os.path.join(work_dir, "epub")
    rotated_dir = os.path.join(work_dir, "rotated")
    os.makedirs(epub_root)
    os.mkdir(rotated_dir)
    extract_epub(epub_path, epub_root)
    pages = collect_epub_pages(epub_root)
    if not pages:
        raise ValueError(f"EPUB has no image pages: {epub_path}")
    images = [prepare_epub_page(path, rotated_dir, rotate=rotate) for path, rotate in pages]
    writer, publisher = read_epub_credit_fields(epub_root)
    return images, writer, publisher


def page_digest(path: str) -> bytes:
    digest = sha256()
    with open(path, "rb") as image:
        for chunk in iter(lambda: image.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def merge_split_volume_pages(upper: list[str], lower: list[str]) -> list[str]:
    # The Kmoe end card belongs at the end of the combined volume.
    if (
        all(os.path.splitext(os.path.basename(pages[-1]))[0].lower() == "theendinfo" for pages in (upper, lower))
        and cmp(upper[-1], lower[-1], shallow=False)
    ):
        upper = upper[:-1]
    if upper and cmp(upper[0], lower[0], shallow=False):
        lower = lower[1:]

    # Look for an exact suffix/prefix match at the join. Limit comparison to
    # nearby pages, since a repeated image elsewhere can be intentional.
    window = min(16, len(upper), len(lower))
    if window:
        ending = [page_digest(path) for path in upper[-window:]]
        opening = [page_digest(path) for path in lower[:window]]
        for overlap in range(window, 0, -1):
            if ending[-overlap:] == opening[:overlap]:
                lower = lower[overlap:]
                break
    return upper + lower


def convert_epub_volume(epubs: tuple[str, ...], wiki_series_metadata=None, *, series_title=None, publisher=None):
    epub_path = epubs[0]
    output_name = volume_output_name(epubs, series_title)
    if series_title is not None:
        series_title = series_title.strip()
    output_cbz = os.path.join(os.path.dirname(epub_path), output_name)
    with tempfile.TemporaryDirectory(prefix="epub2cbz_") as temp_dir:
        final_images, writer, epub_publisher = prepare_epub_pages(epub_path, os.path.join(temp_dir, "first"))
        if len(epubs) == 2:
            lower, lower_writer, lower_publisher = prepare_epub_pages(epubs[1], os.path.join(temp_dir, "second"))
            writer = writer or lower_writer
            epub_publisher = epub_publisher or lower_publisher
            original_count = len(final_images) + len(lower)
            final_images = merge_split_volume_pages(final_images, lower)
            print(f"  - Removed {original_count - len(final_images)} duplicate pages", flush=True)

        comicinfo_xml = build_comicinfo_xml_for_epub(
            epub_path=epub_path,
            output_cbz_name=output_name,
            page_count=len(final_images),
            wiki_series=wiki_series_metadata,
            series_title=series_title,
            keep_local_index=len(epubs) == 2,
            epub_writer=writer,
            epub_publisher=epub_publisher,
            publisher_override=publisher,
        )

        make_cbz(final_images, output_cbz, comicinfo_xml=comicinfo_xml)
        print(f"✅ CBZ created: {output_cbz}, total pages: {len(final_images)}", flush=True)


def epub_to_cbz_fixed(epub_path, wiki_series_metadata=None, *, series_title=None):
    convert_epub_volume((os.path.abspath(epub_path),), wiki_series_metadata, series_title=series_title)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser(description="Convert one EPUB or scan the executable's directory for EPUBs.")
    parser.add_argument("epub", nargs="?", help="Convert this EPUB and its matching upper/lower part, if present.")
    parser.add_argument("--series-title", help="Use this series name for the CBZ filename and ComicInfo.")
    parser.add_argument("--publisher", help="Use this publisher in ComicInfo.")
    wiki_options = parser.add_mutually_exclusive_group()
    wiki_options.add_argument("--no-wiki", action="store_true", help="Use local metadata without querying Wiki.")
    wiki_options.add_argument(
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


def main():
    args = parse_args()
    epub_path = None
    if args.epub:
        epub_path = os.path.abspath(args.epub)
        if not epub_path.lower().endswith(".epub") or not os.path.isfile(epub_path):
            print(f"❌ EPUB file not found: {epub_path}", file=sys.stderr)
            sys.exit(1)
        base_dir = os.path.dirname(epub_path)
    else:
        base_dir = get_base_dir()

    epub_files = [
        entry.path for entry in os.scandir(base_dir)
        if entry.name.lower().endswith(".epub") and entry.is_file()
    ]
    if epub_path and epub_path not in epub_files:
        # The caller can use a different spelling on a case-insensitive volume.
        epub_path = next(
            (path for path in epub_files if os.path.samefile(path, epub_path)), epub_path
        )
        if epub_path not in epub_files:
            epub_files.append(epub_path)
    volumes = group_epub_volumes(epub_files)
    if epub_path:
        volumes = [volume for volume in volumes if epub_path in volume]
    if not volumes:
        print(f"❌ No epub files found in: {base_dir}")
        return 0

    try:
        output_names = [volume_output_name(volume, args.series_title) for volume in volumes]
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    counts = Counter(name.casefold() for name in output_names)
    wiki_series_metadata = None
    if not args.no_wiki:
        print(f"Looking up Wiki metadata for {os.path.basename(base_dir)}...", flush=True)
        wiki_series_metadata = load_wiki_metadata_for_main(base_dir, args.wiki_url)

    failures = False
    for volume, output_name in zip(volumes, output_names):
        source_names = " + ".join(os.path.basename(path) for path in volume)
        if counts[output_name.casefold()] > 1:
            failures = True
            print(f"❌ Multiple inputs would write {output_name}: {source_names}", file=sys.stderr)
            continue
        try:
            print(f"{'Merging' if len(volume) == 2 else 'Converting'} {source_names}", flush=True)
            convert_epub_volume(
                volume,
                wiki_series_metadata=wiki_series_metadata,
                series_title=args.series_title,
                publisher=(args.publisher or "").strip() or None,
            )
        except Exception as exc:
            failures = True
            print(f"❌ EPUB conversion failed: {source_names} ({exc})", file=sys.stderr)
    return int(failures)


if __name__ == "__main__":
    sys.exit(main())
