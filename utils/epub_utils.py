# utils/epub_utils.py
import os
import zipfile
import posixpath
import xml.etree.ElementTree as ET
from typing import List, Tuple
import re


def extract_epub(epub_path: str, extract_dir: str):
    """解压 EPUB 到指定目录"""
    with zipfile.ZipFile(epub_path, "r") as z:
        for member in z.infolist():
            target = os.path.abspath(os.path.join(extract_dir, member.filename))
            extract_dir_abs = os.path.abspath(extract_dir)
            if not target.startswith(extract_dir_abs + os.sep):
                raise Exception(f"unsafe zip path: {member.filename}")
            z.extract(member, extract_dir)


def normalize_href(path_str: str) -> str:
    """规范化 href 路径"""
    from urllib.parse import unquote

    path_str = unquote(path_str)
    path_str = path_str.replace("\\", "/")
    path_str = path_str.split("#", 1)[0]
    return posixpath.normpath(path_str)


def resolve_fs_path(base_dir: str, rel_path: str) -> str:
    """将 href 相对路径转为本地文件路径"""
    rel_path = normalize_href(rel_path)
    return os.path.normpath(os.path.join(base_dir, *rel_path.split("/")))


def find_opf_path(extract_dir: str) -> str:
    """从 META-INF/container.xml 找到 OPF 文件路径"""
    container_path = os.path.join(extract_dir, "META-INF", "container.xml")
    if not os.path.exists(container_path):
        raise Exception("META-INF/container.xml not found")

    tree = ET.parse(container_path)
    root = tree.getroot()
    for elem in root.iter():
        if elem.tag.endswith("rootfile"):
            full_path = elem.attrib.get("full-path")
            if full_path:
                return resolve_fs_path(extract_dir, full_path)
    raise Exception("OPF not found in container.xml")


def parse_opf(opf_path: str) -> Tuple[dict, List[str], str]:
    """解析 OPF 文件，返回 manifest, spine 列表, 基础目录"""
    tree = ET.parse(opf_path)
    root = tree.getroot()
    manifest = {}
    spine = []

    for elem in root.iter():
        if elem.tag.endswith("item"):
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = {"href": href, "media_type": media_type}

    for elem in root.iter():
        if elem.tag.endswith("itemref"):
            idref = elem.attrib.get("idref")
            if idref and idref in manifest:
                spine.append(manifest[idref]["href"])

    return manifest, spine, os.path.dirname(opf_path)


def get_html_files_by_spine(temp_dir: str) -> List[str]:
    """通过 spine 顺序获取 HTML 文件列表"""
    opf_path = find_opf_path(temp_dir)
    manifest, spine, base_dir = parse_opf(opf_path)
    html_files = []
    for href in spine:
        html_path = resolve_fs_path(base_dir, href)
        if os.path.exists(html_path):
            html_files.append(html_path)
    return html_files


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
