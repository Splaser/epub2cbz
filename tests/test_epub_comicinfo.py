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
    def test_old_cache_without_date_alias_support_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "series.meta.json"
            cache_path.write_text(
                json.dumps({
                    "schema_version": 3,
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


if __name__ == "__main__":
    unittest.main()
