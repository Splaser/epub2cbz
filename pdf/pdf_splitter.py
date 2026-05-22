# pdf/pdf_splitter.py
from PIL import Image
import os
from typing import List

from utils.consts import IMG_EXT

def is_probable_double_page(img_path: str, ratio_threshold=1.35) -> bool:
    try:
        with Image.open(img_path) as im:
            w, h = im.size
        return w / h >= ratio_threshold
    except Exception:
        return False

def split_page_rl(img_path: str, temp_dir: str, index: int, keep_original=False) -> List[str]:
    with Image.open(img_path) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        w, h = im.size
        mid = w // 2
        left = im.crop((0, 0, mid, h))
        right = im.crop((mid, 0, w, h))

        ext = os.path.splitext(img_path)[1].lower()
        if ext not in IMG_EXT:
            ext = ".jpg"

        right_path = os.path.join(temp_dir, f"{index:04d}_a_right{ext}")
        left_path = os.path.join(temp_dir, f"{index:04d}_b_left{ext}")

        if ext in (".jpg", ".jpeg"):
            left.convert("RGB").save(left_path, "JPEG", quality=95)
            right.convert("RGB").save(right_path, "JPEG", quality=95)
        else:
            left.save(left_path)
            right.save(right_path)

        if keep_original:
            return [img_path, right_path, left_path]
        return [right_path, left_path]

def process_images(image_paths: List[str], temp_dir: str, split_double_page=True, ratio_threshold=1.20, protect_first_n=1, protect_last_n=1) -> List[str]:
    final_images = []
    total = len(image_paths)
    for i, img in enumerate(image_paths, start=1):
        is_protected = (i <= protect_first_n) or (i > total - protect_last_n)
        if split_double_page and (not is_protected) and is_probable_double_page(img, ratio_threshold):
            parts = split_page_rl(img, temp_dir, i)
            final_images.extend(parts)
        else:
            final_images.append(img)
    return final_images