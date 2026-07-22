import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from cbz_crop_margins import crop_cbz


def _scanned_page(box, color=(229, 211, 193)) -> bytes:
    image = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(box, fill=color)
    draw.rectangle(
        (box[0] + 80, box[1] + 100, box[2] - 80, box[3] - 100),
        outline="black",
        width=8,
    )
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


class CbzMarginCropTests(unittest.TestCase):
    def test_crops_images_and_preserves_comicinfo(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "book.cbz")
            output = Path(directory, "book.cropped.cbz")
            xml = b"<ComicInfo><Series>Test</Series></ComicInfo>"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("0001.jpg", _scanned_page((0, 0, 700, 850)))
                archive.writestr("0002.jpg", _scanned_page((100, 0, 799, 850)))
                archive.writestr("ComicInfo.xml", xml)

            changed, total = crop_cbz(source, output, padding=0)

            self.assertEqual((changed, total), (2, 2))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("ComicInfo.xml"), xml)
                with Image.open(io.BytesIO(archive.read("0001.jpg"))) as first:
                    self.assertLess(first.width, 800)
                    self.assertLess(first.height, 1000)
                with Image.open(io.BytesIO(archive.read("0002.jpg"))) as second:
                    self.assertLess(second.width, 800)
                    self.assertLess(second.height, 1000)

    def test_can_atomically_replace_input_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "book.cbz")
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("0001.jpg", _scanned_page((0, 0, 700, 850)))
                archive.writestr("ComicInfo.xml", b"<ComicInfo />")

            crop_cbz(source, source, padding=0, force=True)

            with zipfile.ZipFile(source) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("ComicInfo.xml"), b"<ComicInfo />")


if __name__ == "__main__":
    unittest.main()
