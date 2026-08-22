import unittest

from metadata.wiki_models import WikiMangaInfo, WikiSeriesMetadata
from metadata.wiki_to_comicinfo import wiki_series_to_comicinfo


class WikiTagFilteringTests(unittest.TestCase):
    def test_only_wikipedia_maintenance_categories_are_filtered(self):
        garbage_categories = [
            "CS1含有日語文本 (ja)",
            "CS1日语来源 (ja)",
            "CS1英语来源 (en)",
            "引文格式1錯誤：日期",
            "引用格式1错误：日期",
            "模板调用错误：参数无效",
            "含有連結內容需訂閱查看的頁面",
            "含有韓語的條目",
            "使用ISBN魔术链接的页面",
            "維基共享資源分類鏈接使用了維基數據上的匹配項",
            "維基百科和維基數據上的官方網站不同",
            "與維基數據不同的Twitter用戶名",
            "與維基數據相同的Twitter用戶名",
        ]
        useful_categories = [
            "2016年日本漫畫作品",
            "2020年完結漫畫",
            "Crunchyroll動畫獎得主",
            "手塚治虫文化獎獲獎作品",
            "週刊少年Jump連載作品",
            "日本漫畫作品",
        ]

        comic_info = wiki_series_to_comicinfo(
            self._wiki(categories=[*garbage_categories, *useful_categories]),
            1,
        )

        self.assertEqual(
            comic_info.tags,
            ["奇幻", "週刊少年Jump", *useful_categories],
        )

    def test_content_categories_are_kept_and_deduplicated(self):
        categories = [
            "兄弟姊妹題材作品",
            "冒險",
            "劍士主角題材作品",
            "吸血鬼題材漫畫",
            "報復題材漫畫",
            "大正時代背景漫畫",
            "奇幻漫畫",
            "孤兒題材作品",
            "少年漫畫",
            "戰鬥",
            "日本刀題材作品",
            "時代劇",
            "東京背景漫畫",
            "氣功題材作品",
            "獵奇",
            "鬼滅之刃",
            "黑暗奇幻",
        ]

        comic_info = wiki_series_to_comicinfo(
            self._wiki(categories=categories),
            1,
        )

        self.assertEqual(
            comic_info.tags,
            ["奇幻", "週刊少年Jump", *categories],
        )

    def test_wiki_genres_and_categories_map_to_stable_kavita_genres(self):
        wiki = self._wiki(categories=[
            "冒險漫畫",
            "黑暗奇幻",
            "獵奇",
            "大正時代背景漫畫",
            "引文格式1錯誤：日期",
        ])
        wiki.main_manga.genre = ["動作", "科幻", "戀愛喜劇"]

        comic_info = wiki_series_to_comicinfo(wiki, 1)

        self.assertEqual(
            comic_info.genre,
            [
                "Action",
                "Science fiction",
                "Romance",
                "Comedy",
                "Adventure",
                "Fantasy",
                "Horror",
                "Historical",
            ],
        )

    def test_publisher_region_prefix_is_removed(self):
        wiki = self._wiki(categories=[])
        wiki.main_manga.taiwan_publishers = ["臺灣： 青文出版社"]
        wiki.main_manga.japan_publishers = ["日本：集英社"]
        wiki.main_manga.publishers = ["日本：集英社", "臺灣： 青文出版社"]

        comic_info = wiki_series_to_comicinfo(wiki, 1)

        self.assertEqual(comic_info.publisher, "青文出版社")

    def test_non_region_publisher_prefix_is_preserved(self):
        wiki = self._wiki(categories=[])
        wiki.main_manga.taiwan_publishers = ["時報文化：漫畫部"]

        comic_info = wiki_series_to_comicinfo(wiki, 1)

        self.assertEqual(comic_info.publisher, "時報文化：漫畫部")

    def test_japanese_publisher_is_not_used_for_traditional_chinese_edition(self):
        wiki = self._wiki(categories=[])
        wiki.main_manga.japan_publishers = ["日本：集英社"]
        wiki.main_manga.publishers = ["日本：集英社"]

        comic_info = wiki_series_to_comicinfo(wiki, 1)

        self.assertIsNone(comic_info.publisher)

    @staticmethod
    def _wiki(*, categories):
        return WikiSeriesMetadata(
            page_title="測試漫畫",
            pageid=1,
            page_url=None,
            wikibase_item=None,
            summary=None,
            main_manga=WikiMangaInfo(
                title="測試漫畫",
                genre=["奇幻"],
                magazine=["週刊少年Jump"],
            ),
            categories=categories,
        )


if __name__ == "__main__":
    unittest.main()
