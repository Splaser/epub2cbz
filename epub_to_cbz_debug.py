import os
import re

from main import epub_to_cbz_fixed


def epub_to_cbz_enhanced(epub_path: str):
    print(f"Processing EPUB: {epub_path}")
    epub_to_cbz_fixed(epub_path)


if __name__ == "__main__":
    epub_files = [f for f in os.listdir(".") if f.lower().endswith(".epub")]
    epub_files.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])
    if not epub_files:
        print("当前目录没有找到 epub 文件。")
    else:
        for epub in epub_files:
            epub_to_cbz_enhanced(epub)
