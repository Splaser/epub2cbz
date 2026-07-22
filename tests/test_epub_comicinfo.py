import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from metadata.epub_comicinfo import load_exact_wiki_series_for_dir
from metadata.wiki_models import WikiMangaInfo, WikiPageData, WikiSeriesMetadata


class _FakeWikiClient:
    def __init__(self, page_data):
        self._page_data = page_data

    def page_data(self, title):
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


if __name__ == "__main__":
    unittest.main()
