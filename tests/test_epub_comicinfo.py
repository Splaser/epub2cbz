import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from metadata.comicinfo import ComicInfo
from metadata.epub_comicinfo import (
    build_comicinfo_xml_for_epub,
    load_cached_wiki_series,
    load_exact_wiki_series_for_dir,
)
from metadata.wiki_models import WikiMangaInfo, WikiPageData, WikiSeriesMetadata
from metadata.wiki_scraper import build_series_metadata_from_wikitext


class _FakeWikiClient:
    def __init__(self, page_data):
        self._page_data = page_data
        self.page_data_calls = []

    def page_data(self, title):
        self.page_data_calls.append(title)
        return self._page_data


class _SearchFallbackWikiClient:
    def __init__(self, page_data):
        self._page_data = page_data
        self.search_calls = []

    def page_data(self, title):
        raise ValueError(f"page not found: {title}")

    def page_data_for_query(self, query, *, limit=5):
        self.search_calls.append((query, limit))
        return self._page_data


def _page_data() -> WikiPageData:
    return WikiPageData(
        requested_title="JOJO的奇妙冒險9 JOJO Lands",
        title="The JOJOLands",
        pageid=123,
        wikitext="wiki source",
        extract="Wiki summary",
        description="Wiki description",
        page_url="https://zh.wikipedia.org/wiki/The_JOJOLands",
        wikibase_item="Q123",
        defaultsort="JOJOLands",
        categories=["日本漫畫作品"],
    )


class RelaxedWikiTitleTests(unittest.TestCase):
    def test_ambiguous_local_title_uses_canonical_manga_title(self):
        bleach_page = WikiPageData(
            requested_title="BLEACH",
            title="BLEACH",
            pageid=1,
            wikitext="wiki source",
            extract="《BLEACH》是久保帶人創作的少年漫畫。",
            page_url="https://zh.wikipedia.org/wiki/BLEACH",
        )
        parsed = WikiSeriesMetadata(
            page_title="BLEACH",
            pageid=1,
            page_url=bleach_page.page_url,
            wikibase_item=None,
            summary=bleach_page.extract,
            main_manga=WikiMangaInfo(title="BLEACH", author=["久保帶人"], volume_count=74),
        )
        client = _FakeWikiClient(bleach_page)

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "metadata.epub_comicinfo.build_series_metadata_from_page_data",
            return_value=parsed,
        ) as build:
            series_dir = Path(temp_dir) / "死神"
            series_dir.mkdir()
            result = load_exact_wiki_series_for_dir(
                series_dir,
                client=client,
                use_cache=False,
            )

        self.assertIs(result, parsed)
        self.assertEqual(client.page_data_calls, ["BLEACH"])
        self.assertEqual(build.call_args.kwargs["query"], "BLEACH")

    def test_missing_exact_page_uses_search_result(self):
        parsed = WikiSeriesMetadata(
            page_title="The JOJOLands",
            pageid=123,
            page_url="https://zh.wikipedia.org/wiki/The_JOJOLands",
            wikibase_item="Q123",
            summary="Wiki summary",
            main_manga=WikiMangaInfo(author=["荒木飛呂彥"]),
        )
        client = _SearchFallbackWikiClient(_page_data())

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "metadata.epub_comicinfo.build_series_metadata_from_page_data",
            return_value=parsed,
        ):
            series_dir = Path(temp_dir) / "JOJO的奇妙冒險9 JOJO Lands"
            series_dir.mkdir()
            result = load_exact_wiki_series_for_dir(
                series_dir,
                client=client,
                use_cache=False,
            )

        self.assertIs(result, parsed)
        self.assertEqual(
            client.search_calls,
            [("JOJO的奇妙冒險9 JOJO Lands", 5)],
        )

    def test_title_mismatch_keeps_parsed_wiki_metadata(self):
        parsed = WikiSeriesMetadata(
            page_title="The JOJOLands",
            pageid=123,
            page_url="https://zh.wikipedia.org/wiki/The_JOJOLands",
            wikibase_item="Q123",
            summary="Wiki summary",
            main_manga=WikiMangaInfo(author=["荒木飛呂彥"]),
            categories=["日本漫畫作品"],
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "metadata.epub_comicinfo.build_series_metadata_from_page_data",
            return_value=parsed,
        ) as build:
            series_dir = Path(temp_dir) / "JOJO的奇妙冒險9 JOJO Lands"
            series_dir.mkdir()
            result = load_exact_wiki_series_for_dir(
                series_dir,
                client=_FakeWikiClient(_page_data()),
                use_cache=False,
            )

        self.assertIs(result, parsed)
        build.assert_called_once_with(
            _page_data(),
            query="JOJO的奇妙冒險9 JOJO Lands",
        )

    def test_infobox_failure_keeps_page_level_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "metadata.epub_comicinfo.build_series_metadata_from_page_data",
            side_effect=ValueError("missing manga infobox"),
        ):
            series_dir = Path(temp_dir) / "Local Series Name"
            series_dir.mkdir()
            result = load_exact_wiki_series_for_dir(
                series_dir,
                client=_FakeWikiClient(_page_data()),
                use_cache=False,
            )

        self.assertIsNotNone(result)
        self.assertEqual(result.page_title, "The JOJOLands")
        self.assertEqual(result.summary, "Wiki summary")
        self.assertEqual(result.page_url, "https://zh.wikipedia.org/wiki/The_JOJOLands")
        self.assertEqual(result.wikibase_item, "Q123")
        self.assertEqual(result.series_sort, "JOJOLands")
        self.assertEqual(result.categories, ["日本漫畫作品"])


