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
    "原画集", "原畫集", "頁集", "设定集", "設定集", "公式书", "公式書",
    "短篇集", "画集", "畫集", "画册", "畫冊", "插画集", "插畫集",
    "黑板报", "黑板報", "after10days", "番外", "外传", "外傳", "特典",
    "附录", "附錄", "短篇", "特別篇", "特别篇", "特刊", "秘笈", "秘籍",
    "内幕集锦", "內幕集錦", "人物特写", "人物特寫", "秘密章节", "秘密章節",
    "元素分析", "名言集", "纪念", "紀念",
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
