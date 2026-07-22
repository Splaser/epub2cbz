import os
import tempfile
import unittest

from pdf.pdf_utils import build_pdf_output_cbz_name


class PdfOutputNameTests(unittest.TestCase):
    def _path(self, filename: str) -> str:
        return os.path.join(self.series_dir, filename)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.series_dir = os.path.join(self.temp_dir.name, "电子游戏软件")

    def test_yearly_issue_uses_total_issue_number(self):
        self.assertEqual(
            build_pdf_output_cbz_name(
                self._path("电子游戏软件.01年第08期.总第85期.pdf")
            ),
            "电子游戏软件 v085.cbz",
        )
        self.assertEqual(
            build_pdf_output_cbz_name(
                self._path("电子游戏软件.01年第12期.总第89期.pdf")
            ),
            "电子游戏软件 v089.cbz",
        )

    def test_numbered_issue_with_publication_month_is_unchanged(self):
        self.assertEqual(
            build_pdf_output_cbz_name(
                self._path("电子游戏软件第54期 1999.01.pdf")
            ),
            "电子游戏软件 v054.cbz",
        )


if __name__ == "__main__":
    unittest.main()
