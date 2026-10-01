import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from images.splitter import split_wide_image_if_needed


class TaggedSpreadTests(unittest.TestCase):
    def setUp(self):
        # A common portrait page ratio of 0.65. A 1264x1640 source splits into
        # two 820x1264 pages after the configured rotation, also ratio 0.65.
        self.common_page_size = (1040, 1600)

    def test_continuous_spread_is_not_cut_even_when_halves_match_page_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "spread.png"
            Image.new("RGB", (1264, 1640), "black").save(image_path)
            with patch("images.splitter.get_epub_rotate_hint", return_value=1):
                result = split_wide_image_if_needed(
                    str(image_path), temp_dir, common_page_size=self.common_page_size
                )
            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1640, 1264))

    def test_clean_separator_does_not_trigger_top_bottom_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "spread.png"
            image = Image.new("RGB", (1264, 1640), "black")
            image.paste("red", (0, 0, 1264, 795))
            image.paste("white", (0, 795, 1264, 845))
            image.save(image_path)
            with patch("images.splitter.get_epub_rotate_hint", return_value=1):
                result = split_wide_image_if_needed(
                    str(image_path), temp_dir, common_page_size=self.common_page_size
                )
            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1640, 1264))
                self.assertEqual(rotated.getpixel((1200, 600)), (255, 0, 0))
                self.assertEqual(rotated.getpixel((400, 600)), (0, 0, 0))

    def test_unclean_gutter_is_not_accepted_via_relaxed_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "spread.png"
            Image.new("RGB", (1264, 1640), "black").save(image_path)
            with patch("images.splitter.get_epub_rotate_hint", return_value=1), patch(
                "images.splitter.find_clean_horizontal_gutter_y", return_value=(None, "projection", 820)
            ):
                result = split_wide_image_if_needed(
                    str(image_path), temp_dir, common_page_size=self.common_page_size
                )
            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1640, 1264))

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

            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1680, 763))

    def test_rejected_jojo_title_spread_is_still_rotated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "title-spread.png"
            image = Image.new("RGB", (943, 1280), "black")
            image.paste("red", (0, 0, 943, 640))
            image.save(image_path)

            with patch("images.splitter.get_epub_rotate_hint", return_value=1), patch(
                "images.splitter.find_clean_horizontal_gutter_y", return_value=(None, "projection", None)
            ):
                result = split_wide_image_if_needed(
                    str(image_path), temp_dir, common_page_size=(776, 1280)
                )

            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1280, 943))
                self.assertEqual(rotated.getpixel((1000, 470)), (255, 0, 0))
                self.assertEqual(rotated.getpixel((100, 470)), (0, 0, 0))

    def test_rejected_gutter_candidate_is_still_rotated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "foldout.png"
            Image.new("RGB", (943, 1280), "black").save(image_path)
            with patch("images.splitter.get_epub_rotate_hint", return_value=1), patch(
                "images.splitter.find_clean_horizontal_gutter_y", return_value=(640, "cv", None)
            ), patch("images.splitter._tb_pre_split_skip_reason", return_value="common-page-part-aspect"):
                result = split_wide_image_if_needed(
                    str(image_path), temp_dir, common_page_size=(776, 1280)
                )
            self.assertEqual(len(result), 1)
            with Image.open(result[0]) as rotated:
                self.assertEqual(rotated.size, (1280, 943))

    def test_rotate_zero_tall_page_is_never_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "title-page.png"
            Image.new("RGB", (1213, 2480), "black").save(image_path)

            with patch("images.splitter.get_epub_rotate_hint", return_value=0):
                result = split_wide_image_if_needed(
                    str(image_path),
                    temp_dir,
                    common_page_size=(1512, 2480),
                )

            self.assertEqual(result, [str(image_path)])

    def test_missing_rotate_tag_is_never_split(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "untagged-wide.png"
            Image.new("RGB", (2400, 1600), "white").save(image_path)

            with patch("images.splitter.get_epub_rotate_hint", return_value=None):
                result = split_wide_image_if_needed(
                    str(image_path),
                    temp_dir,
                    common_page_size=(1000, 1600),
                )

            self.assertEqual(result, [str(image_path)])


if __name__ == "__main__":
    unittest.main()
