# builder/cbz_builder.py
import os
import tempfile
import zipfile
from utils.consts import IMG_EXT


def is_image_file(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)


def make_cbz(image_paths, output_cbz, comicinfo_xml=None):
    output_dir = os.path.dirname(os.path.abspath(output_cbz))
    fd, temporary_cbz = tempfile.mkstemp(
        prefix=f".{os.path.basename(output_cbz)}.",
        suffix=".part",
        dir=output_dir,
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary_cbz, "w", compression=zipfile.ZIP_DEFLATED) as cbz:
            for idx, img_path in enumerate(image_paths, start=1):
                ext = os.path.splitext(img_path)[1].lower()
                arcname = f"{idx:04d}{ext}"
                cbz.write(img_path, arcname)

            if comicinfo_xml:
                if isinstance(comicinfo_xml, str):
                    comicinfo_xml = comicinfo_xml.encode("utf-8")
                cbz.writestr("ComicInfo.xml", comicinfo_xml)

        with zipfile.ZipFile(temporary_cbz, "r") as cbz:
            bad_entry = cbz.testzip()
            if bad_entry is not None:
                raise RuntimeError(f"CBZ verification failed at {bad_entry}")
        os.replace(temporary_cbz, output_cbz)
    finally:
        if os.path.isfile(temporary_cbz):
            os.remove(temporary_cbz)
