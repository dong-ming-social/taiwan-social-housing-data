#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download every published version of a law from Taipei's law system."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup


HOST = "https://laws.gov.taipei"
HISTORY_PATH = "/Law/LawSearch/LawInformation/{law_id}"
USER_AGENT = (
    "taiwan-social-housing-data/1.0 "
    "(+https://github.com/dong-ming-social/taiwan-social-housing-data)"
)


class LawScrapeError(RuntimeError):
    """Raised when the official page cannot be downloaded or parsed safely."""


def clean_inline(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_article_text(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip()


def comparison_text(value: str) -> str:
    """Ignore presentation-only whitespace when comparing legal text."""
    return re.sub(r"\s+", "", value)


def absolute_url(href: str) -> str:
    return urllib.parse.urljoin(HOST, href)


def roc_date_from_history(history: str) -> str:
    match = re.search(r"中華民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", history)
    if not match:
        raise LawScrapeError(f"cannot find ROC date in history: {history!r}")
    year, month, day = map(int, match.groups())
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def order_number_from_history(history: str) -> str | None:
    match = re.search(r"臺北市政府(.+?號令)", history)
    return clean_inline(match.group(1)) if match else None


def metadata_value(soup: BeautifulSoup, label_text: str) -> str:
    wanted = re.sub(r"\s+", "", label_text)
    for row in soup.select(".info-upper .form-group.row"):
        label = row.select_one(".col-label label")
        value = row.select_one(".col-input")
        if not label or not value:
            continue
        if re.sub(r"\s+", "", label.get_text()) == wanted:
            return clean_inline(value.get_text(" ", strip=True))
    raise LawScrapeError(f"missing law metadata field: {label_text}")


def parse_history(document: str, law_id: str) -> dict:
    soup = BeautifulSoup(document, "html.parser")
    revisions = []
    for item in soup.select("ul.law-revision > li"):
        number_node = item.select_one(".revision-no")
        history_node = item.select_one(".revision-content")
        if not number_node or not history_node:
            raise LawScrapeError("history revision is missing its number or content")

        history = clean_inline(history_node.get_text(" ", strip=True))
        try:
            sequence = int(number_node.get_text(strip=True).rstrip("."))
        except ValueError as exc:
            raise LawScrapeError("history revision has an invalid sequence") from exc

        full_text_url = None
        amended_text_url = None
        for link in item.select(".revision-buttons a[href]"):
            href = link.get("href", "")
            if "/LawArticleContent/" in href:
                full_text_url = absolute_url(href)
            elif "/LawArticleAmend/" in href:
                amended_text_url = absolute_url(href)
        if not full_text_url:
            raise LawScrapeError(f"revision {sequence} has no full-text link")

        revisions.append(
            {
                "sequence": sequence,
                "date": roc_date_from_history(history),
                "history": history,
                "order_number": order_number_from_history(history),
                "full_text_url": full_text_url,
                "amended_text_url": amended_text_url,
            }
        )

    if not revisions:
        raise LawScrapeError("history page contains no revisions")
    if len({item["date"] for item in revisions}) != len(revisions):
        raise LawScrapeError("history page contains duplicate revision dates")

    revisions.sort(key=lambda item: item["date"])
    return {
        "law_id": law_id,
        "law_code": metadata_value(soup, "法規類號"),
        "name": metadata_value(soup, "名稱"),
        "authority": "臺北市政府法務局",
        "source_url": absolute_url(HISTORY_PATH.format(law_id=law_id)),
        "revisions": revisions,
    }


def article_number(label: str) -> str:
    match = re.search(r"第\s*(.+?)\s*條", label)
    if not match:
        raise LawScrapeError(f"invalid article label: {label!r}")
    return re.sub(r"\s+", "", match.group(1))


def parse_articles(document: str) -> list[dict]:
    soup = BeautifulSoup(document, "html.parser")
    articles = []
    for item in soup.select("article.col-article li"):
        label_node = item.select_one(".col-no")
        text_node = item.select_one(".law-articlepre")
        if not label_node and not text_node:
            continue
        if not label_node or not text_node:
            raise LawScrapeError("article is missing its number or text")
        label = clean_inline(label_node.get_text(" ", strip=True))
        text = clean_article_text(text_node.get_text())
        if not text:
            raise LawScrapeError(f"{label} has empty text")
        articles.append(
            {"article_number": article_number(label), "label": label, "text": text}
        )

    if not articles:
        raise LawScrapeError("article page contains no articles")
    numbers = [article["article_number"] for article in articles]
    if len(numbers) != len(set(numbers)):
        raise LawScrapeError("article page contains duplicate article numbers")
    return articles


def diff_articles(previous: list[dict], current: list[dict]) -> dict:
    before = {article["article_number"]: article for article in previous}
    after = {article["article_number"]: article for article in current}
    ordered_numbers = list(before) + [number for number in after if number not in before]
    changes = []
    added = []
    removed = []
    modified = []

    for number in ordered_numbers:
        old = before.get(number)
        new = after.get(number)
        if old is None:
            added.append(number)
            changes.append({"article_number": number, "change": "added", "after": new["text"]})
        elif new is None:
            removed.append(number)
            changes.append({"article_number": number, "change": "removed", "before": old["text"]})
        elif comparison_text(old["text"]) != comparison_text(new["text"]):
            modified.append(number)
            changes.append(
                {
                    "article_number": number,
                    "change": "modified",
                    "before": old["text"],
                    "after": new["text"],
                }
            )

    return {
        "summary": {"added": added, "removed": removed, "modified": modified},
        "articles": changes,
    }


class Fetcher:
    def __init__(self, timeout: float = 30, attempts: int = 3, delay: float = 0.5):
        self.timeout = timeout
        self.attempts = attempts
        self.delay = delay
        self._requested = False
        self.ssl_context = ssl.create_default_context()
        # Taipei's otherwise valid chain omits Subject Key Identifier on one
        # certificate. Keep CA and hostname verification, but match browser/curl
        # behavior by disabling only OpenSSL's optional strict-chain checks.
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def __call__(self, url: str) -> str:
        if self._requested and self.delay:
            time.sleep(self.delay)
        self._requested = True
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        errors = []
        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self.ssl_context
                ) as response:
                    document = response.read().decode("utf-8", errors="replace")
                if not document.strip():
                    raise LawScrapeError(f"empty response from {url}")
                return document
            except (urllib.error.URLError, TimeoutError, LawScrapeError) as exc:
                errors.append(str(exc))
                if attempt + 1 < self.attempts:
                    time.sleep(2**attempt)
        raise LawScrapeError(
            f"failed to download {url} after {self.attempts} attempts: {errors[-1]}"
        )


def build_dataset(law_id: str, fetch) -> dict:
    history_url = absolute_url(HISTORY_PATH.format(law_id=law_id))
    metadata = parse_history(fetch(history_url), law_id)
    versions = []
    previous_articles = None

    for revision in metadata.pop("revisions"):
        articles = parse_articles(fetch(revision["full_text_url"]))
        official_amended_articles = []
        if revision["amended_text_url"]:
            official_amended_articles = parse_articles(fetch(revision["amended_text_url"]))

        version = {
            **revision,
            "article_count": len(articles),
            "articles": articles,
            "official_amended_article_numbers": [
                article["article_number"] for article in official_amended_articles
            ],
            "official_amended_articles": official_amended_articles,
            "changes_from_previous": (
                None if previous_articles is None else diff_articles(previous_articles, articles)
            ),
        }
        versions.append(version)
        previous_articles = articles

    dataset = {**metadata, "versions": versions}
    canonical = json.dumps(
        dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    dataset["content_hash"] = hashlib.sha256(canonical).hexdigest()
    return dataset


def write_if_changed(dataset: dict, output: Path) -> bool:
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LawScrapeError(f"cannot read existing output {output}: {exc}") from exc
        old_versions = existing.get("versions", [])
        if len(dataset["versions"]) < len(old_versions):
            raise LawScrapeError(
                "refusing to replace existing data with fewer revisions "
                f"({len(dataset['versions'])} < {len(old_versions)})"
            )
        if existing.get("content_hash") == dataset["content_hash"]:
            return False

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output.parent, delete=False
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--law-id", default="FL071776")
    parser.add_argument(
        "--output", type=Path, default=Path("laws/taipei/FL071776.json")
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--request-delay", type=float, default=0.5)
    parser.add_argument(
        "--check", action="store_true", help="download and validate without writing"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dataset = build_dataset(
            args.law_id,
            Fetcher(timeout=args.timeout, delay=args.request_delay),
        )
        if args.check:
            print(
                f"law={dataset['law_id']} versions={len(dataset['versions'])} "
                f"latest={dataset['versions'][-1]['date']} validation=ok"
            )
            return 0
        changed = write_if_changed(dataset, args.output)
    except LawScrapeError as exc:
        print(f"ERROR: {exc}")
        return 1

    state = "updated" if changed else "unchanged"
    print(
        f"law={dataset['law_id']} versions={len(dataset['versions'])} "
        f"latest={dataset['versions'][-1]['date']} output={args.output} state={state}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
