---
name: housing-doc-to-json
description: Convert a Taiwan social-housing PDF (e.g. 東明社宅 附件 downloads from rent.thurc.org.taipei) into this repo's structured JSON schema using the anydoc pipeline, then update README and open a squash-merge pull request. Use whenever the user pastes a PDF URL, an attachment-download page, or a new document to add to the taiwan-social-housing-data dataset.
---

# Housing document → JSON pipeline

Turns an official social-housing PDF into a repo-schema `.json` file, updates
`README.md`, and ships it via a squash-merged PR. [anydoc](https://github.com/firecrawl/anydoc)
parses the PDF to text; the JSON is this repo's own schema (anydoc does **not**
emit JSON directly).

## When to use
- User pastes one or more PDF URLs from `rent.thurc.org.taipei/documents/...`.
- User pastes an attachment-download page's HTML — extract every PDF link, then
  diff against existing `*.json` files and process only the missing ones.
- User asks to add/update a document in the dataset.

## Repo layout (multi-site)
Files are organised **one folder per housing site**, named by the URL slug in
`/documents/<site>/...` (e.g. `dongming/`, `nangangdepot1/`). Different sites
reuse the same attachment names (附件10, 附件11, …) with different content, so the
site folder is what keeps them apart — **never write a second site's files to the
repo root**. When a new site appears, create `<site>/` and put every JSON there.

## Prerequisites (one-time per machine)
Homebrew Python is externally managed and its `pip` is not on PATH; always use a venv.
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install "firecrawl-anydoc==0.1.9" pypdf pdfplumber
```
Pin `firecrawl-anydoc==0.1.9` — the `metadata.parser` block in every existing JSON records that version.
Upstream project: <https://github.com/firecrawl/anydoc> (installed via the `firecrawl-anydoc` PyPI package).
Note: existing JSON `metadata.parser.repository` records a fork URL for provenance of what was actually used — leave those values as-is unless doing a deliberate metadata migration.

## Workflow

### 1. Resolve the document list
- Note the **site slug** from the URL path (`/documents/<site>/`) — it is the
  output folder and the base for every `official_pdf_url`.
- Single URL → one document.
- Download-page HTML → collect every `/documents/<site>/*.pdf` href, decode the
  `&#xNNNN;` entities to real filenames, and **skip any whose `<site>/*.json`
  already exists**. Confirm the final list with the user if it is large.

### 2. Download & verify (into scratchpad, never commit the PDF)
Python 3.14's `urllib` rejects this host's TLS cert — use `curl`:
```bash
curl -sSL -o doc.pdf "https://rent.thurc.org.taipei/documents/dongming/<percent-encoded-name>.pdf"
file doc.pdf                 # confirm it is a PDF and page count
shasum -a 256 doc.pdf        # -> metadata.pdf_sha256
```
Check encryption/pages with pypdf (`PdfReader(f).is_encrypted`, `len(.pages)`).
If a re-downloaded PDF's sha256 equals the value already recorded in its JSON,
the source is unchanged — leave that file as-is and tell the user.

### 3. Extract & convert
- `anydoc.to_markdown(path)` for the overall structure.
- `pdfplumber` per page for clean `text`, `tables`, `image_count` — it is more
  reliable than anydoc's markdown for multi-column legal layouts.
- **Scanned / image-only PDFs**: anydoc raises `UnsupportedError` ("PDF has no
  extractable text … OCR is required") and pdfplumber returns empty text. By
  default do **not** OCR or guess — emit the JSON (the helper handles empty text:
  pages get `has_text:false` + `image_note`), set a fitting `document_type` (e.g.
  `announcement`) and `structured_data.requires_ocr:true` with a note, and tell
  the user it has no extractable text.
  - **If the user asks to OCR it**: use `scripts/ocr_vision.py` (macOS Vision,
    Traditional Chinese — needs `pymupdf` + `pyobjc-framework-Vision`/`-Quartz`).
    `ocr_pdf(path)` returns `{page_no: text}`. Then set each page's `text`/`has_text`,
    rebuild `sections`, set `structured_data.ocr_applied:true` (drop `requires_ocr`),
    and record OCR provenance in `metadata.parser` (`name:"macos-vision-ocr"`, level
    accurate, languages, rasterizer pymupdf, dpi) instead of anydoc — the text did
    not come from anydoc. Warn that OCR text may contain errors and that rotated
    binding-margin single characters (裝/訂/線/騎) are scan artifacts, not content.
  - **Cleaning OCR text** (if asked): drop bare single-CJK-char lines (裝訂線／騎縫
    residue) and `第N頁，共N頁` footers, then rejoin OCR hard-wraps into paragraphs —
    glue a line onto the previous unless it starts a structural marker (一、／（一）／
    1、／（1）／附件…) or the previous line ended in 。！？：；. Provide the cross-page
    continuous text as `structured_data.full_text`, keep per-page cleaned text in
    `pages[].text`, and record what was stripped in `structured_data.ocr_cleaning`.
    Do NOT rewrite misrecognized characters — that would fabricate content.
- **Table layouts vary between sites/versions** (e.g. 附件5 exists in an 8-column
  form with 行政區 and a 7-column form without). Detect column count from the header
  row; don't hard-code indices.

### 4. Build the JSON (use the helper)
`scripts/pdf_to_json.py` builds `metadata` / `source` / `sections` / `pages`
automatically and merges hand-authored `structured_data`. Import `build()` and pass
`official_pdf_url` for the current site (the module's default `BASE` is dongming;
`build(..., official_pdf_url="https://rent.thurc.org.taipei/documents/<site>/"+quote(name))`),
and write the result to `<site>/<doc_name>.json`. See `reference/schema.md` for the
full schema and `document_type` conventions. Author `structured_data` faithfully
from the extracted text — **never invent content for image-only pages**; mark them
with the standard `image_note`. Standardised clauses (e.g. 附件10 管理扣分規定) may
reuse another site's authored `penalty_rules`, but `pages[]` must carry this PDF's
own verbatim text.

### 5. Update README.md
Add the document to the 收錄範圍 list (numeric order) and bump the
「共收錄 N 份官方文件、M 頁」 counts (M = sum of every JSON's `page_count`).

### 6. Ship via squash-merge PR
Never commit to `main` directly.
```bash
git checkout -b add-<slug>
git add <new>.json README.md
git commit -m "<message>"        # end with the Co-Authored-By trailer
git push -u origin add-<slug>
gh pr create --title "..." --body "..."
gh pr merge --squash --delete-branch
git checkout main && git pull
```

## Verify
- `python3 -c "import json; json.load(open('<file>.json'))"` parses for every file.
- Spot-check `pages[].text` and tables against the PDF; confirm sha256 and page counts.
- `gh pr view` shows the PR merged and `main` contains the new files + README bump.
