import unittest
from unittest.mock import patch

from PIL import Image

from images.splitter import _tagged_tb_fallback_y


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


if __name__ == "__main__":
    unittest.main()
