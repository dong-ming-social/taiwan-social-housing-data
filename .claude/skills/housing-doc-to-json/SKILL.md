---
name: housing-doc-to-json
description: Convert a Taiwan social-housing PDF (e.g. 東明社宅 附件 downloads from rent.thurc.org.taipei) into this repo's structured JSON schema using the anydoc pipeline, then update README and open a squash-merge pull request. Use whenever the user pastes a PDF URL, an attachment-download page, or a new document to add to the taiwan-social-housing-data dataset.
---

# Housing document → JSON pipeline

Turns an official social-housing PDF into a repo-schema `.json` file, updates
`README.md`, and ships it via a squash-merged PR. anydoc parses the PDF to text;
the JSON is this repo's own schema (anydoc does **not** emit JSON directly).

## When to use
- User pastes one or more PDF URLs from `rent.thurc.org.taipei/documents/...`.
- User pastes an attachment-download page's HTML — extract every PDF link, then
  diff against existing `*.json` files and process only the missing ones.
- User asks to add/update a document in the dataset.

## Prerequisites (one-time per machine)
Homebrew Python is externally managed and its `pip` is not on PATH; always use a venv.
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install "firecrawl-anydoc==0.1.9" pypdf pdfplumber
```
Pin `firecrawl-anydoc==0.1.9` — the `metadata.parser` block in every existing JSON records that version.

## Workflow

### 1. Resolve the document list
- Single URL → one document.
- Download-page HTML → collect every `/documents/dongming/*.pdf` href, decode the
  `&#xNNNN;` entities to real filenames, and **skip any whose `.json` already
  exists** (match by the base filename with extension changed to `.json`). Confirm
  the final list with the user if it is large.

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

### 4. Build the JSON (use the helper)
`scripts/pdf_to_json.py` builds `metadata` / `source` / `sections` / `pages`
automatically from the PDF and merges hand-authored `structured_data`. See
`reference/schema.md` for the full schema and the `document_type` / structured
conventions. Author `structured_data` faithfully from the extracted text — **never
invent content for image-only pages**; mark them with the standard `image_note`.

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
