#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query the Taiwan Social Housing Data dataset from a local clone or GitHub Raw.

Data source resolution (first match wins):
  1. --repo PATH or env HOUSING_DATA_REPO
  2. a clone found by walking up from the current directory or this script
  3. GitHub Raw (main branch) — requires network access

Subcommands print compact JSON so the caller does not have to load whole files.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAW_BASE = "https://raw.githubusercontent.com/dong-ming-social/taiwan-social-housing-data/main/"
SKILL_DIR = Path(__file__).resolve().parents[1]
BUNDLED_CATALOG = SKILL_DIR / "reference" / "catalog.json"
REMOTE_CATALOG = ".claude/skills/housing-query/reference/catalog.json"
LAW_PATH = "laws/taipei/FL071776.json"
MARKER = "api/v1/index.json"
DISTRICT_CODES = {
    "北投區": "beitou", "大安區": "daan", "大同區": "datong", "南港區": "nangang",
    "內湖區": "neihu", "士林區": "shilin", "松山區": "songshan", "萬華區": "wanhua",
    "文山區": "wenshan", "信義區": "xinyi", "中山區": "zhongshan", "中正區": "zhongzheng",
}
REMOTE_SEARCH_LIMIT = 15


class Source:
    def __init__(self, repo=None):
        self.repo = Path(repo).resolve() if repo else None

    @property
    def label(self):
        return str(self.repo) if self.repo else RAW_BASE

    def load(self, relative):
        if self.repo:
            return json.loads((self.repo / relative).read_text(encoding="utf-8"))
        url = RAW_BASE + urllib.parse.quote(relative)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except Exception:
            # Some Python builds lack CA certs; curl uses the system store.
            output = subprocess.run(
                ["curl", "-fsSL", "--max-time", "30", url], check=True, capture_output=True
            ).stdout
            return json.loads(output)

    def catalog(self):
        if self.repo:
            local = self.repo / REMOTE_CATALOG
            return json.loads(local.read_text(encoding="utf-8")) if local.exists() else _bundled()
        try:
            return self.load(REMOTE_CATALOG)
        except Exception:
            return _bundled()


def _bundled():
    return json.loads(BUNDLED_CATALOG.read_text(encoding="utf-8"))


def find_repo(explicit):
    if explicit:
        return explicit
    if os.environ.get("HOUSING_DATA_REPO"):
        return os.environ["HOUSING_DATA_REPO"]
    for start in (Path.cwd(), SKILL_DIR):
        for candidate in (start, *start.parents):
            if (candidate / MARKER).exists() and (candidate / LAW_PATH).exists():
                return candidate
    return None


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def terms(text):
    return [term.lower() for term in re.split(r"\s+", text or "") if term]


def matches(haystack, words):
    haystack = haystack.lower()
    return all(word in haystack for word in words)


def filter_documents(catalog, folder=None, doc_type=None, keyword=None):
    labels = {item["folder"]: item["label"] for item in catalog["folders"]}
    words = terms(keyword)
    results = []
    for doc in catalog["documents"]:
        if folder and doc["folder"] != folder:
            continue
        if doc_type and doc["document_type"] != doc_type:
            continue
        text = " ".join([doc["path"], doc["title"], doc.get("version") or "", labels.get(doc["folder"], "")])
        if words and not matches(text, words):
            continue
        results.append({**doc, "folder_label": labels.get(doc["folder"], doc["folder"])})
    return results


def cmd_folders(source, args):
    catalog = source.catalog()
    words = terms(args.keyword)
    folders = [f for f in catalog["folders"] if not words or matches(f["folder"] + " " + f["label"], words)]
    emit({"source": source.label, "count": len(folders), "folders": folders})


def cmd_docs(source, args):
    docs = filter_documents(source.catalog(), args.folder, args.type, args.keyword)
    emit({"source": source.label, "count": len(docs), "documents": docs[: args.limit]})


