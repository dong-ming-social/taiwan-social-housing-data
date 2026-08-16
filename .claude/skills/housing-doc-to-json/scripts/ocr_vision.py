#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR a scanned (image-only) PDF with macOS Vision — Traditional Chinese.

Use ONLY when a PDF has no text layer (anydoc raises UnsupportedError) AND the
user explicitly wants the text extracted. Text is OCR-derived: record the OCR
engine in metadata.parser and set structured_data.ocr_applied = true.

Requires (macOS only): pymupdf, pyobjc-framework-Vision, pyobjc-framework-Quartz.
    ./.venv/bin/python -m pip install pymupdf pyobjc-framework-Vision pyobjc-framework-Quartz

CLI:  python ocr_vision.py scanned.pdf            # prints ===PAGE n=== blocks
Import:  from ocr_vision import ocr_pdf            # -> {page_no: text}
"""
import sys
import pymupdf
import Quartz
import Vision
from Foundation import NSData

DPI = 300


def _cgimage(png_bytes):
    data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
    src = Quartz.CGImageSourceCreateWithData(data, None)
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def ocr_image(png_bytes, languages=("zh-Hant", "zh-Hans", "en")):
    cg = _cgimage(png_bytes)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)          # 0 = accurate (1 = fast, Latin-only — no CJK)
    req.setUsesLanguageCorrection_(True)
    req.setRecognitionLanguages_(list(languages))
    handler.performRequests_error_([req], None)
    lines = []
    for obs in (req.results() or []):
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        bb = obs.boundingBox()           # normalized, origin bottom-left
        lines.append((bb.origin.y + bb.size.height, bb.origin.x, cand[0].string()))
    lines.sort(key=lambda t: (-round(t[0], 3), t[1]))   # top->bottom, left->right
    return "\n".join(t[2] for t in lines)


def ocr_pdf(path, dpi=DPI):
    doc = pymupdf.open(path)
    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    out = {}
    for i in range(doc.page_count):
        png = doc.load_page(i).get_pixmap(matrix=mat).tobytes("png")
        out[i + 1] = ocr_image(png)
    return out


if __name__ == "__main__":
    for page, text in ocr_pdf(sys.argv[1]).items():
        print(f"===PAGE {page}===")
        print(text)
