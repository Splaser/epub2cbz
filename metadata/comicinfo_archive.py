# metadata/comicinfo_archive.py
from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Iterable, Optional

from metadata.comicinfo import ComicInfo


COMICINFO_ENTRY_NAME = "ComicInfo.xml"


def is_comicinfo_path(name: str) -> bool:
    clean = name.replace("\\", "/").lower()
    return clean == "comicinfo.xml" or clean.endswith("/comicinfo.xml")


def find_comicinfo_entry_name(names: Iterable[str]) -> Optional[str]:
    """
    Kavita requires ComicInfo.xml at the archive root.
    This lookup is tolerant for existing archives, but writers should still use the root path.
    """
    normalized = [(name, name.replace("\\", "/")) for name in names]

    for original, clean in normalized:
        if clean == COMICINFO_ENTRY_NAME:
            return original

    for original, clean in normalized:
        if "/" not in clean and clean.lower() == COMICINFO_ENTRY_NAME.lower():
            return original

    for original, clean in normalized:
        if is_comicinfo_path(clean):
            return original

    return None


def read_comicinfo_from_cbz(cbz_path: str) -> Optional[ComicInfo]:
    with zipfile.ZipFile(cbz_path, "r") as archive:
        entry_name = find_comicinfo_entry_name(archive.namelist())
        if entry_name is None:
            return None

        return ComicInfo.from_xml_bytes(archive.read(entry_name))


def write_comicinfo_to_cbz(cbz_path: str, comicinfo: ComicInfo) -> None:
    """
    Add or replace root ComicInfo.xml in a CBZ without leaving duplicate metadata entries.
    """
    cbz_dir = os.path.dirname(os.path.abspath(cbz_path)) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".comicinfo_", suffix=".cbz", dir=cbz_dir)
    os.close(fd)

    try:
        with (
            zipfile.ZipFile(cbz_path, "r") as source,
            zipfile.ZipFile(temp_path, "w") as target,
        ):
            target.comment = source.comment

            for item in source.infolist():
                if is_comicinfo_path(item.filename):
                    continue
                with source.open(item) as entry:
                    target.writestr(item, entry.read())

            info = zipfile.ZipInfo(COMICINFO_ENTRY_NAME)
            info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, comicinfo.to_xml_bytes())

        os.replace(temp_path, cbz_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
