# pdf/pdf_utils.py
import os
import subprocess
from typing import List


try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None


from utils.consts import IMG_EXT

import shutil

def detect_poppler_bin() -> str | None:
    """
    自动探测 Poppler 二进制目录
    返回路径或 None
    """
    exe_name = "pdfimages.exe" if os.name == "nt" else "pdfimages"
    path = shutil.which(exe_name)
    if path:
        # 返回 exe 所在的目录
        return os.path.dirname(path)
    return None

POPPLER_BIN = detect_poppler_bin()

def clean_pdf_name(name: str) -> str:
    import re
    name = re.sub(r'\s+\d+x\d+(?:\.\d+)?\+\d+x\d+(?:\.\d+)?=\d+(?:\.\d+)?', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def list_image_files(folder: str) -> List[str]:
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(IMG_EXT)]
    files.sort()
    return files

def extract_with_pdfimages(pdf_path, temp_dir, poppler_bin=POPPLER_BIN) -> List[str]:
    exe = "pdfimages"
    if poppler_bin:
        exe = os.path.join(poppler_bin, "pdfimages.exe")
    prefix = os.path.join(temp_dir, "page")
    pdf_path = os.path.abspath(pdf_path)

    cmd = [exe, "-all", pdf_path, prefix]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return list_image_files(temp_dir)

def render_with_pdf2image(pdf_path, temp_dir, dpi=300, poppler_bin=POPPLER_BIN) -> List[str]:
    if convert_from_path is None:
        raise RuntimeError("pdf2image 未安装，且 pdfimages 提取失败。")
    pages = convert_from_path(pdf_path, dpi=dpi, fmt="jpeg", thread_count=4, poppler_path=poppler_bin)
    out = []
    for i, page in enumerate(pages, start=1):
        if page.mode != "RGB":
            page = page.convert("RGB")
        path = os.path.join(temp_dir, f"page-{i:04d}.jpg")
        page.save(path, "JPEG", quality=95)
        out.append(path)
    return out