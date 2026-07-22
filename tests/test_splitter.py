import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from images.splitter import _tagged_tb_fallback_y, split_wide_image_if_needed


class TaggedTbFallbackTests(unittest.TestCase):
    def setUp(self):
        # A common portrait page ratio of 0.65. A 1264x1640 source splits into
        # two 820x1264 pages after the configured rotation, also ratio 0.65.
        self.common_page_size = (1040, 1600)

    def test_accepts_tagged_spread_without_a_white_gutter(self):
        image = Image.new("RGB", (1264, 1640), "black")

        with patch("images.splitter.ROTATE_VERTICAL_SPLIT_PAGE", True):
            self.assertEqual(
                _tagged_tb_fallback_y(image, 1, self.common_page_size),
                820,
            )

    def test_rejects_untagged_image_with_the_same_shape(self):
        image = Image.new("RGB", (1264, 1640), "black")

        with patch("images.splitter.ROTATE_VERTICAL_SPLIT_PAGE", True):
            self.assertIsNone(
                _tagged_tb_fallback_y(image, None, self.common_page_size)
            )

    def test_rejects_tagged_cover_wrap_with_a_different_shape(self):
        image = Image.new("RGB", (1181, 1680), "black")

        with patch("images.splitter.ROTATE_VERTICAL_SPLIT_PAGE", True):
            self.assertIsNone(
                _tagged_tb_fallback_y(image, 1, self.common_page_size)
            )

    def test_requires_a_book_level_page_shape(self):
        image = Image.new("RGB", (1264, 1640), "black")

        self.assertIsNone(_tagged_tb_fallback_y(image, 1, None))

    def test_tagged_cover_does_not_fall_through_to_generic_tall_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "cover-wrap.png"
            Image.new("RGB", (763, 1680), "black").save(image_path)

            with patch("images.splitter.get_epub_rotate_hint", return_value=1), patch(
                "images.splitter.ROTATE_VERTICAL_SPLIT_PAGE", True
            ):
                result = split_wide_image_if_needed(
                    str(image_path),
                    temp_dir,
                    common_page_size=self.common_page_size,
                )

            self.assertEqual(result, [str(image_path)])


if __name__ == "__main__":
    unittest.main()
