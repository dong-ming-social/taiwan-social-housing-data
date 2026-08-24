#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover, download, convert, and validate daily portal document changes."""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
SKILL = REPO / ".claude/skills/housing-doc-to-json"
BATCH = SKILL / "batch"
INVENTORY = BATCH / "portal_inventory.json"
README = REPO / "README.md"
SUMMARY_PATH = Path(os.environ.get("HOUSING_UPDATE_SUMMARY", "/tmp/housing-update-summary.md"))
MIN_DISCOVERY_RATIO = 0.90

sys.path.insert(0, str(SKILL / "scripts"))
import batch_convert  # noqa: E402
import portal_discovery  # noqa: E402


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def output_bucket(path):
    parts = Path(path).parts
    if path.startswith("/assets/attachments/"):
        return "citywide"
    if len(parts) >= 3 and parts[1] == "documents":
        return parts[2]
    raise ValueError(f"unsupported PDF path: {path}")


def inventory_bucket(path):
    return "_assets" if path.startswith("/assets/attachments/") else output_bucket(path)


def stem_of(path):
    return Path(path).name[:-4]


def tier_of(stem):
    high = (
        "規約", "手冊", "契約", "所得級距", "租金補貼", "應備文件", "扣分",
        "不能補正", "應補正", "切結書", "招租公告", "徵件簡章", "申請書",
    )
    return "high" if any(word in stem for word in high) else "low"


def dataset_by_source():
    result = {}
    for path in REPO.glob("*/*.json"):
        document = load_json(path)
        url = document.get("source", {}).get("official_pdf_url", "")
        source_path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        if source_path:
            result[source_path] = (path, document)
    return result


def worklist_overrides():
    result = {}
    for name in ("worklist_handbook.json", "worklist_rest.json"):
        for record in load_json(BATCH / name):
            result[record["path"]] = {
                key: record[key] for key in ("output_stem", "title") if key in record
            }
    return result


def merge_inventory(discovered, existing_sources):
    old_records = load_json(INVENTORY)
    old_by_path = {record["path"]: record for record in old_records}
    active_before = sum(not record.get("active") is False for record in old_records)
    if len(discovered) < max(1, int(active_before * MIN_DISCOVERY_RATIO)):
        raise RuntimeError(
            f"discovery guardrail: found only {len(discovered)} PDFs; "
            f"previously had {active_before} active records"
        )

    merged = []
    for path in sorted(set(old_by_path) | set(discovered)):
        if path in old_by_path:
            record = dict(old_by_path[path])
        else:
            record = {
                "bucket": inventory_bucket(path),
                "stem": stem_of(path),
                "path": path,
                "have": path in existing_sources,
                "tier": tier_of(stem_of(path)),
                "src": [],
                "dupe": False,
            }
        if path in discovered:
            record.pop("active", None)
            record["src"] = sorted(set(record.get("src", [])) | set(discovered[path]))
        else:
            record["active"] = False
        record["have"] = path in existing_sources
        merged.append(record)
    return merged


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_all(records, workers):
    active = [record for record in records if not record.get("dupe") and record.get("active") is not False]
    downloaded = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(batch_convert.fetch, record["path"], True): record
            for record in active
        }
        for future in as_completed(futures):
            record = futures[future]
            downloaded[record["path"]] = Path(future.result())
    return downloaded


def unique_new_name(record, downloaded, occupied):
    bucket = output_bucket(record["path"])
    stem = record["stem"]
    candidate = stem
    if (bucket, candidate) not in occupied:
        return candidate, candidate

    # Prefer the first extracted line because it is usually the document's full title.
    try:
        import pdfplumber
        with pdfplumber.open(downloaded[record["path"]]) as pdf:
            first_line = ((pdf.pages[0].extract_text() or "").splitlines() or [""])[0].strip()
        first_line = re.sub(r"[/:]", "_", first_line).strip(" .")
        if first_line and (bucket, first_line) not in occupied:
            return first_line, first_line
    except Exception:
        pass

    path = Path(record["path"])
    parent = path.parent.name
    candidate = f"{parent}_{stem}"
    index = 2
    while (bucket, candidate) in occupied:
        candidate = f"{parent}_{stem}_{index}"
        index += 1
    return candidate, stem


