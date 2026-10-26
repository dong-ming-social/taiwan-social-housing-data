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
    def test_reserved_and_occupied_names(self):
        record = {"path": "/documents/yir/dongming/簡報評選結果.pdf", "stem": "簡報評選結果"}
        self.assertEqual(daily_update.unique_new_name(record, {}, set())[0], "dongming_簡報評選結果")
        self.assertEqual(daily_update.unique_new_name(record, {}, {("yir", "dongming_簡報評選結果")})[0], "dongming_簡報評選結果_2")

    def test_conversion_provenance_updates_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "source.pdf"
            pdf.write_bytes(b"new content")
            records = [{"path": f"/documents/yir/{site}/簡報評選結果.pdf", "stem": "簡報評選結果"}
                       for site in ("dongming", "liuzhangli")]
            downloaded = {r["path"]: pdf for r in records}
            def convert(rec, label):
                out = root / rec["bucket"] / (rec["output_stem"] + ".json")
                out.parent.mkdir(exist_ok=True)
                out.write_text(json.dumps({"metadata": {"pdf_sha256": daily_update.sha256(pdf)},
                    "source": {"official_pdf_url": daily_update.batch_convert.HOST + rec["path"]}}))
                return {"out": str(out)}
            with patch.object(daily_update, "REPO", root), patch.object(daily_update, "CONVERSION_LOG", root / "trace.jsonl"), patch.object(daily_update, "worklist_overrides", return_value={}), patch.object(daily_update.batch_convert, "convert", side_effect=convert):
                new, changed = daily_update.convert_changes(records, downloaded, {})
                self.assertEqual(len(new), 2)
                sources = daily_update.dataset_by_source()
                self.assertEqual(set(sources), set(downloaded))
                self.assertEqual(len({v[0] for v in sources.values()}), 2)
                self.assertEqual(daily_update.convert_changes(records, downloaded, sources), ([], []))
                pdf.write_bytes(b"updated content")
                new2, changed2 = daily_update.convert_changes(records, downloaded, sources)
                self.assertEqual(new2, [])
                self.assertEqual(changed2, new)
                self.assertEqual(set(daily_update.dataset_by_source()), set(downloaded))

    def test_explicit_conflicts_rejected_before_conversion(self):
        for stem in ("簡報評選結果", "occupied"):
            with self.subTest(stem=stem), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "yir").mkdir()
                (root / "yir/occupied.json").write_text("unchanged")
                pdf = root / "source.pdf"
                pdf.write_bytes(b"pdf")
                record = {"path": "/documents/yir/new.pdf", "stem": "new"}
                with patch.object(daily_update, "REPO", root), patch.object(daily_update, "CONVERSION_LOG", root / "trace.jsonl"), patch.object(daily_update, "worklist_overrides", return_value={record["path"]: {"output_stem": stem}}), patch.object(daily_update.batch_convert, "convert") as convert:
                    with self.assertRaisesRegex(ValueError, "explicit output.*conflicts"):
                        daily_update.convert_changes([record], {record["path"]: pdf}, {})
                    convert.assert_not_called()
                    self.assertEqual((root / "yir/occupied.json").read_text(), "unchanged")

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
