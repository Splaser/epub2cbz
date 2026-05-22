# cbz_repair.py
import os
import zipfile
import tempfile
import shutil
from images.filter import get_garbage_image_reason

# -----------------------------
# 垃圾页判断函数
# -----------------------------


def is_garbage_image(img_path: str, val_mean_threshold=250) -> bool:
    return get_garbage_image_reason(img_path, val_mean_threshold) is not None


# -----------------------------
# CBZ 修复函数（覆盖源文件，可跳过无垃圾页）
# -----------------------------


def repair_cbz(cbz_path: str):
    temp_dir = tempfile.mkdtemp(prefix="cbz_repair_")
    try:
        with zipfile.ZipFile(cbz_path, "r") as z:
            z.extractall(temp_dir)

        # 遍历图片
        image_files = sorted(
            [
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if f.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
                )
            ]
        )
        filtered_images = []
        garbage_found = False

        for img in image_files:
            if is_garbage_image(img):
                garbage_found = True
                print(f"  - skip garbage: {os.path.basename(img)}")
            else:
                filtered_images.append(img)

        # 如果没有发现垃圾页，直接跳过，不覆盖写入
        if not garbage_found:
            print(f"✅ No garbage found, skipping overwrite: {cbz_path}")
            return

        # 打包回原文件（覆盖）
        with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_STORED) as z:
            for i, img in enumerate(filtered_images, start=1):
                ext = os.path.splitext(img)[1].lower()
                arcname = f"{i:04d}{ext}"
                z.write(img, arcname)

        print(
            f"✅ CBZ repaired and overwritten: {cbz_path} ({len(filtered_images)} pages)"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# -----------------------------
# 批量处理当前目录 CBZ
# -----------------------------
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cbz_files = [
        os.path.join(current_dir, f)
        for f in os.listdir(current_dir)
        if f.lower().endswith(".cbz")
    ]

    if not cbz_files:
        print("当前目录没有找到 CBZ 文件。")
    else:
        for cbz in cbz_files:
            repair_cbz(cbz)
