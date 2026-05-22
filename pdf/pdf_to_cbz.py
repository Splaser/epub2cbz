# pdf/pdf_to_cbz.py
import os
import tempfile
import shutil
from builder.cbz_builder import make_cbz
from images.filter import filter_image_files
from .pdf_utils import render_with_pdf2image, clean_pdf_name
from .pdf_splitter import process_images

def pdf_to_cbz(pdf_path: str, split_double_page=True, ratio_threshold=1.20, poppler_bin=None):
    temp_dir = tempfile.mkdtemp(prefix="pdf2cbz_")
    try:
        # 渲染 PDF
        image_paths = render_with_pdf2image(pdf_path, temp_dir, dpi=300, poppler_bin=poppler_bin)
        if not image_paths:
            print(f"❌ no pages extracted: {pdf_path}")
            return

        # 过滤垃圾页
        filtered_images = filter_image_files(image_paths)

        # 拆双页
        final_images = process_images(filtered_images, temp_dir, split_double_page=split_double_page, ratio_threshold=ratio_threshold)

        # 打包 CBZ
        output_cbz = os.path.join(os.path.dirname(pdf_path), clean_pdf_name(os.path.splitext(os.path.basename(pdf_path))[0]) + ".cbz")
        make_cbz(final_images, output_cbz)
        print(f"✅ PDF to CBZ done: {output_cbz} [{len(final_images)} pages]")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)