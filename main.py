# main.py
import os
import tempfile
import shutil
import re


from parser.html_parser import extract_image_paths_from_html
from images.filter import filter_html_files, filter_image_files
from images.splitter import split_images_if_needed
from builder.cbz_builder import make_cbz
from utils.epub_utils import extract_epub, get_html_files_by_spine, get_html_files_by_dir_fallback, fallback_all_images
from utils.metadata_utils import compute_normal_page_ratio, build_output_cbz_name


def epub_to_cbz(epub_path: str):
    output_name = build_output_cbz_name(epub_path)
    output_cbz = os.path.join(os.path.dirname(epub_path), output_name)
    temp_dir = tempfile.mkdtemp(prefix="epub2cbz_")

    try:
        # 1. 解压 epub
        extract_epub(epub_path, temp_dir)

        # 2. 获取 HTML 文件
        try:
            html_files = get_html_files_by_spine(temp_dir)
        except Exception:
            html_files = []
        if not html_files:
            html_files = get_html_files_by_dir_fallback(temp_dir)

        # 3. 过滤 HTML
        html_files = filter_html_files(html_files)

        # 4. 提取图片路径
        images = []
        for html in html_files:
            images.extend(extract_image_paths_from_html(html))

        # 5. 图片过滤
        images = filter_image_files(images)

        if not images:
            # fallback 所有图片
            images = fallback_all_images(temp_dir)
            images = filter_image_files(images)

        if not images:
            print(f"❌ no images found in {epub_path}")
            return

        # 6. 计算正常比例
        normal_ratio = compute_normal_page_ratio(images)

        # 7. 拆页
        images = split_images_if_needed(images, temp_dir, normal_ratio=normal_ratio)

        # 8. 打包 CBZ
        make_cbz(images, output_cbz)
        print(f"✅ {output_name}  [{len(images)} pages]")

    except Exception as e:
        print(f"❌ failed: {epub_path} -> {e}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    epub_files = [f for f in os.listdir(".") if f.lower().endswith(".epub")]
    epub_files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])

    if not epub_files:
        print("当前目录没有找到 epub 文件。")
    else:
        for epub in epub_files:
            epub_to_cbz(epub)