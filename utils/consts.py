# utils/consts.py

# 支持的图片扩展名
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")

# HTML / 尾页 / 广告关键字
BAD_KEYWORDS_COMMON = {
    "createby",
    "createinfo",
    "endinfo",
    "theendinfo",
    "mox",
    "kox",
    "wnacg",
    "18comic",
    "manhuagui",
}

BAD_KEYWORDS_HTML_EXTRA = {
    "powered",
    "dmzj",
    "mhx12",
}

BAD_KEYWORDS_CONTENT_EXTRA = {
    "mox.moe",
    "koz",
    "mhx12.com",
    "最新地址",
    "最新域名",
    "收藏本站",
    "加入书签",
    "在线阅读",
    "版权归原作者所有",
}

TAIL_AD_KEYWORDS = [
    "mox",
    "kox",
    "18comic",
    "wnacg",
    "manhuagui",
    "koz",
    "最新地址",
    "最新域名",
    "收藏本站",
    "加入书签",
    "在线阅读",
    "在線閱讀",
    "版权归原作者所有",
    "版權歸原作者所有",
]

SPECIAL_KEYWORDS = [
    "原画集", "頁集", "设定集", "公式书",    
    "画集", "插画集", "黑板报", "after10days", "番外", "外传", "特典",
    "附录", "短篇", "特別篇", "特刊", "内幕集锦", "人物特写", "秘密章节", "元素分析", "名言集"
]

VOL_PATTERN_LIST = {
    r'第\s*(\d+)\s*[卷期]',      # 第01卷 / 第01期
    r'[卷期][_\-\s]*(\d+)',     # 卷01 / 期01
    r'(\d{1,4})\s*期',          # 01期 / 1997年01期
    r'^\s*(\d{1,4})(?=\D)',     # 001xxx
    r'\bv(?:ol)?[_\-\s]*(\d+)\b',
    r'(\d+)$',
}


# 拆页/旋转相关
ROTATE_VERTICAL_SPLIT_PAGE = True
ROTATE_DEGREE = -90
ENABLE_SPLIT_WIDE = True