def convert_changes(records, downloaded, existing_sources):
    labels = load_json(BATCH / "labels_rest.json")
    overrides = worklist_overrides()
    occupied = {(path.parent.name, path.stem) for path in REPO.glob("*/*.json")}
    new_files = []
    changed_files = []

    for record in records:
        path = record["path"]
        if record.get("dupe") or record.get("active") is False:
            continue
        current_sha = sha256(downloaded[path])
        existing = existing_sources.get(path)
        if existing and existing[1]["metadata"].get("pdf_sha256") == current_sha:
            continue

        rec = {
            "bucket": output_bucket(path),
            "stem": record["stem"],
            "path": path,
        }
        if existing:
            existing_path, document = existing
            rec["output_stem"] = existing_path.stem
            rec["title"] = document["metadata"].get("document_name", existing_path.stem)
        else:
            override = overrides.get(path, {})
            if override:
                rec.update(override)
            else:
                output_stem, title = unique_new_name(record, downloaded, occupied)
                rec["output_stem"] = output_stem
                rec["title"] = title
            occupied.add((rec["bucket"], rec.get("output_stem", rec["stem"])))

        result = batch_convert.convert(
            rec, labels.get(rec["bucket"], rec["bucket"] + " 招租文件")
        )
        relative = str(Path(result["out"]).relative_to(REPO))
        (changed_files if existing else new_files).append(relative)

    produced_paths = {
        urllib.parse.unquote(
            urllib.parse.urlparse(load_json(REPO / relative)["source"]["official_pdf_url"]).path
        )
        for relative in new_files + changed_files
    }
    for record in records:
        if record["path"] in produced_paths:
            record["have"] = True

    return sorted(new_files), sorted(changed_files)


def dataset_stats():
    rows = []
    for directory in sorted(path for path in REPO.iterdir() if path.is_dir() and not path.name.startswith(".")):
        files = sorted(directory.glob("*.json"))
        if not files:
            continue
        pages = 0
        ocr = 0
        for path in files:
            document = load_json(path)
            pages += document["metadata"]["page_count"]
            ocr += bool(document["structured_data"].get("requires_ocr"))
        rows.append((directory.name, len(files), pages, ocr))
    return rows


def update_readme():
    rows = dataset_stats()
    documents = sum(row[1] for row in rows)
    pages = sum(row[2] for row in rows)
    ocr = sum(row[3] for row in rows)
    text = README.read_text(encoding="utf-8")
    text = re.sub(
        r"目前共收錄 \*\*\d+ 份官方文件、[\d,]+ 頁\*\*，分布於 \d+ 個來源資料夾。",
        f"目前共收錄 **{documents} 份官方文件、{pages:,} 頁**，分布於 {len(rows)} 個來源資料夾。",
        text,
    )
    table = "\n".join(
        [
            "| 資料夾 | 文件數 | 頁數 | 待 OCR 文件數 |",
            "| --- | ---: | ---: | ---: |",
            *[f"| `{name}/` | {count} | {page_count} | {ocr_count} |" for name, count, page_count, ocr_count in rows],
        ]
    )
    text = re.sub(
        r"\| 資料夾 \| 文件數 \| 頁數 \| 待 OCR 文件數 \|.*?(?=\n\nJSON 檔名)",
        table,
        text,
        flags=re.S,
    )
    text = re.sub(r"\d+ 份無文字層的掃描 PDF", f"{ocr} 份無文字層的掃描 PDF", text)
    README.write_text(text, encoding="utf-8")
    return documents, pages, ocr


def write_summary(discovered_count, new_files, changed_files, inactive, stats):
    documents, pages, ocr = stats
    lines = [
        "# 社宅文件每日更新結果",
        "",
        f"- 本次發現：{discovered_count} 個官方 PDF 連結",
        f"- 新增文件：{len(new_files)}",
        f"- 內容更新：{len(changed_files)}",
        f"- 官網已不再連結（保留資料、不刪除）：{len(inactive)}",
        f"- 更新後資料集：{documents} 份、{pages:,} 頁、{ocr} 份待 OCR",
    ]
    for title, values in (("新增", new_files), ("更新", changed_files), ("停止連結", inactive)):
        if values:
            lines += ["", f"## {title}", *[f"- `{value}`" for value in values]]
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    discovered = portal_discovery.discover()
    existing_sources = dataset_by_source()
    records = merge_inventory(discovered, existing_sources)
    inactive = sorted(record["path"] for record in records if record.get("active") is False)
    print(
        f"discovered={len(discovered)} inventory={len(records)} "
        f"inactive={len(inactive)}"
    )
    if args.discover_only:
        return 0

    downloaded = download_all(records, max(1, args.workers))
    new_files, changed_files = convert_changes(records, downloaded, existing_sources)
    INVENTORY.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    stats = update_readme()
    write_summary(len(discovered), new_files, changed_files, inactive, stats)
    print(f"new={len(new_files)} changed={len(changed_files)} summary={SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
