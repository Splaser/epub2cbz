# parser/html_parser.py
import os
import posixpath
from html.parser import HTMLParser
from urllib.parse import unquote
from typing import List
from bs4 import BeautifulSoup
from utils.consts import IMG_EXT


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

        cls = attr.get("class", "")
        if cls in ["singlePage", "twoPage", "imgl", "tl", "imgr", "tr", "bl", "br"]:
            self.images.append(src)
        else:
            self.images.append(src)  # 没 class 也收，避免漏页


def normalize_href(path_str: str) -> str:
    """Normalize URL/HTML href to filesystem-friendly relative path"""
    path_str = unquote(path_str)
    path_str = path_str.replace("\\", "/")
    path_str = path_str.split("#", 1)[0]
    return posixpath.normpath(path_str)


def resolve_fs_path(base_dir: str, rel_path: str) -> str:
    """Convert href relative to HTML base_dir into local filesystem path"""
    rel_path = normalize_href(rel_path)
    return os.path.normpath(os.path.join(base_dir, *rel_path.split("/")))


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def extract_image_paths_from_html(html_path: str) -> List[str]:
    """
    从单个 HTML 文件抽取漫画图片路径
    返回本地存在的图片文件列表
    """
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return []

    parser = ComicParser()
    parser.feed(content)

    base_dir = os.path.dirname(html_path)
    results = []
    for src in parser.images:
        img_path = resolve_fs_path(base_dir, src)
        if os.path.exists(img_path) and is_image_file(img_path):
            results.append(img_path)

    return results




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