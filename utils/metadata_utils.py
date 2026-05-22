# utils/metadata_utils.py
import os
import re
from .consts import (
    VOL_PATTERN_LIST,
    SPECIAL_KEYWORDS,
)  # 你可以把原来匹配卷/期的正则抽到 consts.py


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


def build_output_cbz_name(
    epub_path: str, series_name: str = None, is_periodical: bool = False
) -> str:
    raw_name = os.path.splitext(os.path.basename(epub_path))[0]

    # 优先提取文件名前缀 [作者][系列]
    m = re.match(r"(\[[^\]]+\])(\[[^\]]+\])", raw_name)
    if m:
        series_name = "".join(m.groups())
    else:
        series_name = series_name or os.path.basename(os.path.dirname(epub_path))

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