def snippet(text, word, width):
    index = text.lower().find(word)
    start = max(0, index - width)
    end = min(len(text), index + len(word) + width)
    return ("…" if start else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")


def cmd_search(source, args):
    words = terms(args.query)
    docs = filter_documents(source.catalog(), args.folder, args.type, args.title)
    if not source.repo and len(docs) > REMOTE_SEARCH_LIMIT:
        emit({
            "source": source.label,
            "error": f"遠端模式一次最多全文搜尋 {REMOTE_SEARCH_LIMIT} 份文件，目前條件有 {len(docs)} 份。"
                     "請加上 --folder、--type 或 --title 縮小範圍。",
        })
        return 2
    hits = []
    for doc in docs:
        data = source.load(doc["path"])
        for page in data.get("pages", []):
            text = page.get("text") or ""
            if matches(text, words):
                hits.append({
                    "path": doc["path"],
                    "title": doc["title"],
                    "page": page["page"],
                    "snippet": snippet(text, words[0], args.context),
                    "official_pdf_url": data["source"]["official_pdf_url"],
                })
                if len(hits) >= args.limit:
                    emit({"source": source.label, "count": len(hits), "truncated": True, "hits": hits})
                    return 0
    emit({"source": source.label, "count": len(hits), "truncated": False, "hits": hits})
    return 0


def parse_pages(spec):
    pages = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            pages.update(range(int(low), int(high) + 1))
        else:
            pages.add(int(part))
    return pages


def cmd_show(source, args):
    data = source.load(args.path)
    structured = data.get("structured_data", {})
    output = {
        "source": source.label,
        "path": args.path,
        "metadata": {k: v for k, v in data["metadata"].items() if k != "parser"},
        "citation": data["source"],
        "structured_fields": sorted(structured),
    }
    if args.field:
        missing = [name for name in args.field if name not in structured]
        if missing:
            output["missing_fields"] = missing
        output["structured_data"] = {name: structured[name] for name in args.field if name in structured}
    if args.sections:
        output["sections"] = [
            {"title": s.get("title"), "source_pages": s.get("source_pages"), "content": s.get("content")}
            for s in data.get("sections", [])
        ]
    else:
        output["section_titles"] = [
            {"title": s.get("title"), "source_pages": s.get("source_pages")} for s in data.get("sections", [])
        ]
    wanted = parse_pages(args.pages)
    if wanted:
        output["pages"] = [
            {key: page.get(key) for key in ("page", "text", "tables", "image_note") if page.get(key) is not None}
            for page in data.get("pages", [])
            if page["page"] in wanted
        ]
    emit(output)


def cmd_locations(source, args):
    if args.district:
        code = DISTRICT_CODES.get(args.district, DISTRICT_CODES.get(args.district + "區", args.district))
        data = source.load(f"api/v1/districts/{code}.json")
    else:
        data = source.load("api/v1/housing-locations.json")
    words = terms(args.name)
    items = [
        item for item in data["items"]
        if (not words or matches(item["name"] + " " + (item.get("address") or ""), words))
        and (not args.status or item.get("status") == args.status)
    ]
    emit({
        "source": source.label,
        "updated_at": data.get("updated_at"),
        "dataset_source": data.get("source"),
        "count": len(items),
        "items": items[: args.limit],
    })


def cmd_law(source, args):
    data = source.load(LAW_PATH)
    versions = data["versions"]
    summary = {
        "source": source.label,
        "name": data["name"],
        "authority": data.get("authority"),
        "source_url": data["source_url"],
        "versions": [
            {"sequence": v["sequence"], "date": v["date"], "history": v.get("history"),
             "article_count": v.get("article_count")}
            for v in versions
        ],
    }
    if args.version is None and not args.article and not args.changes:
        emit(summary)
        return
    chosen = versions[-1] if args.version is None else next(
        (v for v in versions if v["sequence"] == args.version), None
    )
    if chosen is None:
        emit({**summary, "error": f"找不到版本 {args.version}"})
        return 2
    output = {key: summary[key] for key in ("source", "name", "source_url")}
    output["version"] = {k: chosen.get(k) for k in ("sequence", "date", "history", "order_number", "full_text_url")}
    if args.article:
        wanted = {a.strip() for a in args.article.split(",")}
        output["articles"] = [
            a for a in chosen["articles"]
            if str(a.get("article_number", "")).strip() in wanted
        ]
    if args.changes:
        changes = chosen.get("changes_from_previous") or {}
        if args.article and changes.get("articles"):
            changes = {**changes, "articles": [
                c for c in changes["articles"] if str(c.get("article_number", "")).strip() in wanted
            ]}
        output["changes_from_previous"] = changes
    emit(output)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="local clone path (default: auto-detect, else GitHub Raw)")
    parser.add_argument("--remote", action="store_true", help="force GitHub Raw even if a clone is found")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("folders", help="list source folders with Chinese labels")
    p.add_argument("--keyword")
    p.set_defaults(func=cmd_folders)

    p = sub.add_parser("docs", help="filter the document catalog")
    p.add_argument("--folder")
    p.add_argument("--type", help="document_type, e.g. rent_table, lease_contract, announcement")
    p.add_argument("--keyword", help="space-separated terms matched against title/folder label")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("search", help="full-text search page text")
    p.add_argument("query", help="space-separated terms; all must appear on the same page")
    p.add_argument("--folder")
    p.add_argument("--type")
    p.add_argument("--title", help="pre-filter documents by title/folder label terms")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--context", type=int, default=80, help="snippet characters on each side")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="show one document's metadata, citation and selected parts")
    p.add_argument("path", help="repo-relative JSON path from the catalog")
    p.add_argument("--field", action="append", help="structured_data key to include (repeatable)")
    p.add_argument("--pages", help="page numbers, e.g. 1,3-5")
    p.add_argument("--sections", action="store_true", help="include full section content")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("locations", help="Taipei social-housing locations (api/v1)")
    p.add_argument("--district", help="e.g. 文山區, 文山 or wenshan")
    p.add_argument("--name", help="terms matched against name/address")
    p.add_argument("--status", help="已完工, 施工中及待開工 or 規劃中")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_locations)

    p = sub.add_parser("law", help="臺北市社會住宅出租辦法 version history")
    p.add_argument("--version", type=int, help="version sequence (default: latest when other flags are used)")
    p.add_argument("--article", help="article numbers, comma-separated, e.g. 3,23")
    p.add_argument("--changes", action="store_true", help="include changes from the previous version")
    p.set_defaults(func=cmd_law)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    source = Source(None if args.remote else find_repo(args.repo))
    return args.func(source, args) or 0


if __name__ == "__main__":
    sys.exit(main())
