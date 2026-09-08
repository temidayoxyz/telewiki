"""Tests for Wikipedia response parsing — fixtures only, no network."""

import unittest

from telewiki.wikipedia import (
    format_summary_html,
    parse_onthisday_response,
    parse_search_response,
    parse_summary_response,
    strip_tags,
    truncate,
)

SEARCH_FIXTURE = {
    "query": {
        "search": [
            {"title": "Black hole", "snippet": 'A <span class="searchmatch">black hole</span> is a region…'},
            {"title": "Black Hole (film)", "snippet": "Some film &amp; more"},
        ]
    }
}

SUMMARY_FIXTURE = {
    "type": "standard",
    "title": "Black hole",
    "description": "region of spacetime",
    "extract": "A black hole is a region of spacetime where gravity is so strong that nothing can escape.",
    "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Black_hole"}},
}

DISAMBIG_FIXTURE = {"type": "disambiguation", "title": "Mercury", "extract": "Mercury may refer to:"}

NOT_FOUND = {"type": "https://mediawiki.org/wiki/HyperSwitch/errors/not_found", "status": 404}

ONTHISDAY_FIXTURE = {
    "events": [
        {
            "year": 1969,
            "text": "Apollo 11 lands on the Moon.",
            "pages": [{"content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Apollo_11"}}}],
        },
        {"year": "bad-year", "text": "Undated-ish event.", "pages": []},
        {"text": "", "pages": []},
    ]
}

FEATURED_FIXTURE = {
    "tfa": {
        "type": "standard",
        "title": "Featured",
        "extract": "Featured article text.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Featured"}},
    }
}


class ParsingTests(unittest.TestCase):
    def test_search(self):
        results = parse_search_response(SEARCH_FIXTURE)
        self.assertEqual([r.title for r in results], ["Black hole", "Black Hole (film)"])
        self.assertEqual(results[0].snippet, "A black hole is a region…")
        self.assertEqual(results[1].snippet, "Some film & more")

    def test_search_empty(self):
        self.assertEqual(parse_search_response({}), [])
        self.assertEqual(parse_search_response({"query": {}}), [])

    def test_summary(self):
        summary = parse_summary_response(SUMMARY_FIXTURE)
        self.assertEqual(summary.title, "Black hole")
        self.assertEqual(summary.image, "https://upload.wikimedia.org/thumb.jpg")
        self.assertEqual(summary.url, "https://en.wikipedia.org/wiki/Black_hole")
        self.assertFalse(summary.is_disambiguation)

    def test_disambiguation_flag(self):
        summary = parse_summary_response(DISAMBIG_FIXTURE)
        self.assertTrue(summary.is_disambiguation)

    def test_not_found(self):
        self.assertIsNone(parse_summary_response(NOT_FOUND))
        self.assertIsNone(parse_summary_response({}))

    def test_onthisday(self):
        events = parse_onthisday_response(ONTHISDAY_FIXTURE)
        self.assertEqual(len(events), 2)  # empty-text entry skipped
        self.assertEqual(events[0].year, 1969)
        self.assertEqual(events[0].url, "https://en.wikipedia.org/wiki/Apollo_11")
        self.assertIsNone(events[1].year)  # unparseable year -> None, kept
        self.assertIsNone(events[1].url)

    def test_featured_uses_summary_shape(self):
        summary = parse_summary_response(FEATURED_FIXTURE["tfa"])
        self.assertEqual(summary.title, "Featured")


class FormatTests(unittest.TestCase):
    def test_strip_tags(self):
        self.assertEqual(strip_tags("<b>x</b> &amp; <i>y</i>"), "x & y")

    def test_truncate_short(self):
        self.assertEqual(truncate("hello", 10), "hello")

    def test_truncate_word_boundary(self):
        out = truncate("one two three four", 9)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 10)

    def test_format_escapes_and_links(self):
        summary = parse_summary_response(SUMMARY_FIXTURE)
        out = format_summary_html(summary)
        self.assertIn("<b>Black hole</b>", out)
        self.assertIn("Read more on Wikipedia", out)
        self.assertIn(summary.url, out)

    def test_format_escapes_html_in_text(self):
        summary = parse_summary_response({**SUMMARY_FIXTURE, "extract": "<script>alert(1)</script>"})
        out = format_summary_html(summary)
        self.assertNotIn("<script>", out)


if __name__ == "__main__":
    unittest.main()
