import os
import sys

from pdf.pdf_to_cbz import pdf_to_cbz


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    base_dir = get_base_dir()
    os.chdir(base_dir)

    pdf_files = sorted(
        filename
        for filename in os.listdir(base_dir)
        if filename.lower().endswith(".pdf")
    )

    if not pdf_files:
        print(f"No PDF files found in: {base_dir}")
        return

    for filename in pdf_files:
        pdf_to_cbz(os.path.join(base_dir, filename))


if __name__ == "__main__":
    main()
