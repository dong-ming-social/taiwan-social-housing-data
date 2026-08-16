#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Build a repo-schema JSON from a social-housing PDF.

anydoc parses PDF text; this script assembles the repo's own JSON schema
(metadata / source / sections / structured_data / pages) that anydoc does not
produce directly.

Usage (CLI):
    python pdf_to_json.py \
        --pdf doc.pdf \
        --name "附件N_文件名稱" \
        --type regulation \
        --version "民國115年招租附件" \
        --attribution "資料來源：臺北市住宅及都市更新中心，附件N_文件名稱。" \
        --structured structured.json \      # optional: merged into structured_data
        --out /path/to/repo

Or import build() from another script for finer control over structured_data.
"""
import argparse
import hashlib
import json
import os
import urllib.parse

import pdfplumber
from pypdf import PdfReader

BASE = "https://rent.thurc.org.taipei/documents/dongming/"
IMG_NOTE = "本頁包含圖像內容；未臆測無文字層的圖像細節。"
PARSER = {
    "name": "anydoc",
    "distribution": "firecrawl-anydoc",
    "version": "0.1.9",
    "binding": "Python",
    "repository": "https://github.com/dwhao84/anydoc.git",
    "repository_commit": "e754e1d33a1a540ebc9226e36f11d3f401852c9e",
}


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _norm(t):
    return [["" if c is None else c for c in row] for row in t]


def build_pages(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, p in enumerate(pdf.pages, 1):
            text = (p.extract_text() or "").strip()
            tables = [_norm(t) for t in p.extract_tables()]
            ic = len(p.images)
            has_text = bool(text)
            pages.append({
                "page": i,
                "text": text,
                "tables": tables,
                "image_count": ic,
                "has_text": has_text,
                "is_blank": (not has_text) and ic == 0 and not tables,
                "image_note": IMG_NOTE if ic > 0 else None,
            })
    return pages


def empty_entities():
    return {"dates": [], "times": [], "amounts_twd": [],
            "percentages": [], "phone_numbers": []}


def build(pdf_path, doc_name, document_type, version, attribution,
          pdf_basename=None, official_pdf_url=None,
          structured_extra=None, entities=None):
    """Return the JSON dict. pdf_basename defaults to doc_name + '.pdf'."""
    pdf_basename = pdf_basename or (doc_name + ".pdf")
    url = official_pdf_url or (BASE + urllib.parse.quote(pdf_basename))
    reader = PdfReader(pdf_path)
    pages = build_pages(pdf_path)

    structured = {"document_type": document_type,
                  "entities": entities or empty_entities()}
    structured.update(structured_extra or {})
    if "tables" not in structured:
        agg = []
        for p in pages:
            for t in p["tables"]:
                agg.append({"source_pages": [p["page"]], "rows": t})
        structured["tables"] = agg

    return {
        "metadata": {
            "document_name": doc_name,
            "document_type": document_type,
            "version": version,
            "language": "zh-Hant",
            "pdf_filename": pdf_basename,
            "json_filename": doc_name + ".json",
            "page_count": len(reader.pages),
            "pdf_sha256": sha256(pdf_path),
            "pdf_encrypted": bool(reader.is_encrypted),
            "parser": PARSER,
        },
        "source": {
            "official_pdf_url": url,
            "publisher": "臺北市住宅及都市更新中心",
            "website_owner": "臺北市政府都市發展局",
            "attribution": attribution,
            "rights_note": "本資料僅記錄官方來源，不另行宣告授權；使用條件請依官方網站為準。",
        },
        "sections": [{
            "id": "document",
            "title": doc_name,
            "page_start": 1,
            "page_end": len(pages),
            "source_pages": [p["page"] for p in pages],
            "content_pages": [{"page": p["page"], "text": p["text"]} for p in pages],
        }],
        "structured_data": structured,
        "pages": pages,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--name", required=True, help="document_name (no extension)")
    ap.add_argument("--type", required=True, dest="document_type")
    ap.add_argument("--version", required=True)
    ap.add_argument("--attribution", required=True)
    ap.add_argument("--basename", help="original PDF filename with .pdf")
    ap.add_argument("--url", help="official_pdf_url override")
    ap.add_argument("--structured", help="path to JSON merged into structured_data")
    ap.add_argument("--out", default=".", help="output directory")
    a = ap.parse_args()

    extra = None
    if a.structured:
        extra = json.load(open(a.structured, encoding="utf-8"))

    doc = build(a.pdf, a.name, a.document_type, a.version, a.attribution,
                pdf_basename=a.basename, official_pdf_url=a.url,
                structured_extra=extra)
    out_path = os.path.join(a.out, a.name + ".json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", out_path, "| pages", doc["metadata"]["page_count"],
          "| sha", doc["metadata"]["pdf_sha256"][:12])


if __name__ == "__main__":
    main()
