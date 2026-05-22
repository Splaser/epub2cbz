# builder/cbz_builder.py
import os
import zipfile
from typing import List
from utils.consts import IMG_EXT


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def make_cbz(image_paths: List[str], output_cbz: str):
    """
    将图片列表打包成 CBZ 文件
    - image_paths: 已排序的图片路径列表
    - output_cbz: 输出 CBZ 文件路径
    """
    with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_STORED) as z:
        for i, img in enumerate(image_paths, start=1):
            ext = os.path.splitext(img)[1].lower()
            if ext not in IMG_EXT:
                ext = ".jpg"
            arcname = f"{i:04d}{ext}"
            z.write(img, arcname)
