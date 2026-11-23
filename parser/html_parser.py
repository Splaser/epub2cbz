# parser/html_parser.py
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from bs4 import BeautifulSoup
from utils.consts import IMG_EXT
from utils.epub_utils import resolve_fs_path


_ROTATE_TAG = re.compile(r"\brotate\s*:\s*(\d+)\b", re.I)


class ComicParser(HTMLParser):
    """
    HTMLParser subclass for extracting manga/comic image paths from HTML.
    Supports <img>, <image> tags and common lazy-loading attributes.
    """

    def __init__(self):
        super().__init__()
        self.images = []

    def _extract_src_from_attrs(self, attr):
        """
        从 img / source / svg image 标签里尽量提取图片路径。
        支持 src, data-src, data-original, data-lazy-src, href, xlink:href, srcset
        """
        src = (
            attr.get("src")
            or attr.get("data-src")
            or attr.get("data-original")
            or attr.get("data-lazy-src")
            or attr.get("data-original-src")
            or attr.get("data-url")
            or attr.get("href")
            or attr.get("xlink:href")
        )

        # 兼容 <source srcset="a.webp 1x, b.webp 2x"> 或 <img srcset="a.jpg 800w, b.jpg 1600w">
        if not src and attr.get("srcset"):
            srcset = attr.get("srcset", "").strip()
            if srcset:
                first = srcset.split(",")[0].strip()
                src = first.split()[0] if first else None

        return src

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ["img", "image"]:
            return

        attr = dict(attrs)
        src = self._extract_src_from_attrs(attr)
        if not src or src.startswith("data:"):  # 排除 base64 内嵌图
            return

        rotate = _ROTATE_TAG.search(attr.get("kmoetag") or "")
        self.images.append((src, rotate is not None and rotate.group(1).lstrip("0") == "1"))


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def extract_image_references(html_path: str, epub_root: str) -> list[tuple[str, bool]]:
    """Read local image references and orientation in document order."""
    parser = ComicParser()
    with open(html_path, "r", encoding="utf-8", errors="ignore") as source:
        parser.feed(source.read())
    parser.close()

    base_dir = os.path.dirname(html_path)
    results = []
    for src, rotate in parser.images:
        img_path = resolve_fs_path(base_dir, src, epub_root)
        if img_path is None or not is_image_file(img_path):
            continue
        if not os.path.isfile(img_path):
            raise FileNotFoundError(f"Missing EPUB image {src!r} in {html_path}")
        results.append((img_path, rotate))

    return results


def extract_image_paths_from_html(html_path: str) -> list[str]:
    path = Path(html_path).resolve()
    root = next(
        (parent for parent in path.parents
         if (parent / "META-INF").is_dir() or (parent / "vol.opf").is_file()),
        path.parent,
    )
    try:
        return [image for image, _ in extract_image_references(str(path), str(root))]
    except OSError:
        return []


def extract_images_from_html(html_path: str) -> list[str]:
    """
    从 HTML 文件提取所有图片路径
    返回列表，仅包含本地图片路径（绝对或相对可处理）
    """
    if not os.path.exists(html_path):
        return []

    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")
    imgs = []

    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            # 解析相对路径
            img_path = os.path.normpath(os.path.join(os.path.dirname(html_path), src))
            imgs.append(img_path)

    return imgs
