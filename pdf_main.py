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


def main() -> None:
    base_dir = get_base_dir()
    os.chdir(base_dir)

    pdf_files = sorted(
        (
            filename
            for filename in os.listdir(base_dir)
            if filename.lower().endswith(".pdf")
        ),
        key=natural_filename_key,
    )

    if not pdf_files:
        print(f"No PDF files found in: {base_dir}")
        return

    for filename in pdf_files:
        pdf_to_cbz(os.path.join(base_dir, filename))


if __name__ == "__main__":
    main()
