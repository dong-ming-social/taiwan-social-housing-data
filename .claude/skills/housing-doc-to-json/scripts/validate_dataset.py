#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the complete social-housing JSON dataset and its provenance."""

import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
EXPECTED_PUBLISHER = "臺北市住宅及都市更新中心"
EXPECTED_OWNER = "臺北市政府都市發展局"
REQUIRED_TOP_LEVEL = {"metadata", "source", "sections", "structured_data", "pages"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def fail(errors, path, message):
    errors.append(f"{path}: {message}")


def main():
    errors = []
    urls = Counter()
    source_paths = set()
    page_total = 0
    ocr_required = []
    files = sorted(REPO.glob("*/*.json"))

    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(errors, path, f"invalid JSON: {exc}")
            continue

        missing = REQUIRED_TOP_LEVEL - set(doc)
        if missing:
            fail(errors, path, f"missing top-level keys: {sorted(missing)}")
            continue

        metadata = doc["metadata"]
        source = doc["source"]
        pages = doc["pages"]
        page_count = metadata.get("page_count")
        page_total += page_count if isinstance(page_count, int) else 0

        if page_count != len(pages):
            fail(errors, path, f"page_count {page_count!r} != {len(pages)} pages")
        if [page.get("page") for page in pages] != list(range(1, len(pages) + 1)):
            fail(errors, path, "pages are not numbered consecutively from 1")
        if not SHA256_RE.fullmatch(str(metadata.get("pdf_sha256", ""))):
            fail(errors, path, "missing or invalid metadata.pdf_sha256")

        url = source.get("official_pdf_url", "")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "rent.thurc.org.taipei":
            fail(errors, path, f"invalid official_pdf_url: {url!r}")
        else:
            urls[url] += 1
            source_paths.add(urllib.parse.unquote(parsed.path))
        if source.get("publisher") != EXPECTED_PUBLISHER:
            fail(errors, path, "publisher is missing or incorrect")
        if source.get("website_owner") != EXPECTED_OWNER:
            fail(errors, path, "website_owner is missing or incorrect")
        attribution = source.get("attribution", "")
        if EXPECTED_PUBLISHER not in attribution or not attribution.strip():
            fail(errors, path, "source attribution is missing or incomplete")

        if doc["structured_data"].get("requires_ocr"):
            ocr_required.append(path)

    for url, count in urls.items():
        if count > 1:
            errors.append(f"source collision: {url} is used by {count} JSON files")

    inventory_path = (
        REPO / ".claude/skills/housing-doc-to-json/batch/portal_inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    expected_paths = {record["path"] for record in inventory if not record.get("dupe")}
    if len(files) != len(expected_paths):
        errors.append(
            f"dataset: expected {len(expected_paths)} JSON files from inventory, "
            f"found {len(files)}"
        )
    for path in sorted(expected_paths - source_paths):
        errors.append(f"inventory source missing from dataset: {path}")
    for path in sorted(source_paths - expected_paths):
        errors.append(f"dataset source missing from inventory: {path}")

    forbidden = [
        REPO / "yir" / "簡報評選結果.json",
        REPO / "zhongnan" / "永平社會住宅住戶規約手冊(114年12月版).json",
        REPO / "nangangdepot1" / "南港機廠社1區宅手冊.json",
    ]
    for path in forbidden:
        if path.exists():
            fail(errors, path, "explicit duplicate/colliding output must not be present")

    required = [
        REPO / "7-in-one-2" / "附件8_管理扣分規定.json",
        REPO / "yir" / "東明社宅及興隆E區社宅青創計畫第二階段簡報評選結果.json",
        REPO / "yir" / "六張犁社會住宅1與2區青年創新回饋計畫簡報評選結果.json",
    ]
    for path in required:
        if not path.exists():
            fail(errors, path, "required output is missing")

    print(f"documents={len(files)} pages={page_total} requires_ocr={len(ocr_required)}")
    print(f"unique_official_urls={len(urls)}")
    print(
        f"inventory_records={len(inventory)} "
        f"explicit_duplicates={sum(bool(record.get('dupe')) for record in inventory)}"
    )
    if errors:
        for error in errors:
            print("ERROR", error)
        return 1
    print("validation=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
