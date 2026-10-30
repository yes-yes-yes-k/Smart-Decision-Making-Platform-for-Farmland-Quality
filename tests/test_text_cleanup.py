"""Text cleanup: headers, letter-spaced words, page numbers, and honest reporting."""
import unittest

from framework.upload.text_cleanup import (
    clean_chunks, clean_text, collapse_spaced_letters, repeated_lines, unmatched_fragments)

BODY = "Liming raised soil pH and reduced rice Cd uptake in the paddy field trial."
CHUNKS = [
    {"chunk_index": 0, "page": 1,
     "content": "B. Li et al. E c o t o x i c o l o g y a n d E n v i r o n m e n t a l S a f e t y 272 (2024)\n" + BODY},
    {"chunk_index": 1, "page": 2,
     "content": "B. Li et al. E c o t o x i c o l o g y a n d E n v i r o n m e n t a l S a f e t y 272 (2024)\n" + BODY},
    {"chunk_index": 2, "page": 3,
     "content": "B. Li et al. E c o t o x i c o l o g y a n d E n v i r o n m e n t a l S a f e t y 272 (2024)\n" + BODY},
    {"chunk_index": 3, "page": 4, "content": "12\n"},
]


class SpacingTests(unittest.TestCase):
    def test_collapses_letter_spaced_words(self):
        text, count = collapse_spaced_letters("E c o t o x i c o l o g y and Safety")
        self.assertEqual(text, "Ecotoxicology and Safety")
        self.assertEqual(count, 1)

    def test_short_spaced_run_is_collapsed(self):
        text, audit = clean_text("S a f e t y first\n" + BODY)
        self.assertIn("Safety first", text)
        self.assertEqual(audit["collapsed_words"], 1)

    def test_long_spaced_run_is_dropped_as_header(self):
        text, audit = clean_text("E c o t o x i c o l o g y a n d S a f e t y\n" + BODY)
        self.assertNotIn("E c o t o", text)
        self.assertEqual(audit["spaced_headers"], 1)

    def test_keeps_normal_text_untouched(self):
        text, count = collapse_spaced_letters(BODY)
        self.assertEqual(text, BODY)
        self.assertEqual(count, 0)


class HeaderTests(unittest.TestCase):
    def test_repeated_line_detected_across_pages(self):
        headers = repeated_lines([chunk["content"] for chunk in CHUNKS], minimum_pages=3, ratio=0.5)
        self.assertTrue(any("e c o t o x i c o l o g y" in header for header in headers))

    def test_header_and_page_number_removed_but_body_kept(self):
        cleaned, totals = clean_chunks([dict(chunk) for chunk in CHUNKS])
        self.assertIn(BODY, cleaned[0]["content"])
        self.assertNotIn("E c o t o x i c o l o g y", cleaned[0]["content"])
        self.assertEqual(cleaned[3]["content"], "")
        self.assertGreaterEqual(totals["dropped_lines"], 3)
        self.assertEqual(totals["collapsed_words"], 0)

    def test_body_wording_is_not_rewritten(self):
        text, _ = clean_text(BODY)
        self.assertEqual(text, BODY)

    def test_idempotent(self):
        once, _ = clean_chunks([dict(chunk) for chunk in CHUNKS])
        twice, _ = clean_chunks([dict(chunk) for chunk in once])
        self.assertEqual([chunk["content"] for chunk in once], [chunk["content"] for chunk in twice])

    def test_short_fragments_are_reported_not_fixed(self):
        problems = unmatched_fragments([{"chunk_index": 65, "content": "ethodology,\n8"}])
        self.assertEqual(problems[0]["chunk_index"], 65)
        self.assertEqual(problems[0]["length"], 13)


if __name__ == "__main__":
    unittest.main()