class MetadataCacheVersionTests(unittest.TestCase):
    def test_previous_cache_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "series.meta.json"
            cache_path.write_text(
                json.dumps({
                    "schema_version": 4,
                    "series_name": "膽大黨",
                    "metadata": {},
                }),
                encoding="utf-8",
            )

            result = load_cached_wiki_series(
                cache_path,
                expected_series_name="膽大黨",
            )

        self.assertIsNone(result)


class SpecialComicInfoTests(unittest.TestCase):
    def test_unnumbered_bonus_books_are_written_as_specials(self):
        for title in ("官方角色設定集", "秘笈", "畫冊", "20周年紀念短篇"):
            with self.subTest(title=title):
                xml = build_comicinfo_xml_for_epub(
                    epub_path=f"E:/Books/測試系列/{title}.epub",
                    output_cbz_name=f"測試系列 - {title}.cbz",
                    page_count=74,
                    wiki_series=self._wiki(),
                )

                self.assertIsNotNone(xml)
                comicinfo = ComicInfo.from_xml_bytes(xml)
                self.assertEqual(comicinfo.title, title)
                self.assertEqual(comicinfo.format, "Special")
                self.assertIsNone(comicinfo.number)
                self.assertEqual(comicinfo.count, 20)

    def test_numbered_bonus_book_is_special_but_keeps_its_number(self):
        xml = build_comicinfo_xml_for_epub(
            epub_path="E:/Books/測試系列/番外 第2卷.epub",
            output_cbz_name="測試系列 - 番外 第002册.cbz",
            page_count=50,
            wiki_series=self._wiki(),
        )

        comicinfo = ComicInfo.from_xml_bytes(xml)
        self.assertEqual(comicinfo.format, "Special")
        self.assertEqual(comicinfo.number, "2")

    def test_repair_style_cbz_name_does_not_repeat_series_in_special_title(self):
        xml = build_comicinfo_xml_for_epub(
            epub_path="E:/Books/測試系列/測試系列 - 畫冊.cbz",
            output_cbz_name="測試系列 - 畫冊.cbz",
            page_count=63,
            wiki_series=self._wiki(),
        )

        comicinfo = ComicInfo.from_xml_bytes(xml)
        self.assertEqual(comicinfo.title, "畫冊")
        self.assertEqual(comicinfo.format, "Special")

    @staticmethod
    def _wiki():
        return WikiSeriesMetadata(
            page_title="測試系列",
            pageid=1,
            page_url=None,
            wikibase_item=None,
            summary=None,
            main_manga=WikiMangaInfo(title="測試系列", volume_count=20),
        )


