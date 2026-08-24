#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover every PDF currently linked by the Taipei social-housing portal."""

import html
import json
import re
import subprocess
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


def preserve_failed_attachment_source(found, slug):
    """Do not mark known documents inactive when one attachment page is down."""
    if not INVENTORY.exists():
        return
    for record in json.loads(INVENTORY.read_text(encoding="utf-8")):
        if slug in record.get("src", []) and record.get("active") is not False:
            found[record["path"]].add(slug)


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
            preserve_failed_attachment_source(found, slug)
            continue
        add_pdfs(found, document, slug)

    first_news = fetch_html("/News?page=1")
    page_numbers = {
        int(match.group(1))
        for link in hrefs(first_news)
        if (match := re.search(r"/News\?page=(\d+)", link, re.I))
    }
    last_page = max(page_numbers or {1})
    detail_paths = set()
    for page in range(1, last_page + 1):
        document = first_news if page == 1 else fetch_html(f"/News?page={page}")
        for link in hrefs(document):
            if re.fullmatch(r"/news/detail/\d+", urllib.parse.urlparse(link).path, re.I):
                detail_paths.add(urllib.parse.urlparse(link).path)

    for detail_path in sorted(detail_paths):
        document = fetch_html(detail_path)
        source = detail_path.rsplit("/", 1)[-1]
        add_pdfs(found, document, source)

    return {path: sorted(sources) for path, sources in sorted(found.items())}


def main():
    result = discover()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
