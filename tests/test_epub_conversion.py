import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from builder.cbz_builder import make_cbz
from main import epub_to_cbz_fixed, main
from metadata.comicinfo import ComicInfo
from metadata.wiki_models import WikiMangaInfo, WikiSeriesMetadata


class EpubConversionTests(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.series_dir = Path(temp_dir.name) / "Example"
        self.series_dir.mkdir()
        self.epub = self.series_dir / "vol1.epub"
        self.cbz = self.series_dir / "Example - 第001卷.cbz"

    @staticmethod
    def png(color):
        with io.BytesIO() as output:
            Image.new("RGB", (12, 8), color).save(output, format="PNG")
            return output.getvalue()

    def write_epub(self, spine, files, *, opf="OEBPS/content.opf", credits=None):
        package = ET.Element("package")
        if credits:
            metadata = ET.SubElement(package, "metadata")
            for field, value in credits.items():
                ET.SubElement(metadata, f"{{http://purl.org/dc/elements/1.1/}}{field}").text = value
        manifest = ET.SubElement(package, "manifest")
        reading_order = ET.SubElement(package, "spine")
        for index, href in enumerate(spine):
            item_id = f"p{index}"
            ET.SubElement(manifest, "item", {"id": item_id, "href": href})
            ET.SubElement(reading_order, "itemref", {"idref": item_id})
        with zipfile.ZipFile(self.epub, "w") as archive:
            if opf != "vol.opf":
                archive.writestr(
                    "META-INF/container.xml",
                    f'<container><rootfiles><rootfile full-path="{opf}"/></rootfiles></container>',
                )
            archive.writestr(opf, ET.tostring(package))
            for name, content in files.items():
                archive.writestr(str(Path(opf).parent.joinpath(name).as_posix()), content)

    def test_nested_opf_preserves_spine_order_white_pages_and_rotation_per_reference(self):
        red, blue, white = (self.png(color) for color in ("red", "blue", "white"))
        self.write_epub(
            ["html/z.xhtml", "html/a.xhtml", "images/white.png", "html/repeat.xhtml"],
            {
                "html/z.xhtml": '<img src="../images/a/page.png" kmoetag="rotate:1"/>',
                "html/a.xhtml": '<img src="../images/b/page.png" kmoetag="rotate:1"/>',
                "html/repeat.xhtml": '<img src="../images/a/page.png" kmoetag="rotate:0"/>',
                "images/a/page.png": red,
                "images/b/page.png": blue,
                "images/white.png": white,
                "images/unused.png": self.png("green"),
            },
        )
        wiki = WikiSeriesMetadata(
            page_title="Example", pageid=1, page_url=None, wikibase_item=None,
            summary=None, main_manga=WikiMangaInfo(title="Example", volume_count=1),
        )

        epub_to_cbz_fixed(self.epub, wiki)

        with zipfile.ZipFile(self.cbz) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(
                archive.namelist(),
                ["0001.png", "0002.png", "0003.png", "0004.png", "ComicInfo.xml"],
            )
            for name, color in (("0001.png", (255, 0, 0)), ("0002.png", (0, 0, 255))):
                with Image.open(io.BytesIO(archive.read(name))) as page:
                    self.assertEqual(page.size, (8, 12))
                    self.assertEqual(page.getpixel((0, 0)), color)
            self.assertEqual(archive.read("0003.png"), white)
            self.assertEqual(archive.read("0004.png"), red)
            self.assertEqual(archive.getinfo("0004.png").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.getinfo("ComicInfo.xml").compress_type, zipfile.ZIP_DEFLATED)
            info = ComicInfo.from_xml_bytes(archive.read("ComicInfo.xml"))
            self.assertEqual(info.page_count, 4)

    def test_container_takes_precedence_over_legacy_opf(self):
        self.write_epub(["page.png"], {"page.png": self.png("red")})
        with zipfile.ZipFile(self.epub, "a") as archive:
            archive.writestr("vol.opf", "invalid XML")

        epub_to_cbz_fixed(self.epub)

        with zipfile.ZipFile(self.cbz) as archive:
            self.assertEqual(archive.namelist(), ["0001.png"])

    def test_series_title_override_matches_output_name_and_comicinfo(self):
        self.write_epub(["page.png"], {"page.png": self.png("red")})
        wiki = WikiSeriesMetadata(
            page_title="Example Wiki", pageid=1, page_url=None, wikibase_item=None,
            summary=None, main_manga=WikiMangaInfo(title="Example Wiki", volume_count=1),
        )

        epub_to_cbz_fixed(self.epub, wiki, series_title="舊版系列")

        with zipfile.ZipFile(self.series_dir / "舊版系列 - 第001卷.cbz") as archive:
            info = ComicInfo.from_xml_bytes(archive.read("ComicInfo.xml"))
        self.assertEqual((info.series, info.series_sort, info.localized_series), ("舊版系列",) * 3)
        self.assertEqual(info.number, "1")
        self.assertFalse(self.cbz.exists())

    def test_cli_merges_upper_and_lower_with_unique_pages_and_combined_tags(self):
        upper = self.series_dir / "[Kmoe][Example]卷01.上.epub"
        lower = self.series_dir / "[Kmoe][Example]卷01.下.epub"
        pages = {
            "cover.png": self.png("red"),
            "upper.png": self.png("blue"),
            "overlap1.png": self.png("green"),
            "overlap2.png": self.png("yellow"),
            "lower.png": self.png("orange"),
            "theendinfo.png": self.png("white"),
        }
        for epub, order in (
            (upper, ["cover.png", "upper.png", "overlap1.png", "overlap2.png", "theendinfo.png"]),
            (lower, ["cover.png", "overlap1.png", "overlap2.png", "lower.png", "theendinfo.png"]),
        ):
            self.epub = epub
            self.write_epub(order, {name: pages[name] for name in order})
        wiki = WikiSeriesMetadata(
            page_title="Example", pageid=1, page_url=None, wikibase_item=None,
            summary=None, main_manga=WikiMangaInfo(title="Example"),
        )

        # Passing the lower half still puts the upper half first.
        with patch("sys.argv", ["epub2cbz", str(lower)]), patch(
            "main.load_wiki_metadata_for_main", return_value=wiki
        ):
            self.assertEqual(main(), 0)

        with zipfile.ZipFile(self.cbz) as archive:
            order = ["cover.png", "upper.png", "overlap1.png", "overlap2.png", "lower.png", "theendinfo.png"]
            self.assertEqual(
                [archive.read(f"{index:04}.png") for index in range(1, 7)],
                [pages[name] for name in order],
            )
            info = ComicInfo.from_xml_bytes(archive.read("ComicInfo.xml"))
            self.assertEqual((info.number, info.page_count, info.count), ("1", 6, 1))
            self.assertIsNone(archive.testzip())
        self.assertEqual(list(self.series_dir.glob("*.cbz")), [self.cbz])

    def test_batch_keeps_unpaired_part_and_preserves_distinct_covers(self):
        for name, color in (("卷01上", "red"), ("卷01下", "blue"), ("卷02.上", "green")):
            self.epub = self.series_dir / (name + ".epub")
            self.write_epub(["cover.png"], {"cover.png": self.png(color)})

        with patch("sys.argv", ["epub2cbz"]), patch("main.get_base_dir", return_value=str(self.series_dir)), patch(
            "main.load_wiki_metadata_for_main", return_value=None
        ):
            self.assertEqual(main(), 0)
        with zipfile.ZipFile(self.cbz) as archive:
            self.assertEqual(archive.read("0001.png"), self.png("red"))
            self.assertEqual(archive.read("0002.png"), self.png("blue"))
            info = ComicInfo.from_xml_bytes(archive.read("ComicInfo.xml"))
            self.assertEqual((info.series, info.number, info.page_count, info.count), ("Example", "1", 2, 2))
        with zipfile.ZipFile(self.series_dir / "Example - 第002卷（上）.cbz") as archive:
            self.assertEqual(archive.read("0001.png"), self.png("green"))

    def test_no_wiki_uses_epub_creator_and_explicit_publisher(self):
        self.write_epub(
            ["page.png"], {"page.png": self.png("red")},
            credits={"creator": "水木茂", "publisher": "Kmoe"},
        )
        with patch("main.load_wiki_metadata_for_main") as lookup:
            for publisher_args, expected in (([], None), (["--publisher", "遠足文化"], "遠足文化")):
                with self.subTest(publisher=expected), patch(
                    "sys.argv", ["epub2cbz", "--no-wiki", *publisher_args, str(self.epub)]
                ):
                    self.assertEqual(main(), 0)
                    with zipfile.ZipFile(self.cbz) as archive:
                        info = ComicInfo.from_xml_bytes(archive.read("ComicInfo.xml"))
                    self.assertEqual((info.writer, info.publisher, info.number), (["水木茂"], expected, "1"))
            lookup.assert_not_called()

    def test_legacy_opf_keeps_white_page_and_skips_explicit_ad_document(self):
        white = self.png("white")
        self.write_epub(
            ["page.xhtml", "ad.xhtml"],
            {
                "page.xhtml": '<img src="white.png"/>',
                "ad.xhtml": '<img src="ad.png"/>',
                "white.png": white,
                "ad.png": self.png("red"),
            },
            opf="vol.opf",
        )

        epub_to_cbz_fixed(self.epub)

        with zipfile.ZipFile(self.cbz) as archive:
            self.assertEqual(archive.namelist(), ["0001.png"])
            self.assertEqual(archive.read("0001.png"), white)

    def test_zero_pages_never_create_or_replace_an_archive(self):
        self.write_epub(["page.xhtml"], {"page.xhtml": "<p>No image pages</p>"})
        with self.assertRaisesRegex(ValueError, "EPUB has no image pages"):
            epub_to_cbz_fixed(self.epub)
        self.assertFalse(self.cbz.exists())

        self.cbz.write_bytes(b"existing output")
        with self.assertRaisesRegex(ValueError, "without image pages"):
            make_cbz(iter(()), self.cbz, comicinfo_xml=b"<ComicInfo/>")
        self.assertEqual(self.cbz.read_bytes(), b"existing output")

    def test_missing_or_corrupt_page_preserves_existing_archive(self):
        self.cbz.write_bytes(b"existing output")
        for payload, error, message in (
            (None, FileNotFoundError, "Missing EPUB image"),
            (b"invalid image", ValueError, "Cannot prepare EPUB page"),
        ):
            with self.subTest(payload=payload):
                files = {
                    "page.xhtml": '<img src="good.png"/><img src="bad.png"/>',
                    "good.png": self.png("red"),
                }
                if payload is not None:
                    files["bad.png"] = payload
                self.write_epub(["page.xhtml"], files)

                with self.assertRaisesRegex(error, message):
                    epub_to_cbz_fixed(self.epub)
                self.assertEqual(self.cbz.read_bytes(), b"existing output")

    def test_spine_and_html_paths_cannot_leave_epub_directory(self):
        for href, source in (
            ("../../page.png", "<p>Empty</p>"),
            ("page.xhtml", '<img src="%2e%2e/%2e%2e/page.png"/>'),
        ):
            with self.subTest(href=href):
                self.write_epub([href], {"page.xhtml": source})

                with self.assertRaisesRegex(ValueError, "leaves the EPUB directory"):
                    epub_to_cbz_fixed(self.epub)
                self.assertFalse(self.cbz.exists())

    def test_missing_spine_document_does_not_package_the_remaining_pages(self):
        self.write_epub(["page.png", "missing.xhtml"], {"page.png": self.png("red")})

        with self.assertRaisesRegex(FileNotFoundError, "Missing EPUB spine file"):
            epub_to_cbz_fixed(self.epub)

        self.assertFalse(self.cbz.exists())
