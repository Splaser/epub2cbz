# utils/metadata_utils.py
import os
import re
import numpy as np
from PIL import Image
from typing import List


from .consts import (
    VOL_PATTERN_LIST,
    SPECIAL_KEYWORDS,
)



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

# utils/metadata_utils.py
def zh_to_int(text: str) -> int | None:
    """
    中文数字月份转换为整数
    支持：
    一、二、三、四、五、六、七、八、九、十、十一、十二
    """
    mapping = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
        "十一": 11,
        "十二": 12,
    }
    return mapping.get(text)


def clean_raw_name(raw_name: str) -> str:
    cleaned = raw_name
    cleaned = re.sub(r"\.kepub$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:\[[^\]]+\])+", "", cleaned).strip()
    cleaned = re.sub(r"^[^\[\]]+?\([^)]*\)", "", cleaned).strip()
    return cleaned


def extract_series_name(raw_name: str) -> str:
    """
    从文件名中提取中文系列名，删除网站/方括号信息
    例如：[Kmoe][蠟筆小新]卷01 -> 蠟筆小新
    """
    # 取第一个中文字符开头的方括号内容
    m = re.findall(r'\[([^\]]*[\u4e00-\u9fff]+[^\]]*)\]', raw_name)
    if m:
        return m[-1]  # 取最后一个包含中文的方括号
    # fallback 父目录名
    return os.path.basename(os.path.dirname(raw_name))


def build_output_cbz_name(
    epub_path: str, series_name: str = None, is_periodical: bool = False
) -> str:
    raw_name = os.path.splitext(os.path.basename(epub_path))[0]

    series_name = extract_series_name(raw_name)
    cleaned = clean_raw_name(raw_name)

    # 1) 期刊 T/D 特刊优先
    if is_periodical:
        td_match = re.match(r"^([TD])\s*(\d{1,3})(.*)$", cleaned, re.IGNORECASE)
        if td_match:
            prefix, num, tail = td_match.groups()
            prefix = prefix.upper()
            num = int(num)
            tail = (tail or "").strip()
            return f"{series_name} - {prefix}{num:02d}{tail}.cbz"

        # 1.1) 年月分册
        ym_match = re.search(r"(20\d{2})年(\d{1,2})月", cleaned)
        if ym_match:
            year, month = ym_match.groups()
            return f"{series_name} - {year}-{int(month):02d}.cbz"

        # 1.2) 月份分册 / 上下 / 特刊
        part_match = re.search(
            r"(\d{1,3})\s*([一二三四五六七八九十]{1,3})月\s*(上|下|特刊)", cleaned
        )
        if part_match:
            issue, zh_month, slot = part_match.groups()
            month = zh_to_int(zh_month)  # 你原来有 zh_month_to_int
            return f"{series_name} - 第{int(issue):03d}期 {month}月{slot}.cbz"

        # 1.5) 合刊
        multi_match = re.search(r"第\s*(\d+)[,、-~](\d+)\s*期", cleaned)
        if multi_match:
            a, b = multi_match.groups()
            return f"{series_name} - 第{int(a):03d}-{int(b):03d}期.cbz"

    # 2) 普通特刊/番外/特典/画集
    for kw in SPECIAL_KEYWORDS:
        if kw.lower() in cleaned.lower():
            return f"{series_name} - {cleaned}.cbz"

    # 3) 普通卷 / 期
    vol = None
    for p in VOL_PATTERN_LIST:  # 从 consts.py 统一抽正则
        m = re.search(p, cleaned, re.IGNORECASE)
        if m:
            vol = int(m.group(1))
            break
    if vol is not None:
        unit = "期" if is_periodical else "卷"
        return f"{series_name} - 第{vol:03d}{unit}.cbz"

    # 4) 保底
    return f"{series_name} - {cleaned}.cbz"
