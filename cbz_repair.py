import argparse
from copy import copy
from hashlib import sha256
import os
from pathlib import Path
import sys
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET

from images.filter import get_garbage_image_reason, is_image_file
from images.splitter import infer_common_page_size, split_wide_image_if_needed
from builder.cbz_builder import make_cbz
from metadata.comicinfo import ComicInfo
from metadata.comicinfo_archive import (
    find_comicinfo_entry_name,
    is_comicinfo_path,
    write_comicinfo_to_cbz,
)
from metadata.epub_comicinfo import build_comicinfo_xml_for_epub


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


def repair_cbz(
    cbz_path: str,
    overwrite: bool = True,
    backup: bool = False,
    wiki_series_metadata=None,
):
    temp_dir = tempfile.mkdtemp(prefix="cbz_repair_")
    out_path = cbz_path if overwrite else os.path.splitext(cbz_path)[0] + ".repaired.cbz"

    try:
        with zipfile.ZipFile(cbz_path, "r") as z:
            comicinfo_xml = read_existing_comicinfo_xml(z)
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

        refreshed_comicinfo_xml = None
        if wiki_series_metadata is not None:
            try:
                refreshed_comicinfo_xml = build_comicinfo_xml_for_epub(
                    epub_path=cbz_path,
                    output_cbz_name=os.path.basename(cbz_path),
                    page_count=len(final_images),
                    wiki_series=wiki_series_metadata,
                )
            except Exception as exc:
                print(f"  - keep existing ComicInfo.xml: refresh failed ({exc})")

        metadata_changed = (
            refreshed_comicinfo_xml is not None
            and comicinfo_xml != refreshed_comicinfo_xml
        )

        # Metadata-only repairs preserve every existing archive entry.  Avoid a
        # full image rebuild when pages themselves did not need repair.
        if garbage_count == 0 and split_count == 0 and metadata_changed:
            if overwrite and backup:
                create_backup(cbz_path)

            metadata_out_path = cbz_path if overwrite else out_path
            if not overwrite:
                shutil.copy2(cbz_path, metadata_out_path)
            write_comicinfo_to_cbz(
                metadata_out_path,
                ComicInfo.from_xml_bytes(refreshed_comicinfo_xml),
            )
            print(f"✅ ComicInfo refreshed: {metadata_out_path}")
            return

        # 没有垃圾页、拆页或元数据变化，就不覆盖
        if garbage_count == 0 and split_count == 0:
            print(f"✅ No repair needed, skipping overwrite: {cbz_path}")
            return

        if overwrite and backup:
            create_backup(cbz_path)

        make_cbz(
            final_images,
            out_path,
            comicinfo_xml=refreshed_comicinfo_xml or comicinfo_xml,
        )

        print(
            f"✅ CBZ repaired: {out_path}, "
            f"pages={len(final_images)}, "
            f"garbage_removed={garbage_count}, "
            f"wide_images_split={split_count}"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def read_existing_comicinfo_xml(archive: zipfile.ZipFile):
    entry_name = find_comicinfo_entry_name(archive.namelist())
    if entry_name is None:
        return None

    try:
        return archive.read(entry_name)
    except Exception as exc:
        print(f"  - skip existing ComicInfo.xml: {exc}")
        return None


def create_backup(cbz_path: str):
    backup_path = cbz_path + ".bak"
    if not os.path.exists(backup_path):
        shutil.copy2(cbz_path, backup_path)
        print(f"  - backup created: {backup_path}")


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_KMOE_END_CARD = (86934, "cdc4a0dd92011239fc9d9c5e83667de2fa1722c73f265865760b09f8c3e2d1a9")


def is_end_card_name(name):
    return Path(name.replace("\\", "/")).stem.casefold() == "theendinfo"


def end_card_hashes(folder):
    size, digest = _KMOE_END_CARD
    hashes_by_size = {size: {digest}}
    for epub in sorted(folder.iterdir()):
        if epub.suffix.lower() != ".epub" or not epub.is_file():
            continue
        try:
            with zipfile.ZipFile(epub) as source:
                for entry in source.infolist():
                    if is_image_file(entry.filename) and is_end_card_name(entry.filename):
                        digest = sha256(source.read(entry)).hexdigest()
                        hashes_by_size.setdefault(entry.file_size, set()).add(digest)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
            print(f"  - could not read reference {epub.name}: {exc}")
    return hashes_by_size


def update_comicinfo_pages(xml, page_count, removed_indices):
    root = ET.fromstring(xml, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    count = root.find("PageCount")
    if count is None:
        count = ET.SubElement(root, "PageCount")
    count.text = str(page_count)
    pages = root.find("Pages")
    if pages is not None:
        for page in pages.findall("Page"):
            image = page.get("Image")
            if image is None:
                continue
            index = int(image)
            if index in removed_indices:
                pages.remove(page)
            else:
                shift = sum(removed < index for removed in removed_indices)
                page.set("Image", str(index - shift))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def repair_end_cards(path, hashes_by_size, *, apply=False, backup=False):
    temporary = None
    try:
        with zipfile.ZipFile(path) as source:
            images = sorted(
                (entry for entry in source.infolist() if is_image_file(entry.filename)),
                key=lambda entry: entry.filename.replace("\\", "/").casefold(),
            )
            removed = {}
            for index, entry in enumerate(images):
                hashes = hashes_by_size.get(entry.file_size)
                if is_end_card_name(entry.filename) or (
                    hashes and sha256(source.read(entry)).hexdigest() in hashes
                ):
                    removed[entry.header_offset] = index
                    print(f"  - end card: {entry.filename}")
            if not removed:
                return 0
            page_count = len(images) - len(removed)
            if not page_count:
                raise ValueError("Repair would remove all pages")
            if not apply:
                return len(removed)

            removed_indices = set(removed.values())
            fd, temporary = tempfile.mkstemp(prefix=".cbz-repair-", suffix=".part", dir=path.parent)
            os.close(fd)
            with zipfile.ZipFile(temporary, "w") as target:
                target.comment = source.comment
                for entry in source.infolist():
                    if entry.header_offset in removed:
                        continue
                    data = source.read(entry)
                    if is_comicinfo_path(entry.filename):
                        data = update_comicinfo_pages(data, page_count, removed_indices)
                    target.writestr(copy(entry), data)
        with zipfile.ZipFile(temporary) as target:
            if bad_entry := target.testzip():
                raise ValueError(f"CBZ verification failed at {bad_entry}")
        if backup:
            create_backup(str(path))
        os.replace(temporary, path)
        return len(removed)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.remove(temporary)


def main():
    parser = argparse.ArgumentParser(description="Find and remove known Kmoe end cards from CBZ files.")
    parser.add_argument("paths", nargs="*", type=Path, help="CBZ files or folders containing CBZ files")
    parser.add_argument("--apply", action="store_true", help="Apply repairs in place")
    parser.add_argument("--backup", action="store_true", help="Keep a .cbz.bak backup when applying repairs")
    args = parser.parse_args()
    paths = args.paths or [Path(get_base_dir())]
    cbz_files = {}
    failed = False
    for item in paths:
        if item.is_dir():
            for path in sorted(item.iterdir()):
                if path.is_file() and path.suffix.lower() == ".cbz":
                    cbz_files[path.resolve()] = None
        elif item.is_file() and item.suffix.lower() == ".cbz":
            cbz_files[item.resolve()] = None
        else:
            print(f"CBZ file or folder not found: {item}")
            failed = True

    if not cbz_files:
        print("No CBZ files found.")
        return 1 if failed else 0

    folder_hashes = {}
    changed = total_removed = 0
    for path in cbz_files:
        print(f"Checking {path}")
        try:
            if path.parent not in folder_hashes:
                folder_hashes[path.parent] = end_card_hashes(path.parent)
            count = repair_end_cards(path, folder_hashes[path.parent], apply=args.apply, backup=args.backup)
            if count:
                changed += 1
                total_removed += count
        except (OSError, ValueError, RuntimeError, ET.ParseError, zipfile.BadZipFile) as exc:
            print(f"  - failed: {exc}")
            failed = True
    action = "Applied" if args.apply else "Preview"
    print(f"{action}: {len(cbz_files)} checked, {changed} matched, {total_removed} end card(s).")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
