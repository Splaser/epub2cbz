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
        sat_mean = hsv[:,:,1].mean()
        return sat_mean >= min_saturation
    except Exception:
        return False
    

def dedupe_cover_images_cv(
    image_paths: List[str], similarity_threshold: float = 0.95
) -> List[str]:
    """
    CV 封面去重，仅依赖 PIL + OpenCV
    - similarity_threshold: 判定重复的灰度直方图相关系数阈值
    """
    if not image_paths:
        return []

    retained = [image_paths[0]]
    histograms = []

    # 第一张封面
    img = Image.open(retained[0]).convert("L")


    arr = np.array(img)
    hist = cv2.calcHist([arr], [0], None, [256], [0, 256])
    histograms.append(cv2.normalize(hist, hist).flatten())

    for path in image_paths[1:]:
        img = Image.open(path).convert("L")
        
        # print(f"[DEBUG] dedupe img type={type(img)}, value={img}")

        arr = np.array(img)
        hist_curr = cv2.calcHist([arr], [0], None, [256], [0, 256])
        hist_curr = cv2.normalize(hist_curr, hist_curr).flatten()

        is_duplicate = False
        for h in histograms:
            sim = cv2.compareHist(h, hist_curr, cv2.HISTCMP_CORREL)
            if sim >= similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            retained.append(path)
            histograms.append(hist_curr)

    return retained
