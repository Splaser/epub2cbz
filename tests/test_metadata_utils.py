import unittest

from utils.metadata_utils import build_output_cbz_name, extract_series_name


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


if __name__ == "__main__":
    unittest.main()
