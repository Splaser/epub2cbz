import os
import tempfile
import shutil
from images.filter import get_garbage_image_reason
from parser.html_parser import extract_images_from_html
from builder.cbz_builder import make_cbz
from utils.epub_utils import extract_epub, get_html_files_by_spine, fallback_all_images
from utils.metadata_utils import build_output_cbz_name
from images.splitter import split_wide_image_if_needed

def epub_to_cbz_fixed(epub_path):
    output_name = build_output_cbz_name(epub_path)
    output_cbz = os.path.join(os.path.dirname(epub_path), output_name)
    temp_dir = tempfile.mkdtemp(prefix="epub2cbz_")

    try:
        # 解压 EPUB
        extract_epub(epub_path, temp_dir)

        # 严格 spine 顺序获取 HTML
        html_files, spine_dicts = get_html_files_by_spine(temp_dir)

        images_with_index = []

        for spine_idx, item in enumerate(spine_dicts):
            html_path = item["local_path"]
            imgs = extract_images_from_html(html_path)
            imgs = [img for img in imgs if not get_garbage_image_reason(img)]

            split_counter = 0  # 保证拆页连续
            for img in imgs:
                split_imgs = split_wide_image_if_needed(img, temp_dir, enable_split=True)
                for s_img in split_imgs:
                    images_with_index.append((spine_idx, split_counter, s_img))
                    split_counter += 1

        # fallback 仅补缺页
        if not images_with_index:
            fallback_imgs = fallback_all_images(temp_dir)
            fallback_imgs = [img for img in fallback_imgs if not get_garbage_image_reason(img)]
            for f_idx, f_img in enumerate(fallback_imgs):
                images_with_index.append((9999, 0, f_idx, f_img))  # spine_idx=9999表示 fallback

        # 排序
        images_with_index.sort(key=lambda x: (x[0], x[1]))
        final_images = [img for _, _, img in images_with_index]

        # 打包 CBZ
        make_cbz(final_images, output_cbz)
        print(f"✅ CBZ created: {output_cbz}, total pages: {len(final_images)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    epub_files = [f for f in os.listdir(".") if f.lower().endswith(".epub")]
    epub_files.sort()
    for epub in epub_files:
        epub_to_cbz_fixed(epub)