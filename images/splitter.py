# images/splitter.py
import os
from typing import List
from PIL import Image
from utils.consts import ROTATE_DEGREE, ROTATE_VERTICAL_SPLIT_PAGE, ENABLE_SPLIT_WIDE, IMG_EXT

def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def save_image_part(im: Image.Image, path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".jpg", ".jpeg"] and im.mode not in ["RGB", "L"]:
        im = im.convert("RGB")
    im.save(path)


def rotate_if_landscape(im: Image.Image) -> Image.Image:
    w, h = im.size
    if w > h * 1.10:
        return im.rotate(ROTATE_DEGREE, expand=True)
    return im


def split_wide_image_if_needed(img_path: str, out_dir: str, normal_ratio: float = 1.0, enable_split: bool = ENABLE_SPLIT_WIDE) -> List[str]:
    """
    对单张漫画图片拆分：
    - 横置跨页拆成左右两页
    - 上下堆叠拆成上下两页
    - 末页/版权页保护
    """
    if not enable_split:
        return [img_path]

    name_lower = os.path.basename(img_path).lower()
    skip_keywords = ["end", "ad", "ads", "adv", "advertisement", "copyright", "backcover", "afterword"]
    if any(k in name_lower for k in skip_keywords):
        return [img_path]  # 尾页/版权页保护

    try:
        with Image.open(img_path) as im:
            w, h = im.size
            base = os.path.splitext(os.path.basename(img_path))[0]
            ext = os.path.splitext(img_path)[1].lower()


            # 横向拆分
            if w / h >= 1.35:
                if h > w:  # 纵图横置情况
                    im = im.rotate(ROTATE_DEGREE, expand=True)
                    w, h = im.size

                left = im.crop((0, 0, w//2, h))
                right = im.crop((w//2, 0, w, h))
                left_path = os.path.join(out_dir, f"{base}__L{ext}")
                right_path = os.path.join(out_dir, f"{base}__R{ext}")
                save_image_part(left, left_path)
                save_image_part(right, right_path)
                print(f"  - split [wide-LR] {base} {w}x{h}")
                return [right_path, left_path]
            
            # 上下堆叠拆分：高度必须比宽度大至少2.0倍，并且宽度大于某个最小阈值（可选）
            if h / w >= 2.0 and w >= 400:
                top = im.crop((0, 0, w, h//2))
                bottom = im.crop((0, h//2, w, h))
                if ROTATE_VERTICAL_SPLIT_PAGE:
                    top = rotate_if_landscape(top)
                    bottom = rotate_if_landscape(bottom)
                top_path = os.path.join(out_dir, f"{base}__TOP{ext}")
                bottom_path = os.path.join(out_dir, f"{base}__BOTTOM{ext}")
                save_image_part(top, top_path)
                save_image_part(bottom, bottom_path)
                print(f"  - split [vertical-TB] {base} {w}x{h}")
                return [top_path, bottom_path]

            return [img_path]

    except Exception as e:
        print(f"  - split failed [{base}]: {e}")
        return [img_path]


def split_images_if_needed(image_paths: List[str], out_dir: str, normal_ratio: float = 1.0) -> List[str]:
    """
    批量拆分图片
    """
    split_images = []
    for img in image_paths:
        if is_image_file(img):
            split_images.extend(split_wide_image_if_needed(img, out_dir, normal_ratio=normal_ratio))
        else:
            split_images.append(img)
    return split_images