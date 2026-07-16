# pdf/pdf_to_cbz.py
import os
import tempfile
import shutil
from builder.cbz_builder import make_cbz
from images.filter import filter_image_files
from .pdf_utils import build_pdf_output_cbz_name, extract_or_render_with_pymupdf


def pdf_to_cbz(pdf_path: str):
    temp_dir = tempfile.mkdtemp(prefix="pdf2cbz_")
    try:
        # 优先无损提取铺满整页的 JPEG，复杂页面回退为逐页渲染。
        image_paths = extract_or_render_with_pymupdf(pdf_path, temp_dir, dpi=300)
        if not image_paths:
            print(f"❌ no pages extracted: {pdf_path}")
            return

        # 过滤垃圾页
        filtered_images = filter_image_files(image_paths)

        # 打包 CBZ
        output_cbz = os.path.join(
            os.path.dirname(pdf_path),
            build_pdf_output_cbz_name(pdf_path),
        )
        make_cbz(filtered_images, output_cbz)
        print(f"✅ PDF to CBZ done: {output_cbz} [{len(filtered_images)} pages]")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
