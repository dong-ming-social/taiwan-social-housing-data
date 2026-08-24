#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import daily_update  # noqa: E402
import portal_discovery  # noqa: E402


class PortalDiscoveryTests(unittest.TestCase):
    def test_splits_malformed_href_with_two_pdf_urls(self):
        href = (
            "https://rent.thurc.org.taipei/documents/elder-project/115/附件4_委託書.pdf "
            "https://rent.thurc.org.taipei/documents/elder-project/115/附件5_授權書.pdf"
        )
        self.assertEqual(
            portal_discovery.normalized_pdf_paths(href),
            [
                "/documents/elder-project/115/附件4_委託書.pdf",
                "/documents/elder-project/115/附件5_授權書.pdf",
            ],
        )

    def test_rejects_external_pdf(self):
        self.assertEqual(
            portal_discovery.normalized_pdf_paths("https://example.com/file.pdf"), []
        )

    def test_preserves_known_documents_when_attachment_page_fails(self):
        records = [
            {
                "path": "/documents/example/file.pdf",
                "src": ["example"],
                "active": True,
            },
            {
                "path": "/documents/retired/file.pdf",
                "src": ["example"],
                "active": False,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inventory.json"
            inventory.write_text(json.dumps(records), encoding="utf-8")
            found = {}
            from collections import defaultdict

            found = defaultdict(set)
            with patch.object(portal_discovery, "INVENTORY", inventory):
                portal_discovery.preserve_failed_attachment_source(found, "example")
        self.assertEqual(found["/documents/example/file.pdf"], {"example"})
        self.assertNotIn("/documents/retired/file.pdf", found)


class DailyUpdateTests(unittest.TestCase):
    def test_bucket_mapping(self):
        self.assertEqual(
            daily_update.output_bucket("/assets/attachments/a.pdf"), "citywide"
        )
        self.assertEqual(
            daily_update.output_bucket("/documents/yir/dongming/a.pdf"), "yir"
        )

    def test_inventory_preserves_missing_sources_as_inactive(self):
        records = [
            {
                "bucket": "one",
                "stem": "a",
                "path": "/documents/one/a.pdf",
                "have": True,
                "tier": "low",
                "src": ["old"],
                "dupe": False,
            },
            {
                "bucket": "two",
                "stem": "b",
                "path": "/documents/two/b.pdf",
                "have": True,
                "tier": "low",
                "src": ["old"],
                "dupe": False,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inventory.json"
            inventory.write_text(json.dumps(records), encoding="utf-8")
            with patch.object(daily_update, "INVENTORY", inventory), patch.object(
                daily_update, "MIN_DISCOVERY_RATIO", 0.5
            ):
                merged = daily_update.merge_inventory(
                    {"/documents/one/a.pdf": ["current"]},
                    {"/documents/one/a.pdf", "/documents/two/b.pdf"},
                )
        by_path = {record["path"]: record for record in merged}
        self.assertNotIn("active", by_path["/documents/one/a.pdf"])
        self.assertTrue(by_path["/documents/two/b.pdf"]["active"] is False)
        self.assertEqual(by_path["/documents/one/a.pdf"]["src"], ["current", "old"])

    def test_inventory_guardrail_rejects_large_drop(self):
        records = [
            {
                "bucket": "one",
                "stem": str(index),
                "path": f"/documents/one/{index}.pdf",
                "have": True,
                "tier": "low",
                "src": [],
                "dupe": False,
            }
            for index in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inventory.json"
            inventory.write_text(json.dumps(records), encoding="utf-8")
            with patch.object(daily_update, "INVENTORY", inventory):
                with self.assertRaisesRegex(RuntimeError, "discovery guardrail"):
                    daily_update.merge_inventory({}, set())


if __name__ == "__main__":
    unittest.main()
