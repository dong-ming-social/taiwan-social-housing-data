#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the housing-query skill against the local dataset (no network)."""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPTS))
import build_catalog  # noqa: E402
import query  # noqa: E402

RENT_TABLE = "dongming/附件3_所得級距分級標準表及租金補貼表.json"


def run(*argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = query.main(["--repo", str(REPO), *argv])
    return code, json.loads(buffer.getvalue())


class CatalogTest(unittest.TestCase):
    def test_catalog_is_up_to_date(self):
        expected = build_catalog.render(build_catalog.build())
        actual = build_catalog.CATALOG.read_text(encoding="utf-8")
        self.assertEqual(actual, expected, "catalog.json 已過期，請執行 build_catalog.py")

    def test_catalog_covers_every_document(self):
        catalog = json.loads(build_catalog.CATALOG.read_text(encoding="utf-8"))
        paths = {doc["path"] for doc in catalog["documents"]}
        for path in paths:
            self.assertTrue((REPO / path).exists(), path)
        self.assertNotIn("api", {doc["folder"] for doc in catalog["documents"]})
        self.assertNotIn("laws", {doc["folder"] for doc in catalog["documents"]})
        self.assertEqual(catalog["document_count"], len(paths))
        self.assertEqual(catalog["document_count"], sum(f["document_count"] for f in catalog["folders"]))


class QueryTest(unittest.TestCase):
    def test_find_repo_from_explicit_path(self):
        self.assertEqual(query.find_repo(str(REPO)), str(REPO))

    def test_parse_pages(self):
        self.assertEqual(query.parse_pages("1, 3-5,8"), {1, 3, 4, 5, 8})
        self.assertEqual(query.parse_pages(None), set())

    def test_folders_keyword_matches_chinese_label(self):
        _, out = run("folders", "--keyword", "東明")
        self.assertIn("dongming", {f["folder"] for f in out["folders"]})

    def test_docs_filters_by_folder_and_type(self):
        _, out = run("docs", "--folder", "dongming", "--type", "rent_table")
        self.assertEqual([d["path"] for d in out["documents"]], [RENT_TABLE])
        self.assertEqual(out["documents"][0]["folder_label"], "東明社會住宅")

    def test_show_returns_field_and_citation(self):
        _, out = run("show", RENT_TABLE, "--field", "rent_after_subsidy", "--field", "nope", "--pages", "1")
        rows = out["structured_data"]["rent_after_subsidy"]
        self.assertTrue(all("source_pages" in row for row in rows))
        self.assertEqual(out["missing_fields"], ["nope"])
        self.assertTrue(out["citation"]["official_pdf_url"].startswith("https://rent.thurc.org.taipei/"))
        self.assertEqual([p["page"] for p in out["pages"]], [1])

    def test_search_returns_page_hits(self):
        _, out = run("search", "寵物", "--folder", "dongming", "--limit", "3")
        self.assertGreater(out["count"], 0)
        for hit in out["hits"]:
            self.assertIn("寵物", hit["snippet"])
            self.assertIsInstance(hit["page"], int)

    def test_locations_accepts_short_district_name(self):
        _, short = run("locations", "--district", "文山")
        _, code = run("locations", "--district", "wenshan")
        self.assertEqual(short["count"], code["count"])
        self.assertTrue(all(item["district"] == "文山區" for item in short["items"]))

    def test_law_article_and_changes(self):
        _, out = run("law", "--article", "23", "--changes")
        self.assertEqual([a["article_number"] for a in out["articles"]], ["23"])
        changed = {c["article_number"] for c in out["changes_from_previous"]["articles"]}
        self.assertEqual(changed, {"23"})

    def test_law_unknown_version(self):
        code, out = run("law", "--version", "999")
        self.assertEqual(code, 2)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
