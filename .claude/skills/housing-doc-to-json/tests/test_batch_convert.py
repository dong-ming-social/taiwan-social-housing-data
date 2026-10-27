#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import batch_convert  # noqa: E402
import daily_update  # noqa: E402


class BatchConvertDownloadTests(unittest.TestCase):
    PATH = "/documents/immediate/附件11_管理扣分規定.pdf"

    def test_retries_curl_failure_then_saves_valid_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = [
                subprocess.CompletedProcess([], 56, "", "connection reset"),
                subprocess.CompletedProcess([], 0, "", ""),
            ]

            def run(*args, **kwargs):
                result = results.pop(0)
                if result.returncode == 0:
                    Path(args[0][args[0].index("--output") + 1]).write_bytes(b"pdf")
                return result

            with patch.object(batch_convert, "PDFDIR", tmp), patch.object(
                batch_convert.subprocess, "run", side_effect=run
            ) as curl, patch.object(
                batch_convert, "valid_pdf", side_effect=lambda path: Path(path).read_bytes() == b"pdf"
            ), patch.object(batch_convert.time, "sleep") as sleep:
                result = Path(batch_convert.fetch(self.PATH, refresh=True))

            self.assertEqual(result.read_bytes(), b"pdf")
            self.assertEqual(curl.call_count, 2)
            command = curl.call_args_list[-1].args[0]
            self.assertIn("--show-error", command)
            self.assertEqual(command[command.index("--connect-timeout") + 1], "30")
            self.assertEqual(command[command.index("--max-time") + 1], "300")
            sleep.assert_called_once_with(2)
            self.assertFalse(Path(str(result) + ".download").exists())

    def test_exhausted_retries_report_curl_error_and_clean_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            def run(command, **kwargs):
                Path(command[command.index("--output") + 1]).write_bytes(b"partial")
                return subprocess.CompletedProcess([], 56, "", "HTTP/2 stream reset")

            with patch.object(batch_convert, "PDFDIR", tmp), patch.object(
                batch_convert.subprocess, "run", side_effect=run
            ) as curl, patch.object(batch_convert.time, "sleep") as sleep:
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"after 4 attempts.*curl exit 56: HTTP/2 stream reset.*https://",
                ):
                    batch_convert.fetch(self.PATH, refresh=True)

            self.assertEqual(curl.call_count, 4)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8])
            self.assertFalse(any(Path(tmp).glob("*.download")))

    def test_incomplete_pdf_is_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = [b"partial", b"pdf"]

            def run(command, **kwargs):
                Path(command[command.index("--output") + 1]).write_bytes(downloads.pop(0))
                return subprocess.CompletedProcess([], 0, "", "")

            with patch.object(batch_convert, "PDFDIR", tmp), patch.object(
                batch_convert.subprocess, "run", side_effect=run
            ) as curl, patch.object(
                batch_convert, "valid_pdf", side_effect=lambda path: Path(path).read_bytes() == b"pdf"
            ), patch.object(batch_convert.time, "sleep") as sleep:
                result = Path(batch_convert.fetch(self.PATH, refresh=True))

            self.assertEqual(result.read_bytes(), b"pdf")
            self.assertEqual(curl.call_count, 2)
            sleep.assert_called_once_with(2)


class DailyUpdateDownloadDiagnosticsTests(unittest.TestCase):
    def test_download_failure_is_written_to_conversion_log(self):
        record = {
            "bucket": "immediate",
            "stem": "附件11_管理扣分規定",
            "path": BatchConvertDownloadTests.PATH,
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            daily_update, "CONVERSION_LOG", Path(tmp) / "conversions.jsonl"
        ), patch.object(
            daily_update.batch_convert, "fetch", side_effect=RuntimeError("curl exit 56")
        ):
            with self.assertRaisesRegex(RuntimeError, "curl exit 56"):
                daily_update.download_all([record], 1)
            log = daily_update.CONVERSION_LOG.read_text(encoding="utf-8")

        self.assertIn('"status": "download_failed"', log)
        self.assertIn('"reason": "curl exit 56"', log)
        self.assertIn("%E9%99%84%E4%BB%B611_", log)


if __name__ == "__main__":
    unittest.main()
