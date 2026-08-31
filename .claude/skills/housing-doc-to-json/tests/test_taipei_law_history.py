#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "taipei_law_history"
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPTS))

import taipei_law_history as law  # noqa: E402


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def article_page(numbers, suffix=""):
    items = "".join(
        (
            '<li><div class="row"><div class="col-no">第 '
            f'{number} 條</div><div class="law-articlepre">'
            f"第{number}條內容{suffix}。</div></div></li>"
        )
        for number in numbers
    )
    return f'<article class="col-article"><ul class="law">{items}</ul></article>'


class ParserTests(unittest.TestCase):
    def test_parses_history_and_sorts_oldest_first(self):
        parsed = law.parse_history(fixture("history.html"), "FL071776")
        self.assertEqual(parsed["law_code"], "北市13－06－4001")
        self.assertEqual(parsed["name"], "臺北市社會住宅出租辦法")
        self.assertEqual(
            [item["date"] for item in parsed["revisions"]],
            ["2013-10-17", "2015-12-31", "2017-08-03", "2023-10-27"],
        )
        self.assertIsNone(parsed["revisions"][0]["amended_text_url"])
        self.assertNotIn("date=", parsed["revisions"][-1]["full_text_url"])

    def test_parses_articles_and_preserves_newlines(self):
        articles = law.parse_articles(fixture("articles.html"))
        self.assertEqual([item["article_number"] for item in articles], ["1", "2"])
        self.assertEqual(articles[0]["text"], "第一行\n第二行")

    def test_rejects_empty_or_malformed_pages(self):
        with self.assertRaisesRegex(law.LawScrapeError, "no revisions"):
            law.parse_history("<html></html>", "FL071776")
        with self.assertRaisesRegex(law.LawScrapeError, "no articles"):
            law.parse_articles("<html></html>")


class DatasetTests(unittest.TestCase):
    def test_builds_four_versions_and_official_2015_amendments(self):
        history = law.parse_history(fixture("history.html"), "FL071776")
        full_counts = {
            "20131017": 22,
            "20151231": 22,
            "20170803": 22,
            "latest": 24,
        }
        amendments = {
            "20151231": [4, 5, 6, 12, 14, 15],
            "20170803": list(range(1, 23)),
            "latest": list(range(1, 25)),
        }

        pages = {history["source_url"]: fixture("history.html")}
        for revision in history["revisions"]:
            query = urllib_date(revision["full_text_url"])
            pages[revision["full_text_url"]] = article_page(
                range(1, full_counts[query] + 1), suffix=query
            )
            if revision["amended_text_url"]:
                pages[revision["amended_text_url"]] = article_page(amendments[query])

        dataset = law.build_dataset("FL071776", pages.__getitem__)
        self.assertEqual([item["article_count"] for item in dataset["versions"]], [22, 22, 22, 24])
        self.assertEqual(
            dataset["versions"][1]["official_amended_article_numbers"],
            ["4", "5", "6", "12", "14", "15"],
        )
        self.assertEqual(len(dataset["content_hash"]), 64)

    def test_diff_detects_changes_but_ignores_whitespace(self):
        previous = [
            {"article_number": "1", "text": "相同 文字"},
            {"article_number": "2", "text": "舊文字"},
            {"article_number": "3", "text": "刪除"},
        ]
        current = [
            {"article_number": "1", "text": "相同\n文字"},
            {"article_number": "2", "text": "新文字"},
            {"article_number": "4", "text": "新增"},
        ]
        result = law.diff_articles(previous, current)
        self.assertEqual(
            result["summary"],
            {"added": ["4"], "removed": ["3"], "modified": ["2"]},
        )

    def test_atomic_writer_is_idempotent_and_guards_revision_loss(self):
        dataset = {"content_hash": "a" * 64, "versions": [{"date": "2020-01-01"}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "law.json"
            self.assertTrue(law.write_if_changed(dataset, output))
            original_stat = output.stat().st_mtime_ns
            self.assertFalse(law.write_if_changed(dataset, output))
            self.assertEqual(output.stat().st_mtime_ns, original_stat)

            shorter = {"content_hash": "b" * 64, "versions": []}
            with self.assertRaisesRegex(law.LawScrapeError, "fewer revisions"):
                law.write_if_changed(shorter, output)
            self.assertEqual(json.loads(output.read_text())["content_hash"], "a" * 64)

    def test_fetcher_reports_repeated_http_failure(self):
        fetcher = law.Fetcher(timeout=0.01, attempts=2, delay=0)
        error = law.urllib.error.URLError("offline")
        with patch.object(law.urllib.request, "urlopen", side_effect=error), patch.object(
            law.time, "sleep"
        ):
            with self.assertRaisesRegex(law.LawScrapeError, "after 2 attempts"):
                fetcher("https://example.invalid/law")


class CommittedDatasetTests(unittest.TestCase):
    def test_committed_dataset_has_verified_original_versions(self):
        path = REPO / "laws" / "taipei" / "FL071776.json"
        dataset = json.loads(path.read_text(encoding="utf-8"))
        original_versions = dataset["versions"][:4]
        self.assertEqual(
            [item["date"] for item in original_versions],
            ["2013-10-17", "2015-12-31", "2017-08-03", "2023-10-27"],
        )
        self.assertEqual(
            [item["article_count"] for item in original_versions], [22, 22, 22, 24]
        )
        self.assertEqual(
            original_versions[1]["official_amended_article_numbers"],
            ["4", "5", "6", "12", "14", "15"],
        )

        expected_hash = dataset.pop("content_hash")
        canonical = json.dumps(
            dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected_hash)


def urllib_date(url):
    if "date=" not in url:
        return "latest"
    return url.rsplit("date=", 1)[1]


if __name__ == "__main__":
    unittest.main()
