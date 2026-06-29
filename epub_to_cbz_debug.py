import os
import tempfile
import shutil
import re
from parser.html_parser import extract_image_paths_from_html, is_image_file
from images.filter import filter_html_files, filter_image_files
from images.splitter import infer_common_page_size, split_wide_image_if_needed
from builder.cbz_builder import make_cbz
from utils.epub_utils import extract_epub, get_html_files_by_spine, get_html_files_by_dir_fallback, fallback_all_images
from utils.metadata_utils import build_output_cbz_name


def epub_to_cbz_enhanced(epub_path: str):
    output_name = build_output_cbz_name(epub_path)
    output_cbz = os.path.join(os.path.dirname(epub_path), output_name)
    temp_dir = tempfile.mkdtemp(prefix="epub2cbz_enh_")

    try:
        print(f"Processing EPUB: {epub_path}")
        # 解压 EPUB
        extract_epub(epub_path, temp_dir)

        # 获取 spine HTML 文件
        try:
            html_files = get_html_files_by_spine(temp_dir)
            print(f"[DEBUG] Spine HTML count: {len(html_files)}")
        except Exception as e:
            html_files = []
            print(f"[DEBUG] Spine parse failed: {e}")

        if not html_files:
            html_files = get_html_files_by_dir_fallback(temp_dir)
            print(f"[DEBUG] Using fallback HTML files, count: {len(html_files)}")

        # 过滤广告页/尾页/垃圾页
        html_files = filter_html_files(html_files)
        print(f"[DEBUG] Filtered HTML count: {len(html_files)}")

        # 提取图片并绑定 spine index
        images_with_index = []
        processed_imgs = set()
        spine_missing = []

        for spine_idx, html_path in enumerate(html_files):
            img_paths = extract_image_paths_from_html(html_path)
            if not img_paths:
                spine_missing.append(spine_idx)
                continue
            for split_idx, img_path in enumerate(img_paths):
                if isinstance(img_path, tuple):
                    img_path = img_path[0]
                if is_image_file(img_path) and filter_image_files([img_path]):
                    if img_path not in processed_imgs:
                        processed_imgs.add(img_path)
                        images_with_index.append((spine_idx, split_idx, img_path))

        # 全局 fallback，只用一次
        if spine_missing:
            fallback_imgs = fallback_all_images(temp_dir)
            # 去除垃圾图片
            fallback_imgs = [p for p in fallback_imgs if filter_image_files([p])]
            # 去重
            fallback_imgs = [p for p in fallback_imgs if p not in processed_imgs]

            # 依次绑定缺图 spine
            for idx, spine_idx in enumerate(spine_missing):
                if idx < len(fallback_imgs):
                    img_path = fallback_imgs[idx]
                    processed_imgs.add(img_path)
                    images_with_index.append((spine_idx, 0, img_path))

        if not images_with_index:
            print(f"❌ No valid images found in {epub_path}")
            return

        # 拆页并保持 spine index
        final_split_images = []
        common_page_size = infer_common_page_size([img_path for _, _, img_path in images_with_index])
        for spine_idx, split_idx, img_path in images_with_index:
            split_imgs = split_wide_image_if_needed(
                img_path,
                temp_dir,
                common_page_size=common_page_size,
            )
            for s_idx, s_img in enumerate(split_imgs):
                final_split_images.append((spine_idx, split_idx, s_idx, s_img))

        # 排序: spine_idx -> split_idx -> s_idx
        final_split_images.sort(key=lambda x: (x[0], x[1], x[2]))

        # 最终图片列表
        final_images = [img for _, _, _, img in final_split_images]
        print(f"[DEBUG] Total final images count: {len(final_images)}")

        # 打包 CBZ
        make_cbz(final_images, output_cbz)
        print(f"✅ CBZ created: {output_cbz}, total pages: {len(final_images)}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



if __name__ == "__main__":
    epub_files = [f for f in os.listdir(".") if f.lower().endswith(".epub")]
    epub_files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\\d+)", s)])
    if not epub_files:
        print("当前目录没有找到 epub 文件。")
    else:
        for epub in epub_files:
            epub_to_cbz_enhanced(epub)
