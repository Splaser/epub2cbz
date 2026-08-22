import unittest

from metadata.epub_comicinfo import infer_volume_number
from utils.metadata_utils import (
    build_output_cbz_name,
    extract_series_name,
    extract_special_label,
)


class SeriesNameTests(unittest.TestCase):
    def test_parent_directory_wins_over_truncated_bracket_label(self):
        path = (
            "E:/Books/JOJO的奇妙冒險9 JOJO Lands/"
            "[Kmoe][JOJO的奇妙冒險9JOJO]卷001.epub"
        )

        self.assertEqual(
            extract_series_name(path),
            "JOJO的奇妙冒險9 JOJO Lands",
        )
        self.assertEqual(
            build_output_cbz_name(path),
            "JOJO的奇妙冒險9 JOJO Lands - 第001卷.cbz",
        )

    def test_bare_filename_still_uses_bracket_label(self):
        filename = "[Kmoe][海賊王]卷111.epub"

        self.assertEqual(extract_series_name(filename), "海賊王")
        self.assertEqual(
            build_output_cbz_name(filename),
            "海賊王 - 第111卷.cbz",
        )


class SpecialNameTests(unittest.TestCase):
    def test_traditional_chinese_bonus_book_names_are_recognized(self):
        for title in ("官方角色設定集", "秘笈", "畫冊", "20周年紀念短篇"):
            with self.subTest(title=title):
                self.assertIsNotNone(extract_special_label(title))

    def test_anniversary_number_is_not_used_as_a_volume(self):
        path = "E:/Books/測試系列/20周年紀念短篇.epub"
        output_name = build_output_cbz_name(path)

        self.assertEqual(
            output_name,
            "測試系列 - 20周年紀念短篇.cbz",
        )
        self.assertIsNone(infer_volume_number(path))
        self.assertIsNone(infer_volume_number(output_name))

    def test_explicit_numbered_special_still_keeps_its_number(self):
        path = "E:/Books/測試系列/番外 第2卷.epub"

        self.assertEqual(
            build_output_cbz_name(path),
            "測試系列 - 番外 第002册.cbz",
        )


if __name__ == "__main__":
    unittest.main()