class RegionalEditionComicInfoTests(unittest.TestCase):
    def test_region_suffix_is_kept_in_metadata_while_output_name_omits_it(self):
        wiki = WikiSeriesMetadata(
            page_title="烏龍派出所",
            pageid=1,
            page_url=None,
            wikibase_item=None,
            summary=None,
            main_manga=WikiMangaInfo(title="烏龍派出所", volume_count=201),
        )

        xml = build_comicinfo_xml_for_epub(
            epub_path="V:/漫畫/烏龍派出所（台版）/卷001.epub",
            output_cbz_name="烏龍派出所 - 第001卷.cbz",
            page_count=200,
            wiki_series=wiki,
        )

        comicinfo = ComicInfo.from_xml_bytes(xml)
        self.assertEqual(comicinfo.series, "烏龍派出所（台版）")
        self.assertEqual(comicinfo.localized_series, "烏龍派出所（台版）")
        self.assertEqual(comicinfo.number, "1")


class DistinctWikiSeriesTests(unittest.TestCase):
    def test_main_series_and_sequel_keep_distinct_kavita_names_and_counts(self):
        wikitext = """
{{Infobox animanga/Manga
|冊數 = 全22冊
}}
{{Infobox animanga/Manga
|標題 = 殺手寓言 The second contact
|冊數 = 全9冊
}}
"""
        for series_name, expected_count in (
            ("殺手寓言", 22),
            ("殺手寓言 The second contact", 9),
        ):
            with self.subTest(series=series_name):
                wiki = build_series_metadata_from_wikitext(
                    wikitext,
                    page_title="殺手寓言",
                    pageid=1,
                    query=series_name,
                    series_sort="The Fable",
                )
                xml = build_comicinfo_xml_for_epub(
                    epub_path=f"E:/Books/{series_name}/卷01.epub",
                    output_cbz_name=f"{series_name} - 第001卷.cbz",
                    page_count=100,
                    wiki_series=wiki,
                )
                comicinfo = ComicInfo.from_xml_bytes(xml)
                self.assertEqual(comicinfo.series, series_name)
                self.assertEqual(comicinfo.localized_series, series_name)
                self.assertEqual(comicinfo.series_sort, series_name)
                self.assertEqual(comicinfo.count, expected_count)

    def test_baki_sequels_use_shared_wiki_page_and_distinct_manga_blocks(self):
        wikitext = """
{{Infobox animanga/Manga|標題=刃牙|冊數=全42卷}}
{{Infobox animanga/Manga|標題=刃牙II|冊數=全31卷}}
{{Infobox animanga/Manga|標題=範馬刃牙|冊數=全37卷}}
{{Infobox animanga/Manga|標題=刃牙道|冊數=全22卷}}
{{Infobox animanga/Manga|標題=刃牙道II|冊數=全17卷}}
"""
        page = WikiPageData(
            requested_title="刃牙",
            title="刃牙",
            pageid=1,
            wikitext=wikitext,
            defaultsort="Baki",
        )
        expected_counts = {
            "刃牙": 42,
            "範馬刃牙": 37,
            "刃牙II": 31,
            "刃牙道": 22,
            "刃牙道II": 17,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for series_name, expected_count in expected_counts.items():
                with self.subTest(series=series_name):
                    series_dir = Path(temp_dir) / series_name
                    series_dir.mkdir()
                    client = _FakeWikiClient(page)
                    wiki = load_exact_wiki_series_for_dir(
                        series_dir,
                        client=client,
                        use_cache=False,
                    )
                    self.assertEqual(client.page_data_calls, ["刃牙"])
                    self.assertEqual(wiki.main_manga.title, series_name)
                    self.assertEqual(wiki.main_manga.volume_count, expected_count)

                    xml = build_comicinfo_xml_for_epub(
                        epub_path=str(series_dir / "卷01.epub"),
                        output_cbz_name=f"{series_name} - 第001卷.cbz",
                        page_count=100,
                        wiki_series=wiki,
                    )
                    comicinfo = ComicInfo.from_xml_bytes(xml)
                    self.assertEqual(comicinfo.series, series_name)
                    self.assertEqual(comicinfo.series_sort, series_name)
                    self.assertEqual(comicinfo.count, expected_count)


if __name__ == "__main__":
    unittest.main()
