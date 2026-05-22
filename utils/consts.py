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

# 拆页/旋转相关
ROTATE_VERTICAL_SPLIT_PAGE = True
ROTATE_DEGREE = -90
ENABLE_SPLIT_WIDE = True