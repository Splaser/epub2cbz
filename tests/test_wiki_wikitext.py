import unittest

from metadata.wiki_wikitext import parse_edition_count, parse_wikitext


FOOTBALL_WIKITEXT = """
{{Infobox animanga/Manga
|標題 = 足球小將
|作者 = [[高橋陽一]]
|出版社 = [[集英社]]
|label = ジャンプ・コミックス
|冊數 = 全37卷<br>全21卷（文庫版）
}}
"""


class EditionCountTests(unittest.TestCase):
    def test_aizoban_alias_selects_bunkoban_count(self):
        parsed = parse_wikitext(
            FOOTBALL_WIKITEXT,
            query="足球小將翼 (愛藏版)",
        )

        self.assertIsNotNone(parsed.main_manga)
        self.assertEqual(parsed.main_manga.volume_count, 21)

    def test_simplified_aizoban_alias_selects_simplified_annotation(self):
        self.assertEqual(
            parse_edition_count("全37卷；全21卷（文库版）", "足球小将翼 (爱藏版)"),
            21,
        )

    def test_regular_edition_keeps_default_first_count(self):
        parsed = parse_wikitext(FOOTBALL_WIKITEXT, query="足球小將翼")

        self.assertIsNotNone(parsed.main_manga)
        self.assertEqual(parsed.main_manga.volume_count, 37)

    def test_annotation_before_count_is_supported(self):
        self.assertEqual(
            parse_edition_count("普通版：37卷／文庫版：全21卷", "足球小將翼 文庫版"),
            21,
        )


if __name__ == "__main__":
    unittest.main()
