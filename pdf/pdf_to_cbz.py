# pdf/pdf_to_cbz.py
import os
import tempfile
import shutil
from builder.cbz_builder import make_cbz
from metadata.pdf_comicinfo import build_comicinfo_xml_for_pdf
from .pdf_frontmatter_filter import filter_leading_disclaimer_pages
from .pdf_utils import build_pdf_output_cbz_name, extract_or_render_with_pymupdf


def pdf_to_cbz(pdf_path: str):
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
        output_name = build_pdf_output_cbz_name(pdf_path)
        output_cbz = os.path.join(
            os.path.dirname(pdf_path),
            output_name,
        )
        comicinfo_xml = build_comicinfo_xml_for_pdf(
            pdf_path=pdf_path,
            output_cbz_name=output_name,
            page_count=len(filtered_images),
        )
        make_cbz(filtered_images, output_cbz, comicinfo_xml=comicinfo_xml)
        print(f"PDF to CBZ done: {output_cbz} [{len(filtered_images)} pages]")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
