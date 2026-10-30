import hashlib
from pathlib import Path
import tempfile
import unittest

import fitz

from framework.upload.pdf_layout import extract_page, map_old_chunks, parse_layout_pdf, versioned_chunks
from framework.upload.document_parser import parse_document


class LayoutV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"columns.pdf"
        pdf = fitz.open()
        page = pdf.new_page(width=600, height=800)
        # Write alternating blocks to force native stream order to be wrong.
        for side, x in (("LEFT_START", 30), ("RIGHT_START", 320), ("LEFT_END", 30), ("RIGHT_END", 320)):
            y = 60 if side.endswith("START") else 340
            remaining = page.insert_textbox(fitz.Rect(x, y, x+250, y+250), side+"\n"+(side.split('_')[0]+" sentence. ")*40, fontsize=10)
            self.assertGreaterEqual(remaining, 0, "Fixture text must fit on its page")
        pdf.save(self.path)
        pdf.close()

    def test_columns_read_in_order_and_each_codepoint_maps_to_page(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        document = parse_layout_pdf(self.path)
        p = document["pages"][0]
        self.assertEqual(p["reading_order"], "two_column_geometry")
        self.assertLess(p["text"].index("LEFT_END"), p["text"].index("RIGHT_START"))
        self.assertEqual(len(p["text"]), len(p["char_bboxes"]))
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(document["parse_version"], parse_layout_pdf(self.path)["parse_version"])

    def test_duplicates_removed_and_off_page_text_not_imported(self):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((50, 70), "Blue and red", fontsize=12)
        page.insert_text((50, 70), "Blue and red", fontsize=12)
        page.insert_text((50, -20), "FOR PEER REVIEW", fontsize=12)
        result = extract_page(page)
        self.assertEqual(result["text"].count("Blue and red"), 1)
        self.assertNotIn("FOR PEER REVIEW", result["text"])
        self.assertGreater(result["duplicate_glyphs_removed"], 0)
        pdf.close()

    def test_chunk_offsets_rebuild_and_old_mixed_text_never_silently_maps(self):
        doc = parse_layout_pdf(self.path)
        chunk_set = versioned_chunks(doc, size=200, overlap=30)
        for c in chunk_set["chunks"]:
            self.assertEqual(c["content"], doc["pages"][c["page"]-1]["text"][c["page_start"]:c["page_end"]])
        mapped = map_old_chunks([{"chunk_index": 0, "page": 1, "content": "LEFT_START RIGHT_START"}], doc, chunk_set)
        self.assertEqual(mapped[0]["state"], "same_page_only_no_span_transfer")
        self.assertIsNone(mapped[0]["new_page_start"])

    def test_explicit_profile_returns_version_and_native_caj_requires_conversion(self):
        parsed = parse_document(str(self.path), "pdf", page_aware=True, pdf_profile="pdf-layout-v2")
        self.assertEqual(parsed.parse_metadata["parser_profile"], "pdf-layout-v2")
        self.assertEqual(parsed[0][1], parsed.layout_document["pages"][0]["text"])
        caj = Path(self.temp.name)/"native.caj"
        caj.write_bytes(b"CAJpayload")
        with self.assertRaisesRegex(ValueError, "native_CAJ"):
            parse_document(str(caj), "caj", pdf_profile="pdf-layout-v2")


if __name__ == "__main__":
    unittest.main()
