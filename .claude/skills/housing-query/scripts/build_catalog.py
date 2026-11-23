#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the document catalog that the housing-query skill uses to find files.

The catalog is deterministic (no timestamps) so `--check` can detect drift in CI.
Folder labels come from FOLDER_DESCRIPTIONS in the housing-doc-to-json
daily_update.py, the same source that renders the README table.
"""

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CATALOG = Path(__file__).resolve().parents[1] / "reference" / "catalog.json"
DAILY_UPDATE = REPO / ".claude/skills/housing-doc-to-json/scripts/daily_update.py"
NON_DOCUMENT_DIRS = {"api", "laws", "docs"}
GENERIC_FIELDS = {"document_type", "entities", "tables", "requires_ocr", "ocr_note", "note"}


def folder_descriptions():
    """Read FOLDER_DESCRIPTIONS without importing daily_update (and its deps)."""
    tree = ast.parse(DAILY_UPDATE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "FOLDER_DESCRIPTIONS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    return {}


def document_dirs():
    return sorted(
        path
        for path in REPO.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in NON_DOCUMENT_DIRS
        and any(path.glob("*.json"))
    )


def build():
    labels = folder_descriptions()
    folders = []
    documents = []
    for directory in document_dirs():
        files = sorted(directory.glob("*.json"))
        folder_pages = 0
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            metadata = data["metadata"]
            structured = data.get("structured_data", {})
            folder_pages += metadata["page_count"]
            documents.append(
                {
                    "path": path.relative_to(REPO).as_posix(),
                    "folder": directory.name,
                    "title": metadata.get("document_name") or path.stem,
                    "document_type": metadata.get("document_type") or structured.get("document_type"),
                    "version": metadata.get("version"),
                    "page_count": metadata["page_count"],
                    "requires_ocr": bool(structured.get("requires_ocr")),
                    "structured_fields": sorted(key for key in structured if key not in GENERIC_FIELDS),
                }
            )
        folders.append(
            {
                "folder": directory.name,
                "label": labels.get(directory.name, directory.name),
                "document_count": len(files),
                "page_count": folder_pages,
            }
        )
    return {
        "schema_version": "1.0",
        "repository": "dong-ming-social/taiwan-social-housing-data",
        "raw_base_url": "https://raw.githubusercontent.com/dong-ming-social/taiwan-social-housing-data/main/",
        "document_count": len(documents),
        "page_count": sum(doc["page_count"] for doc in documents),
        "datasets": {
            "housing_locations": "api/v1/housing-locations.json",
            "districts": "api/v1/districts.json",
            "district_detail": "api/v1/districts/{district-code}.json",
            "taipei_rental_regulation_history": "laws/taipei/FL071776.json",
        },
        "folders": folders,
        "documents": documents,
    }


def render(catalog):
    """Pretty top level, one compact line per folder/document to keep the file small and diffable."""
    lines = ["{"]
    items = list(catalog.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        if isinstance(value, list):
            rows = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in value]
            lines.append(f' "{key}": [')
            lines.extend(f"  {row}," for row in rows[:-1])
            if rows:
                lines.append(f"  {rows[-1]}")
            lines.append(f" ]{comma}")
        else:
            lines.append(f' "{key}": {json.dumps(value, ensure_ascii=False)}{comma}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if catalog.json is out of date; do not write")
    args = parser.parse_args()

    text = render(build())
    if args.check:
        current = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else ""
        if current != text:
            print(
                f"{CATALOG.relative_to(REPO)} 已過期，請執行 "
                "python .claude/skills/housing-query/scripts/build_catalog.py",
                file=sys.stderr,
            )
            return 1
        print("catalog.json 與資料集一致")
        return 0
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    if not CATALOG.exists() or CATALOG.read_text(encoding="utf-8") != text:
        CATALOG.write_text(text, encoding="utf-8")
        print(f"已更新 {CATALOG.relative_to(REPO)}")
    else:
        print("catalog.json 無變化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
