#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean OCR text from a scanned government PDF.

- drops bare single-CJK-char lines (裝訂線／騎縫 binding-margin residue)
- drops `第N頁，共N頁` page footers
- rejoins OCR hard-wrapped lines into logical paragraphs

Import: clean_pages({page_no: raw_text}) -> (cleaned_pages, full_text, stats)
Never rewrites misrecognized characters — that would fabricate content.
"""
import re

SINGLE_CJK = re.compile(r"^[一-鿿]$")
FOOTER = re.compile(r"^第\s*\d+\s*頁[，,]\s*共\s*\d+\s*頁$")
MARKER = re.compile(
    r"^("
    r"[一二三四五六七八九十百]+、"
    r"|（[一二三四五六七八九十百]+）"
    r"|\d+、|（\d+）|\(\d+\)"
    r"|[壹貳參肆伍陸柒捌玖拾]+、"
    r"|附件[：:]?"
    r"|檔號[：:]|保存年限[：:]|發文日期[：:]|發文字號[：:]|依據[：:]|公告事項[：:]|主旨[：:]|受文者[：:]"
    r")")
TERMINAL = "。！？：；"


def _keep(line, stats):
    if SINGLE_CJK.match(line):
        stats["removed_binding_margin_lines"] += 1
        return False
    if FOOTER.match(line):
        stats["removed_footer_lines"] += 1
        return False
    return True


def _rejoin(lines):
    out = []
    for ln in (l.strip() for l in lines):
        if not ln:
            continue
        if out and not MARKER.match(ln) and out[-1][-1] not in TERMINAL:
            out[-1] += ln            # CJK: no separator between wrapped fragments
        else:
            out.append(ln)
    return out


def clean_pages(page_texts):
    """page_texts: {page_no: raw_text}. Returns (cleaned_pages, full_text, stats)."""
    stats = {"removed_binding_margin_lines": 0, "removed_footer_lines": 0}
    kept = {}
    for pg in sorted(page_texts):
        kept[pg] = [l for l in page_texts[pg].splitlines()
                    if l.strip() and _keep(l.strip(), stats)]
    cleaned_pages = {pg: "\n".join(_rejoin(ls)) for pg, ls in kept.items()}
    all_lines = [l for pg in sorted(kept) for l in kept[pg]]
    full_text = "\n".join(_rejoin(all_lines))     # cross-page rejoin
    return cleaned_pages, full_text, stats
