# images/filter.py
import os
from typing import List
from PIL import Image
import numpy as np
import cv2
from images.cv_cover_dedup import dedupe_cover_images_cv, is_rgb_color_image

from parser.html_parser import extract_image_paths_from_html
from utils.consts import (
    IMG_EXT,
    BAD_KEYWORDS_COMMON,
    BAD_KEYWORDS_HTML_EXTRA,
    BAD_KEYWORDS_CONTENT_EXTRA,
    TAIL_AD_KEYWORDS,

)


def log_skip(reason, path):
    print(f"  - skip [{reason}] {os.path.basename(path)}")


def should_skip_html_by_name(html_path: str) -> bool:
    """根据 HTML 文件名判断是否跳过（尾页、广告页）"""
    name = os.path.basename(html_path).lower()
    stem = os.path.splitext(name)[0]

    exact_bad_names = {
        "end",
        "ad",
        "ads",
        "adv",
        "advertisement",
        "copyright",
        "about",
        "source",
        "credits",
        "colophon",
        "backcover",
        "afterword",
    }
    if stem in exact_bad_names:
        return True

    bad_parts = BAD_KEYWORDS_COMMON | BAD_KEYWORDS_HTML_EXTRA
    return any(part in name for part in bad_parts)


def should_skip_html_by_content(html_path: str) -> bool:
    """根据 HTML 内容判断是否跳过（广告、免责声明等）"""
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return False

    content_lower = content.lower()
    bad_keywords = BAD_KEYWORDS_COMMON | BAD_KEYWORDS_CONTENT_EXTRA
    hit_count = sum(1 for kw in bad_keywords if kw.lower() in content_lower)

    return hit_count >= 1


def is_probable_cover_html(html_path: str) -> bool:
    """判断是否可能是封面类 HTML 页面"""
    name = os.path.basename(html_path).lower()
    return any(k in name for k in ["cover", "封面", "frontcover", "backcover"])


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def dedupe_keep_order(items: List[str]) -> List[str]:
    """去重但保持顺序"""
    seen = set()
    out = []
    for x in items:
        norm = os.path.normcase(os.path.normpath(x))
        if norm not in seen:
            seen.add(norm)
            out.append(x)
    return out


def get_garbage_image_reason(img_path: str) -> str | None:
    """
    判断图片是否为垃圾页
    改进：
    - 极高白色比例 (>0.995) + 极小尺寸(<60KB) 才跳过
    - 边缘密度低 (<0.002) 进一步确认极空白页
    - 保留白色比例高但有内容/角色页
    """
    name = os.path.basename(img_path).lower()

    # 文件名关键字直接跳过
    for k in BAD_KEYWORDS_COMMON:
        if k in name:
            return f"name-keyword:{k}"

    try:
        size_kb = os.path.getsize(img_path) / 1024
    except Exception:
        return None

    try:
        with Image.open(img_path) as im:
            w, h = im.size
            if w <= 0 or h <= 0:
                return None

            im_gray = im.convert("L")
            im_gray.thumbnail((256, 256), Image.Resampling.BILINEAR)
            arr = np.asarray(im_gray)
            total = arr.size
            if total == 0:
                return None

            near_white_ratio = np.count_nonzero(arr >= 245) / total
            near_black_ratio = np.count_nonzero(arr <= 10) / total

            # 边缘密度
            edges = cv2.Canny(arr, 100, 200)
            edge_density = np.count_nonzero(edges) / total

    except Exception:
        return None

    # 黑页保护
    if near_black_ratio > 0.90:
        return None

    # 改进的垃圾页规则
    if near_white_ratio > 0.995 and size_kb < 60 and edge_density < 0.002:
        return f"small-extreme-white size={size_kb:.1f}KB white={near_white_ratio:.3f} edge={edge_density:.3f}"

    # 保留其他白色比例高的过渡页（edge_density >= 0.002 或体积较大）
    return None


def filter_image_files(image_paths: List[str]) -> List[str]:
    """过滤图片文件列表，去掉垃圾页并去重"""
    filtered = []
    for img in image_paths:
        reason = get_garbage_image_reason(img)
        if reason:
            try:
                size_kb = os.path.getsize(img) // 1024
            except Exception:
                size_kb = -1
            print(
                f"  - skip [garbage-image:{reason}] {os.path.basename(img)} ({size_kb}KB)"
            )
            continue
        filtered.append(img)

    return dedupe_keep_order(filtered)


def filter_html_files(html_files: List[str]) -> List[str]:
    """
    过滤 HTML 文件列表：
    - 去掉广告页 / 尾页
    - 前 2–4 页封面 CV 去重 + 保底彩色封面
    - 保证返回列表只包含图片路径
    """
    if not html_files:
        return []

    # 强制所有元素都是字符串
    html_files = [h[0] if isinstance(h, tuple) else h for h in html_files]

    # 记录结果
    filtered = []
    cover_candidates = []

    # 遍历 spine HTML
    for idx, html_path in enumerate(html_files):
        is_last_html = idx == len(html_files) - 1
        stem = os.path.splitext(html_path)[0].lower()

        # 文件名秒杀
        if should_skip_html_by_name(html_path):
            log_skip("html-name", html_path)
            continue
        # HTML 内容秒杀
        if should_skip_html_by_content(html_path):
            log_skip("html-content", html_path)
            continue

        # 最后一页尾页关键字秒杀
        if is_last_html:
            try:
                with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                    last_content = f.read().lower()
            except Exception:
                last_content = ""
            tail_hit = next((k for k in TAIL_AD_KEYWORDS if k.lower() in last_content), None)
            if tail_hit or stem in {"end", "ad", "ads", "adv"}:
                log_skip(f"last-html-tail:{tail_hit}", html_path)
                continue

        # 前 2–4 页候选封面 → 提取对应图片
        if idx < 4:
            imgs = extract_image_paths_from_html(html_path)
            for img_path in imgs:
                if isinstance(img_path, tuple):
                    img_path = img_path[0]
                if is_image_file(img_path):
                    cover_candidates.append(img_path)
        else:
            # 后续 HTML 对应的图片加入 filtered
            imgs = extract_image_paths_from_html(html_path)
            for img_path in imgs:
                if isinstance(img_path, tuple):
                    img_path = img_path[0]
                if is_image_file(img_path):
                    filtered.append(img_path)

  
    cover_candidates = [p[0] if isinstance(p, tuple) else p for p in cover_candidates]
    unique_covers = dedupe_cover_images_cv(cover_candidates, similarity_threshold=0.95)
    unique_covers = [p[0] if isinstance(p, tuple) else p for p in unique_covers]

    # 彩色保底
    if not any(is_rgb_color_image(p) for p in unique_covers):
        for p in cover_candidates:
            p = p[0] if isinstance(p, tuple) else p
            if is_rgb_color_image(p):
                unique_covers.append(p)
                break

    # 合并最终列表，保证都是图片路径
    final_images = unique_covers + filtered
    final_images = [p[0] if isinstance(p, tuple) else p for p in final_images]
    final_images = [p for p in final_images if is_image_file(p)]

    return final_images