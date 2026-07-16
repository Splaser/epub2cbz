# pdf/pdf_to_cbz.py
import os
import io
import tempfile
import shutil
import zipfile
from PIL import Image
from builder.cbz_builder import make_cbz
from metadata.pdf_comicinfo import build_comicinfo_xml_for_pdf
from .pdf_frontmatter_filter import filter_leading_disclaimer_pages
from .pdf_utils import (
    build_pdf_output_cbz_name,
    extract_or_render_with_pymupdf,
    image_is_nearly_white,
)


def _cbz_cover_is_nearly_white(cbz_path: str) -> bool:
    try:
        with zipfile.ZipFile(cbz_path) as cbz:
            image_names = sorted(
                name for name in cbz.namelist()
                if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            )
            if not image_names:
                return True
            with Image.open(io.BytesIO(cbz.read(image_names[0]))) as cover:
                return image_is_nearly_white(cover)
    except (OSError, zipfile.BadZipFile, KeyError):
        return True


def pdf_to_cbz(pdf_path: str, *, force: bool = False):
    output_name = build_pdf_output_cbz_name(pdf_path)
    output_cbz = os.path.join(os.path.dirname(pdf_path), output_name)
    if os.path.isfile(output_cbz) and not force:
        if _cbz_cover_is_nearly_white(output_cbz):
            print(f"REBUILD: existing CBZ has a blank/invalid cover: {output_cbz}")
        else:
            print(f"SKIP: CBZ already exists: {output_cbz}")
            return

    temp_dir = tempfile.mkdtemp(prefix="pdf2cbz_")
    try:
        # 优先无损提取铺满整页的 JPEG，复杂页面回退为逐页渲染。
        image_paths = extract_or_render_with_pymupdf(pdf_path, temp_dir, dpi=300)
        if not image_paths:
            print(f"ERROR: no pages extracted: {pdf_path}")
            return

        # PDF 不执行全书 OpenCV 垃圾页扫描，只检查开头连续的免责声明页。
        filtered_images = filter_leading_disclaimer_pages(image_paths, max_pages=3)

        # 打包 CBZ
        comicinfo_xml = build_comicinfo_xml_for_pdf(
            pdf_path=pdf_path,
            output_cbz_name=output_name,
            page_count=len(filtered_images),
        )
        make_cbz(filtered_images, output_cbz, comicinfo_xml=comicinfo_xml)
        print(f"PDF to CBZ done: {output_cbz} [{len(filtered_images)} pages]")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
