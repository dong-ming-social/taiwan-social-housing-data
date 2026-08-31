#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch driver: portal PDF -> repo-schema JSON, one folder per /documents/<bucket>/.

Reads a worklist JSON [{bucket, stem, path}], downloads each PDF into the
scratchpad, and writes <repo>/<bucket>/<stem>.json via the skill helper.
Records nothing it cannot read from the PDF itself.
"""
import json, os, re, subprocess, sys, tempfile, urllib.parse
from pathlib import Path

from pypdf import PdfReader

REPO = Path(__file__).resolve().parents[4]
SKILL = REPO / ".claude/skills/housing-doc-to-json/scripts"
PDFDIR = os.environ.get(
    "HOUSING_PDF_CACHE",
    os.path.join(tempfile.gettempdir(), "taiwan-social-housing-pdf-cache"),
)
sys.path.insert(0, str(SKILL))
import pdf_to_json as H  # noqa: E402

HOST = "https://rent.thurc.org.taipei"

# filename -> document_type. Order matters: first match wins.
TYPE_RULES = [
    ("規約手冊", "resident_handbook"), ("住戶手冊", "resident_handbook"),
    ("管理扣分規定", "regulation"),
    ("租賃契約書", "lease_contract"), ("契約書範本", "lease_contract"),
    ("租約範本", "lease_contract"), ("契約書", "lease_contract"),
    ("不能補正", "guidance"), ("應補正", "guidance"),
    ("應備文件", "required_documents"),
    ("評點制辦理情形", "reference_table"),
    ("所得級距", "rent_table"), ("租金補貼", "rent_table"),
    ("分級租金", "rent_table"), ("租金對照", "rent_table"),
    ("切結書", "declaration"),
    ("複查申請表", "form"), ("申請書封套", "form"), ("撤案申請書", "form"),
    ("委託書", "form"), ("授權書", "form"), ("申請表", "form"),
    ("申請書", "form"), ("填寫範例", "form"),
    ("一覽表", "reference_table"), ("戶數表", "reference_table"),
    ("說明表", "reference_table"), ("平面圖", "floor_plan"),
    ("招租手冊", "rental_handbook"), ("選屋手冊", "rental_handbook"),
    ("徵件簡章", "rental_handbook"), ("聯招手冊", "rental_handbook"),
    ("手冊", "rental_handbook"),
    ("公告", "announcement"), ("結果", "announcement"), ("名單", "announcement"),
    ("清冊", "announcement"),
    ("租賃標的", "guidance"), ("租期及費用", "guidance"), ("說明", "guidance"),
    ("操作方式", "guidance"), ("懶人包", "guidance"), ("基地介紹", "guidance"),
    ("方案", "reference_table"), ("摺頁", "guidance"), ("簡報", "announcement"),
]


def doc_type(stem):
    for k, v in TYPE_RULES:
        if k in stem:
            return v
    return "announcement"


def version_of(stem, bucket_label):
    m = re.search(r"\((\d{3}年\d{1,2}月版)\)", stem)
    if m:
        return "中華民國" + m.group(1)
    m = re.search(r"(\d{3})年", stem)
    if m:
        return f"民國{m.group(1)}年版"
    return bucket_label


def valid_pdf(path):
    """Return True only for a complete, readable PDF with at least one page."""
    try:
        if not (os.path.exists(path) and os.path.getsize(path) > 1000):
            return False
        with open(path, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                return False
        return len(PdfReader(path).pages) > 0
    except Exception:
        return False


def fetch(path, refresh=False):
    """Download one PDF; returns local path. Percent-encodes the filename only."""
    os.makedirs(PDFDIR, exist_ok=True)
    parts = path.split("/")
    url = HOST + "/".join(
        [urllib.parse.quote(p, safe="") if i == len(parts) - 1 else p
         for i, p in enumerate(parts)])
    local = os.path.join(PDFDIR, re.sub(r"[/]", "_", path.lstrip("/")))
    if refresh or not valid_pdf(local):
        tmp = local + ".download"
        r = subprocess.run(["curl", "-sSL", "--fail", "-o", tmp, url],
                           capture_output=True, text=True)
        if r.returncode != 0:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise RuntimeError(f"download failed ({r.returncode}) {url}")
        if not valid_pdf(tmp):
            os.unlink(tmp)
            raise RuntimeError(f"downloaded file is not a complete PDF: {path}")
        os.replace(tmp, local)
    return local


def convert(rec, bucket_label):
    bucket, stem, path = rec["bucket"], rec["stem"], rec["path"]
    output_stem = rec.get("output_stem", stem)
    title = rec.get("title", output_stem)
    local = fetch(path)
    dt = doc_type(title)
    url = HOST + "/".join(
        [urllib.parse.quote(p, safe="") if i == len(path.split("/")) - 1 else p
         for i, p in enumerate(path.split("/"))])
    doc = H.build(
        local, title, dt,
        version_of(title, bucket_label),
        f"資料來源：臺北市住宅及都市更新中心，{title}。",
        pdf_basename=stem + ".pdf",
        official_pdf_url=url,
    )
    npages = doc["metadata"]["page_count"]
    ntext = sum(1 for p in doc["pages"] if p["has_text"])
    if ntext == 0:
        doc["structured_data"]["requires_ocr"] = True
        doc["structured_data"]["ocr_note"] = (
            "本 PDF 無文字層（掃描影像），未進行 OCR，故未擷取內文；"
            "如需內文請對照官方 PDF 或另行 OCR。")
    outdir = REPO / bucket
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{output_stem}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return dict(out=str(out), type=dt, pages=npages, text_pages=ntext,
                sha=doc["metadata"]["pdf_sha256"][:12])


def main():
    worklist = json.load(open(sys.argv[1], encoding="utf-8"))
    labels = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else {}
    ok, fail = [], []
    for rec in worklist:
        try:
            r = convert(rec, labels.get(rec["bucket"], rec["bucket"] + " 招租文件"))
            ok.append((rec, r))
            print(f"OK   {r['type']:<19} p{r['pages']:<3} text{r['text_pages']:<3} "
                  f"{rec['bucket']}/{rec['stem'][:52]}")
        except Exception as e:
            fail.append((rec, str(e)))
            print(f"FAIL {rec['bucket']}/{rec['stem'][:52]} :: {e}")
    print(f"\n=== {len(ok)} ok, {len(fail)} failed ===")
    for rec, e in fail:
        print("  ", rec["path"], "::", e)


if __name__ == "__main__":
    main()
