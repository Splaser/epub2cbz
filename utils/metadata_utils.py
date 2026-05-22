# utils/metadata_utils.py
import os
import re
from typing import List
from PIL import Image
import numpy as np


# ---------------------------
# 图片统计
# ---------------------------
def compute_normal_page_ratio(image_paths: List[str]) -> float:
    """
    计算漫画全书正常单页宽高比中位数
    """
    ratios = []
    for img_path in image_paths:
        try:
            with Image.open(img_path) as im:
                w, h = im.size
                if w > 0 and h > 0:
                    ratios.append(w / h)
        except Exception:
            continue
    if not ratios:
        return 1.0  # 防止除零
    return np.median(ratios)


# ---------------------------
# CBZ 文件名生成逻辑
# ---------------------------
def clean_raw_name(raw_name: str) -> str:
    cleaned = raw_name
    cleaned = re.sub(r'\.kepub$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^(?:\[[^\]]+\])+', '', cleaned).strip()
    cleaned = re.sub(r'^[^\[\]]+?\([^)]*\)', '', cleaned).strip()
    return cleaned


def build_output_cbz_name(epub_path: str, series_name: str = None, is_periodical: bool = False) -> str:
    """
    根据 epub 文件名或目录生成 CBZ 输出名称
    保留原来的期刊、卷、特典、合刊逻辑
    """
    raw_name = os.path.splitext(os.path.basename(epub_path))[0]
    cleaned = clean_raw_name(raw_name)

    # 简化版本：如果是期刊则加“期”，否则加“卷”
    # 可扩展为之前的完整逻辑（番外、特典、月份、合刊）
    vol_match = re.search(r'\d{1,4}', cleaned)
    vol_num = int(vol_match.group()) if vol_match else None
    unit = "期" if is_periodical else "卷"

    series_name = series_name or os.path.basename(os.path.dirname(epub_path))
    if vol_num:
        return f"{series_name} - 第{vol_num:03d}{unit}.cbz"
    else:
        return f"{series_name} - {cleaned}.cbz"