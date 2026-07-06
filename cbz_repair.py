import os
import sys
import zipfile
import tempfile
import shutil

from images.filter import get_garbage_image_reason, is_image_file
from images.splitter import infer_common_page_size, split_wide_image_if_needed
from builder.cbz_builder import make_cbz


def iter_images_recursive(root_dir: str):
    images = []
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if is_image_file(path):
                images.append(path)

    # 保留 CBZ 内部路径顺序，而不是只按 basename 排
    images.sort(key=lambda p: os.path.relpath(p, root_dir).replace("\\", "/"))
    return images


def repair_cbz(cbz_path: str, overwrite: bool = True, backup: bool = True):
    temp_dir = tempfile.mkdtemp(prefix="cbz_repair_")
    out_path = cbz_path if overwrite else os.path.splitext(cbz_path)[0] + ".repaired.cbz"

    try:
        with zipfile.ZipFile(cbz_path, "r") as z:
            z.extractall(temp_dir)

        image_files = iter_images_recursive(temp_dir)

        valid_images = []
        garbage_count = 0

        for idx, img_path in enumerate(image_files):
            reason = get_garbage_image_reason(img_path)
            if reason:
                garbage_count += 1
                try:
                    size_kb = os.path.getsize(img_path) // 1024
                except Exception:
                    size_kb = -1
                print(
                    f"  - skip [garbage-image:{reason}] "
                    f"{os.path.basename(img_path)} ({size_kb}KB)"
                )
                continue

            valid_images.append((idx, img_path))

        if not valid_images:
            print(f"❌ No valid images found, skip: {cbz_path}")
            return

        common_page_size = infer_common_page_size([img for _, img in valid_images])

        images_with_index = []
        split_counter = 0
        split_count = 0

        for idx, img_path in valid_images:
            split_out_dir = os.path.join(temp_dir, "__split_pages", f"{idx:06d}")
            os.makedirs(split_out_dir, exist_ok=True)

            split_imgs = split_wide_image_if_needed(
                img_path,
                split_out_dir,
                enable_split=True,
                common_page_size=common_page_size,
            )
            
            if len(split_imgs) > 1:
                split_count += 1
                print(f"  - split wide page: {os.path.basename(img_path)} -> {len(split_imgs)} pages")

            for s_img in split_imgs:
                images_with_index.append((idx, split_counter, s_img))
                split_counter += 1

        images_with_index.sort(key=lambda x: (x[0], x[1]))
        final_images = [img for _, _, img in images_with_index]

        # 没有垃圾页、也没有拆页，就不覆盖
        if garbage_count == 0 and split_count == 0:
            print(f"✅ No repair needed, skipping overwrite: {cbz_path}")
            return

        if overwrite and backup:
            backup_path = cbz_path + ".bak"
            if not os.path.exists(backup_path):
                shutil.copy2(cbz_path, backup_path)
                print(f"  - backup created: {backup_path}")

        make_cbz(final_images, out_path)

        print(
            f"✅ CBZ repaired: {out_path}, "
            f"pages={len(final_images)}, "
            f"garbage_removed={garbage_count}, "
            f"wide_images_split={split_count}"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


if __name__ == "__main__":
    base_dir = get_base_dir()
    os.chdir(base_dir)

    cbz_files = [
        os.path.join(base_dir, f)
        for f in os.listdir(base_dir)
        if f.lower().endswith(".cbz")
    ]
    cbz_files.sort()

    if not cbz_files:
        print(f"❌ No cbz files found in: {base_dir}")

    for cbz in cbz_files:
        repair_cbz(cbz, overwrite=True, backup=False)