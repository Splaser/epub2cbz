# utils/epub_utils.py
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List
import re
from urllib.parse import unquote, urlsplit


def extract_epub(epub_path: str, extract_dir: str):
    """解压 EPUB 到指定目录"""
    with zipfile.ZipFile(epub_path, "r") as z:
        for member in z.infolist():
            _resolve_inside_epub(extract_dir, member.filename, extract_dir)
            z.extract(member, extract_dir)


def _resolve_inside_epub(base_dir: str, path: str, epub_root: str) -> str:
    path = path.replace("\\", "/")
    root = os.path.realpath(epub_root)
    if path.startswith("/") or ":" in path or "\x00" in path:
        raise ValueError(f"Unsafe EPUB path: {path}")
    target = os.path.realpath(os.path.join(base_dir, path))
    if os.path.commonpath((root, target)) != root:
        raise ValueError(f"Path leaves the EPUB directory: {path}")
    return target


def resolve_fs_path(base_dir: str, href: str, epub_root: str) -> str | None:
    """Resolve a local EPUB URL, or return None for an external resource."""
    if re.match(r"^[a-z]:", href, flags=re.I):
        raise ValueError(f"Unsafe EPUB path: {href}")
    url = urlsplit(href.replace("\\", "/"))
    if url.scheme or url.netloc or not url.path:
        return None
    return _resolve_inside_epub(base_dir, unquote(url.path), epub_root)


def find_opf_path(extract_dir: str) -> str:
    """从 META-INF/container.xml 找到 OPF 文件路径"""
    container_path = os.path.join(extract_dir, "META-INF", "container.xml")
    if not os.path.isfile(container_path):
        legacy_opf = os.path.join(extract_dir, "vol.opf")
        if os.path.isfile(legacy_opf):
            return legacy_opf
        raise FileNotFoundError("EPUB has no META-INF/container.xml or vol.opf")

    tree = ET.parse(container_path)
    root = tree.getroot()
    for elem in root.iter():
        if elem.tag.endswith("rootfile"):
            full_path = elem.attrib.get("full-path")
            if full_path:
                opf_path = resolve_fs_path(extract_dir, full_path, extract_dir)
                if not opf_path or not os.path.isfile(opf_path):
                    raise FileNotFoundError(f"OPF not found in EPUB: {full_path}")
                return opf_path
    raise ValueError("OPF not found in container.xml")


def parse_opf(opf_path: str, epub_root: str):
    tree = ET.parse(opf_path)
    root = tree.getroot()
    manifest = {}

    # 先解析 manifest
    for elem in root.iter():
        if elem.tag.endswith("item"):
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = {
                    "href": href,
                    "media_type": media_type,
                    "local_path": resolve_fs_path(os.path.dirname(opf_path), href, epub_root)
                }

    # 再解析 spine
    spine = []
    for elem in root.iter():
        if elem.tag.endswith("itemref"):
            idref = elem.attrib.get("idref")
            if idref not in manifest:
                raise ValueError(f"Missing OPF manifest item for spine entry: {idref}")
            item = manifest[idref]
            if not item["local_path"] or not os.path.isfile(item["local_path"]):
                raise FileNotFoundError(f"Missing EPUB spine file: {item['href']}")
            spine.append(item)

    return manifest, spine, os.path.dirname(opf_path)


# spine_dicts[i] = {"id": ..., "href": ..., "media_type": ..., "local_path": ...}
def get_html_files_by_spine(temp_dir: str):
    opf_path = find_opf_path(temp_dir)
    _, spine, _ = parse_opf(opf_path, temp_dir)
    return [item["local_path"] for item in spine], spine


def get_html_files_by_dir_fallback(temp_dir: str) -> List[str]:
    """目录遍历 fallback 获取 HTML 文件"""
    html_candidates = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower().endswith((".html", ".htm", ".xhtml")):
                html_candidates.append(os.path.join(root, f))
    html_candidates.sort(
        key=lambda p: [
            int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", os.path.relpath(p, temp_dir))
        ]
    )
    return html_candidates


def fallback_all_images(temp_dir: str) -> List[str]:
    """目录遍历 fallback 获取所有图片"""
    from utils.consts import IMG_EXT

    images = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower().endswith(IMG_EXT):
                images.append(os.path.join(root, f))
    images.sort(
        key=lambda p: [
            int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", os.path.relpath(p, temp_dir))
        ]
    )
    return images
