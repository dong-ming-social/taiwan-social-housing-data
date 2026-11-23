#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover every PDF currently linked by the Taipei social-housing portal."""

import html
import json
import re
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


HOST = "https://rent.thurc.org.taipei"
REPO = Path(__file__).resolve().parents[4]
INVENTORY = REPO / ".claude/skills/housing-doc-to-json/batch/portal_inventory.json"


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def fetch_html(path):
    url = urllib.parse.urljoin(HOST, path)
    result = subprocess.run(
        [
            "curl", "--silent", "--show-error", "--location", "--fail",
            "--retry", "3", "--retry-delay", "2", "--max-time", "90", url,
        ],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"HTTP fetch failed ({result.returncode}) {url}")
    return result.stdout.decode("utf-8", errors="replace")


def hrefs(document):
    parser = LinkParser()
    parser.feed(document)
    return parser.hrefs


def normalized_pdf_paths(href):
    """Return all PDF paths, including malformed hrefs containing two URLs."""
    value = html.unescape(href).strip()
    candidates = re.findall(
        r"https?://[^\s\"']+?\.pdf|/(?:documents|assets/attachments)/[^\s\"']+?\.pdf",
        value,
        flags=re.I,
    )
    if not candidates and value.lower().endswith(".pdf"):
        candidates = [value]

    result = []
    for candidate in candidates:
        absolute = urllib.parse.urljoin(HOST, candidate)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.netloc.lower() != "rent.thurc.org.taipei":
            continue
        path = urllib.parse.unquote(parsed.path)
        if path.startswith("/documents/") or path.startswith("/assets/attachments/"):
            result.append(path)
    return result


def add_pdfs(found, document, source):
    for href in hrefs(document):
        for path in normalized_pdf_paths(href):
            found[path].add(source)


def known_attachment_slugs():
    if not INVENTORY.exists():
        return set()
    records = json.loads(INVENTORY.read_text(encoding="utf-8"))
    slugs = set()
    for record in records:
        for source in record.get("src", []):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", str(source)):
                slugs.add(source)
    return slugs


def warn(message):
    print(f"WARNING {message}", file=sys.stderr, flush=True)


def preserve_failed_source(found, source):
    """Do not mark known documents inactive when one portal page is down."""
    if not INVENTORY.exists():
        return
    for record in json.loads(INVENTORY.read_text(encoding="utf-8")):
        if source in record.get("src", []) and record.get("active") is not False:
            found[record["path"]].add(source)


def known_news_sources():
    """Return news detail ids that previously linked active documents."""
    if not INVENTORY.exists():
        return set()
    return {
        str(source)
        for record in json.loads(INVENTORY.read_text(encoding="utf-8"))
        if record.get("active") is not False
        for source in record.get("src", [])
        if str(source).isdigit()
    }


def news_detail_paths(document):
    return {
        urllib.parse.urlparse(link).path
        for link in hrefs(document)
        if re.fullmatch(r"/news/detail/\d+", urllib.parse.urlparse(link).path, re.I)
    }


def discover_news(found):
    """Collect PDFs from news pages, tolerating individual page failures.

    If any list page fails, some detail pages may be missing from this run, so
    every previously known news source that was not fetched is preserved.
    """
    detail_paths = set()
    list_failed = False
    try:
        first_news = fetch_html("/News?page=1")
    except RuntimeError as exc:
        warn(f"news list page 1 skipped: {exc}")
        first_news = None
        list_failed = True

    if first_news is not None:
        detail_paths |= news_detail_paths(first_news)
        page_numbers = {
            int(match.group(1))
            for link in hrefs(first_news)
            if (match := re.search(r"/News\?page=(\d+)", link, re.I))
        }
        for page in range(2, max(page_numbers or {1}) + 1):
            try:
                detail_paths |= news_detail_paths(fetch_html(f"/News?page={page}"))
            except RuntimeError as exc:
                warn(f"news list page {page} skipped: {exc}")
                list_failed = True

    fetched = set()
    for detail_path in sorted(detail_paths):
        source = detail_path.rsplit("/", 1)[-1]
        try:
            document = fetch_html(detail_path)
        except RuntimeError as exc:
            warn(f"news detail {source} skipped: {exc}")
            preserve_failed_source(found, source)
            continue
        fetched.add(source)
        add_pdfs(found, document, source)

    if list_failed:
        for source in sorted(known_news_sources() - fetched):
            preserve_failed_source(found, source)


def discover():
    found = defaultdict(set)

    home = fetch_html("/")
    add_pdfs(found, home, "home")

    downloads = fetch_html("/attachments")
    add_pdfs(found, downloads, "attachments")

    site_map = fetch_html("/housing-sites/map")
    site_slugs = {
        match.group(1)
        for link in hrefs(site_map)
        if (match := re.search(r"/Rental/Site/([^/?#]+)", link, re.I))
    }
    candidates = set(site_slugs) | known_attachment_slugs()
    candidates |= {slug.replace("-", "_") for slug in site_slugs}
    candidates |= {slug.replace("_", "-") for slug in site_slugs}
    for slug in sorted(candidates):
        try:
            document = fetch_html(f"/Attachments/{urllib.parse.quote(slug)}")
        except RuntimeError:
            # This portal returns HTTP 500 for sites without attachment pages.
            # Preserve previously known links for transient failures as well.
            preserve_failed_source(found, slug)
            continue
        add_pdfs(found, document, slug)

    discover_news(found)

    return {path: sorted(sources) for path, sources in sorted(found.items())}


def main():
    result = discover()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
