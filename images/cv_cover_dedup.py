import cv2
import numpy as np
from PIL import Image
from typing import List


def is_rgb_color_image(img_path: str, min_saturation: float = 5.0) -> bool:
    """
    保证图片是彩色封面
    - min_saturation: HSV饱和度均值阈值
    """
    try:
        im = Image.open(img_path).convert("RGB")
        arr = np.array(im)
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        sat_mean = hsv[:, :, 1].mean()
        return sat_mean >= min_saturation
    except Exception:
        return False


def _image_stats(img_path: str) -> dict:
    im = Image.open(img_path).convert("RGB")
    arr = np.array(im)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    total = gray.size

    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

    return {
        "white": np.count_nonzero(gray >= 245) / total,
        "black": np.count_nonzero(gray <= 10) / total,
        "edge": np.count_nonzero(cv2.Canny(gray, 100, 200)) / total,
        "sat": hsv[:, :, 1].mean(),
        "val": hsv[:, :, 2].mean(),
        "std": gray.std(),
    }


def _is_text_or_catalog_like(stats: dict) -> bool:
    """
    白底 + 明显黑字/线条/边缘，倾向目录页、版权页、说明页。
    这类页面即使直方图像封面/白页，也绝不能被静默去重。
    """
    return (
        stats["white"] < 0.96
        or stats["black"] >= 0.008
        or stats["edge"] >= 0.012
        or stats["std"] >= 28
    )


def dedupe_cover_images_cv(
    image_paths: List[str], similarity_threshold: float = 0.95
) -> List[str]:
    """
    CV 封面去重，仅依赖 PIL + OpenCV。

    安全策略：
    - 只允许对“封面候选”去重
    - 疑似目录/正文/说明页直接保留
    - 所有 drop 都打印日志，避免静默吞页
    """
    if not image_paths:
        return []

    retained = []
    histograms = []

    for idx, path in enumerate(image_paths):
        try:
            stats = _image_stats(path)
        except Exception as e:
            print(f"  - keep [cover-dedupe:error {e}] {path}")
            retained.append(path)
            continue

        # 第一张永远保留
        if idx == 0:
            retained.append(path)

            img = Image.open(path).convert("L")
            arr = np.array(img)
            hist = cv2.calcHist([arr], [0], None, [256], [0, 256])
            histograms.append(cv2.normalize(hist, hist).flatten())

            print(
                f"  - keep [cover-dedupe:first "
                f"white={stats['white']:.3f} black={stats['black']:.3f} "
                f"edge={stats['edge']:.3f} sat={stats['sat']:.1f}] "
                f"{path}"
            )
            continue

        # 疑似目录/文字页：禁止 CV 去重
        if _is_text_or_catalog_like(stats):
            retained.append(path)
            print(
                f"  - keep [cover-dedupe:catalog-protect "
                f"white={stats['white']:.3f} black={stats['black']:.3f} "
                f"edge={stats['edge']:.3f} std={stats['std']:.1f}] "
                f"{path}"
            )
            continue

        img = Image.open(path).convert("L")
        arr = np.array(img)
        hist_curr = cv2.calcHist([arr], [0], None, [256], [0, 256])
        hist_curr = cv2.normalize(hist_curr, hist_curr).flatten()

        duplicate_sim = None
        for h in histograms:
            sim = cv2.compareHist(h, hist_curr, cv2.HISTCMP_CORREL)
            if sim >= similarity_threshold:
                duplicate_sim = sim
                break

        if duplicate_sim is not None:
            print(
                f"  - skip [cover-dedupe:duplicate sim={duplicate_sim:.3f} "
                f"white={stats['white']:.3f} black={stats['black']:.3f} "
                f"edge={stats['edge']:.3f}] "
                f"{path}"
            )
            continue

        retained.append(path)
        histograms.append(hist_curr)
        print(
            f"  - keep [cover-dedupe:unique "
            f"white={stats['white']:.3f} black={stats['black']:.3f} "
            f"edge={stats['edge']:.3f} sat={stats['sat']:.1f}] "
            f"{path}"
        )

    return retained
