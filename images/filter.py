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
    return path.lower().endswith(tuple(IMG_EXT))


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


def get_garbage_image_reason(img_path: str, val_mean_threshold=250) -> str | None:
    """
    低门槛垃圾页检测：
    - 高白、低边缘、亮度接近最大值
    - 可针对首几页广告/空白页使用
    """
    try:
        size_kb = os.path.getsize(img_path) / 1024
        im = Image.open(img_path).convert("RGB")
        arr = np.array(im)

        # 灰度
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        total = gray.size
        near_white_ratio = np.count_nonzero(gray >= 245) / total
        edge_density = np.count_nonzero(cv2.Canny(gray, 100, 200)) / total
        val_mean = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)[:, :, 2].mean()

    except Exception:
        return None

    # 原有极端垃圾页规则（保留）
    if near_white_ratio > 0.995 and size_kb < 60 and edge_density < 0.002:
        return f"small-extreme-white size={size_kb:.1f}KB white={near_white_ratio:.3f} edge={edge_density:.3f}"

    # **针对第三张广告页**
    # 条件：白度 >0.98, 边缘密度低, 文件小于120KB, 明度均值接近最大
    if near_white_ratio > 0.98 and edge_density < 0.01 and size_kb < 140 and val_mean > val_mean_threshold:
        return f"frontpage-ad size={size_kb:.1f}KB white={near_white_ratio:.3f} edge={edge_density:.3f} val_mean={val_mean:.1f}"

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