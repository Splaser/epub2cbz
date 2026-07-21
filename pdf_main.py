import argparse
import os
import re
import sys

from pdf.pdf_to_cbz import pdf_to_cbz


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def natural_filename_key(filename: str):
    """Sort filenames case-insensitively while comparing digit runs numerically."""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", filename)
        if part
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PDFs beside this program to CBZ files.")
    parser.add_argument(
        "pdf_paths",
        nargs="*",
        metavar="PDF",
        help=(
            "PDF file(s) dragged onto the executable; these are converted directly "
            "without front-page detection or OCR"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild every CBZ even when an output file already exists",
    )
    args = parser.parse_args()

    base_dir = get_base_dir()
    direct_mode = bool(args.pdf_paths)
    if direct_mode:
        # Resolve relative CLI paths before changing into the executable folder.
        # Explorer drag-and-drop normally supplies absolute paths.
        pdf_files = [os.path.abspath(path) for path in args.pdf_paths]
        invalid_paths = [
            path
            for path in pdf_files
            if not os.path.isfile(path) or not path.lower().endswith(".pdf")
        ]
        if invalid_paths:
            for path in invalid_paths:
                print(f"ERROR: not a PDF file: {path}")
            return 2
        print("Direct conversion mode: front-page detection and OCR are disabled.")
    else:
        pdf_files = sorted(
            (
                os.path.join(base_dir, filename)
                for filename in os.listdir(base_dir)
                if filename.lower().endswith(".pdf")
            ),
            key=lambda path: natural_filename_key(os.path.basename(path)),
        )

    os.chdir(base_dir)

    if not pdf_files:
        print(f"No PDF files found in: {base_dir}")
        return 0

    failures = []
    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        try:
            pdf_to_cbz(
                pdf_path,
                force=args.force,
                filter_frontmatter=not direct_mode,
            )
        except Exception as exc:
            failures.append((filename, exc))
            print(f"ERROR: PDF conversion failed: {filename} ({exc})")

    if failures:
        print(f"Completed with {len(failures)} failure(s):")
        for filename, exc in failures:
            print(f"  - {filename}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
