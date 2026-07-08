# builder/cbz_builder.py
import os
import zipfile
from utils.consts import IMG_EXT


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def make_cbz(image_paths, output_cbz, comicinfo_xml=None):
    with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_DEFLATED) as cbz:
        for idx, img_path in enumerate(image_paths, start=1):
            ext = os.path.splitext(img_path)[1].lower()
            arcname = f"{idx:04d}{ext}"
            cbz.write(img_path, arcname)

        if comicinfo_xml:
            if isinstance(comicinfo_xml, str):
                comicinfo_xml = comicinfo_xml.encode("utf-8")
            cbz.writestr("ComicInfo.xml", comicinfo_xml)
