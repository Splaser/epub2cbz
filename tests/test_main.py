import io
import unittest
from contextlib import redirect_stdout

from main import choose_wiki_candidate
from metadata.wiki_models import WikiSearchItem


class WikiCandidateSelectionTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            WikiSearchItem(
                title="三國志 (橫山光輝漫畫)",
                pageid=1,
                snippet='<span class="searchmatch">橫山光輝</span>創作的漫畫',
            ),
            WikiSearchItem(
                title="三國演義",
                pageid=2,
                snippet="中國古典小說",
            ),
            WikiSearchItem(
                title="三國 (電視劇)",
                pageid=3,
                snippet="中國電視劇",
            ),
        ]

    def test_number_selects_requested_wiki_title(self):
        answers = iter(["invalid", "2"])
        output = io.StringIO()

        with redirect_stdout(output):
            selected = choose_wiki_candidate(
                "三国志",
                self.candidates,
                input_func=lambda _: next(answers),
            )

        self.assertEqual(selected, "三國演義")
        self.assertIn("1. 三國志 (橫山光輝漫畫) — 橫山光輝創作的漫畫", output.getvalue())
        self.assertIn("输入无效", output.getvalue())

    def test_zero_skips_wiki_metadata(self):
        selected = choose_wiki_candidate(
            "三国志",
            self.candidates,
            input_func=lambda _: "0",
        )

        self.assertIsNone(selected)

    def test_closed_input_skips_without_crashing(self):
        def closed_input(_):
            raise EOFError

        selected = choose_wiki_candidate(
            "三国志",
            self.candidates,
            input_func=closed_input,
        )

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
