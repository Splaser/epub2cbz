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

class DateFieldAliasTests(unittest.TestCase):
    def test_traditional_start_and_end_date_fields_are_supported(self):
        parsed = parse_wikitext("""
{{Infobox animanga/Manga
|標題 = 膽大黨
|開始日 = 2021年4月6日
|結束日 = 2026年7月1日
}}
""")

        self.assertIsNotNone(parsed.main_manga)
        self.assertEqual(parsed.main_manga.start, "2021年4月6日")
        self.assertEqual(parsed.main_manga.end, "2026年7月1日")

    def test_simplified_date_fields_are_supported(self):
        parsed = parse_wikitext("""
{{Infobox animanga/Manga
|标题 = Example
|开始日 = 2022年3月
|结束 = 2025年8月
}}
""")

        self.assertIsNotNone(parsed.main_manga)
        self.assertEqual(parsed.main_manga.start, "2022年3月")
        self.assertEqual(parsed.main_manga.end, "2025年8月")

    def test_release_date_is_used_only_when_start_fields_are_missing(self):
        parsed = parse_wikitext("""
{{Infobox animanga/Manga
|標題 = Example
|開始 = 2020年
|發售日 = 2019年12月
}}
""")
        fallback = parse_wikitext("""
{{Infobox animanga/Manga
|標題 = Example
|發售日 = 2019年12月
}}
""")

        self.assertEqual(parsed.main_manga.start, "2020年")
        self.assertEqual(fallback.main_manga.start, "2019年12月")


class PublisherFieldTests(unittest.TestCase):
    def test_localized_publishers_are_parsed_from_other_publishers_field(self):
        parsed = parse_wikitext("""
{{Infobox animanga/Manga
|標題 = BLEACH
|出版社 = {{flagicon|Japan}} [[集英社]]
|其他出版社 = {{flagicon|Taiwan}} [[東立出版社]]<br>{{flagicon|Hong Kong}} [[文化傳信]]
}}
""")

        self.assertIsNotNone(parsed.main_manga)
        self.assertEqual(parsed.main_manga.japan_publishers, ["集英社"])
        self.assertEqual(parsed.main_manga.taiwan_publishers, ["東立出版社"])
        self.assertEqual(parsed.main_manga.hongkong_publishers, ["文化傳信"])


if __name__ == "__main__":
    unittest.main()
