import argparse
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from comicinfo_repair import infer_volume_number, process_cbz, resolve_wiki_metadata
from metadata.wiki_models import WikiMangaInfo, WikiSeriesMetadata


def _repair_args(**overrides):
    values = {
        "wiki_url": None,
        "probe_dir": None,
        "wikitext": None,
        "page_title": None,
        "pageid": 0,
        "page_url": None,
        "wikibase_item": None,
        "summary": None,
        "query": None,
        "series_sort": None,
        "cbz": None,
        "series_title": None,
        "series_title_from_dir": None,
        "write_number": True,
        "write_volume": False,
        "language_iso": "zh-Hant-TW",
        "manga": "Yes",
        "age_rating": "Teen",
        "print_xml": False,
        "backup": False,
        "backup_suffix": ".bak",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class RepairMetadataTests(unittest.TestCase):
    def test_local_wikitext_uses_series_directory_as_edition_query(self):
        parsed = WikiSeriesMetadata(
            page_title="足球小將",
            pageid=1,
            page_url=None,
            wikibase_item=None,
            summary=None,
            main_manga=WikiMangaInfo(volume_count=21),
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "comicinfo_repair.build_series_metadata_from_file",
            return_value=parsed,
        ) as build:
            series_dir = Path(temp_dir) / "足球小將翼 (愛藏版)"
            series_dir.mkdir()
            wikitext_path = Path(temp_dir) / "05_wikitext.txt"
            wikitext_path.write_text("wiki source", encoding="utf-8")

            result = resolve_wiki_metadata(
                _repair_args(wikitext=str(wikitext_path)),
                series_dir,
            )

        self.assertIs(result, parsed)
        self.assertEqual(build.call_args.kwargs["query"], "足球小將翼 (愛藏版)")

    def test_explicit_query_still_overrides_directory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "comicinfo_repair.build_series_metadata_from_file",
        ) as build:
            series_dir = Path(temp_dir) / "Local Name"
            series_dir.mkdir()
            wikitext_path = Path(temp_dir) / "05_wikitext.txt"
            wikitext_path.write_text("wiki source", encoding="utf-8")

            resolve_wiki_metadata(
                _repair_args(wikitext=str(wikitext_path), query="文庫版"),
                series_dir,
            )

        self.assertEqual(build.call_args.kwargs["query"], "文庫版")

    def test_long_series_name_does_not_steal_volume_number(self):
        self.assertEqual(
            infer_volume_number("JOJO的奇妙冒險9 JOJO Lands - 012.cbz"),
            12,
        )

    def test_repair_writes_edition_count_and_kavita_year(self):
        wiki = WikiSeriesMetadata(
            page_title="足球小將",
            pageid=1,
            page_url="https://example.invalid/wiki",
            wikibase_item=None,
            summary="summary",
            main_manga=WikiMangaInfo(
                start="1981年",
                volume_count=21,
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            series_dir = Path(temp_dir) / "足球小將翼 (愛藏版)"
            series_dir.mkdir()
            cbz_path = series_dir / "足球小將翼 (愛藏版) - 第012卷.cbz"
            with zipfile.ZipFile(cbz_path, "w") as archive:
                archive.writestr("001.jpg", b"image-one")
                archive.writestr("002.jpg", b"image-two")

            process_cbz(cbz_path, _repair_args(), wiki, effective_write=True)

            with zipfile.ZipFile(cbz_path, "r") as archive:
                xml = archive.read("ComicInfo.xml").decode("utf-8")

        self.assertIn("<Series>足球小將翼 (愛藏版)</Series>", xml)
        self.assertIn("<Number>12</Number>", xml)
        self.assertIn("<Count>21</Count>", xml)
        self.assertIn("<Year>1981</Year>", xml)

    def test_repair_writes_unnumbered_anniversary_book_as_special(self):
        wiki = WikiSeriesMetadata(
            page_title="BLEACH",
            pageid=1,
            page_url="https://zh.wikipedia.org/wiki/BLEACH",
            wikibase_item=None,
            summary="summary",
            main_manga=WikiMangaInfo(volume_count=74),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            series_dir = Path(temp_dir) / "死神"
            series_dir.mkdir()
            cbz_path = series_dir / "死神 - 20周年紀念短篇.cbz"
            with zipfile.ZipFile(cbz_path, "w") as archive:
                archive.writestr("001.jpg", b"image")

            process_cbz(cbz_path, _repair_args(), wiki, effective_write=True)

            with zipfile.ZipFile(cbz_path, "r") as archive:
                xml = archive.read("ComicInfo.xml").decode("utf-8")

        self.assertIn("<Title>20周年紀念短篇</Title>", xml)
        self.assertIn("<Format>Special</Format>", xml)
        self.assertNotIn("<Number>", xml)
        self.assertIn("<Count>74</Count>", xml)

    def test_repair_writes_numbered_bonus_book_as_special(self):
        wiki = WikiSeriesMetadata(
            page_title="BLEACH",
            pageid=1,
            page_url=None,
            wikibase_item=None,
            summary=None,
            main_manga=WikiMangaInfo(volume_count=74),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            series_dir = Path(temp_dir) / "死神"
            series_dir.mkdir()
            cbz_path = series_dir / "死神 - 番外 第2卷.cbz"
            with zipfile.ZipFile(cbz_path, "w") as archive:
                archive.writestr("001.jpg", b"image")

            process_cbz(cbz_path, _repair_args(), wiki, effective_write=True)

            with zipfile.ZipFile(cbz_path, "r") as archive:
                xml = archive.read("ComicInfo.xml").decode("utf-8")

        self.assertIn("<Title>番外 第2卷</Title>", xml)
        self.assertIn("<Format>Special</Format>", xml)
        self.assertIn("<Number>2</Number>", xml)


if __name__ == "__main__":
    unittest.main()
