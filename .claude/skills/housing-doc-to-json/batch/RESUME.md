# 批次轉檔進度與接手說明

最後更新：2026-08-24。此檔案記錄一次大規模補齊作業的狀態，供 token 用盡或換 session 後接手。

## 背景：為什麼有這次作業

原本資料集只收錄 `dongming`（12 份）與 `nangangdepot1`（14 份）共 26 份 JSON。
盤點官方網站後發現實際有 **366 份** PDF，覆蓋率僅 7%。缺口不只是「還沒收的基地」，
還包括兩個既有基地本身的漏檔。

### 盤點方法（重要：只看附件頁會漏掉一大半）

官方文件散在**三種**頁面，必須全部抓才完整：

1. `/housing-sites/map` → 取得 42 個基地 slug。
2. `/Attachments/<slug>` → 32 個基地有附件頁；10 個回 HTTP 500。
   已驗證隨機無效 slug 也回 500，故 500 = 「該基地沒有附件頁」，不是 slug 猜錯。
   敦煌、信安、溪州等幸福住宅都屬此類。
3. `/news` 公告列表全 10 頁 → 75 篇 `/news/detail/<id>` 公告詳情頁。
   **這裡另有 147 份任何附件頁都看不到的 PDF**，包含既有兩基地的後續公告。

比對時務必先做 HTML entity 解碼與 URL 解碼，否則同一檔案會因編碼差異被重複計算。
與 repo 既有檔案比對時要忽略檔名序號前綴（`7.東明…` 對應 `東明…`）。

## 已完成

- `.venv` 已建立並安裝 `firecrawl-anydoc==0.1.9` + `pypdf` + `pdfplumber`（`.venv/` 已在 .gitignore）。
- 全站 366 份 PDF 的完整清單 → `portal_inventory.json`
  （每筆含 `bucket` / `stem` / `path` / `have` / `tier` / `src` / `dupe`）。
- 住戶規約手冊族已完成；`zhongnan/` 的永平規約副本依重複政策排除。
- 其餘 313 筆工作清單已全部完成，包含修復截斷的 `7-in-one-2/附件8_管理扣分規定.pdf`。
- 兩份來源路徑不同但同名的 `yir/簡報評選結果.pdf` 已用文件完整標題分別輸出，避免覆寫。
- 全庫完成 **365 份 JSON、4,292 頁、365 個唯一官方 PDF URL**；50 份掃描文件標記待 OCR。
- `README.md` 已更新收錄範圍、來源出處、品質限制與最新統計。
- `scripts/validate_dataset.py` 已加入，可重跑全庫結構、頁數、SHA-256、來源出處與重複政策驗證。

## 已排除的兩個假缺口（不要再把它們當缺檔）

1. `/documents/nangangdepot1/南港機廠社1區宅手冊.pdf`
   SHA-256 與既有的 `南港機廠社宅1區招租手冊.pdf` **完全相同**，是同一檔案以誤植檔名重複發布。
   已在 `portal_inventory.json` 標記 `dupe: true`。
2. `永平社會住宅住戶規約手冊(114年12月版).pdf` 同時掛在 `zhongnan/` 與 `yongping/` 兩個路徑，
   SHA-256 相同。已只保留 `yongping/`（該基地自己的資料夾），刪除 `zhongnan/` 的重複副本。

## 如何接著跑

```bash
cd /Users/dawei84/taiwan-social-housing-data
S=.claude/skills/housing-doc-to-json

# 重跑其餘文件（已下載的 PDF 會跳過、已存在的 JSON 會覆寫，可安全重複執行）
./.venv/bin/python $S/scripts/batch_convert.py \
    $S/batch/worklist_rest.json $S/batch/labels_rest.json

# 只重跑規約手冊族
./.venv/bin/python $S/scripts/batch_convert.py \
    $S/batch/worklist_handbook.json $S/batch/labels_handbook.json
```

`batch_convert.py` 是冪等的：PDF 預設下載到系統暫存區的
`taiwan-social-housing-pdf-cache/`，也可用 `HOUSING_PDF_CACHE` 指定；只有通過完整 PDF
與頁數檢查的快取才會重用。JSON 直接覆寫，中斷後重跑即可續做。

建議加 `-u` 讓 stdout 不緩衝，才能即時看進度：`./.venv/bin/python -u …`。
或直接數檔案：`find . -name '*.json' -not -path './.git/*' -not -path './.claude/*' | wc -l`。

## 資料夾命名規則

資料夾名 = PDF 網址中 `/documents/<bucket>/` 的那一段，與 skill 既有規則一致。
兩個例外：

- `/assets/attachments/*.pdf`（全市通用契約範本、包租代管申請書）沒有 slug，統一放 `citywide/`。
- 聯合招租案（`16-in-one`、`four-in-one-rental`、`4-in-one-xinglong_a` 等）不是單一基地，
  但仍以其 bucket 名建資料夾，以保留出處路徑。

## 還沒做的事（接手後要補）

1. **`structured_data` 只有基本層。** 批次轉檔產出的是
   `document_type` + `entities`（空陣列）+ `tables`（自動彙整），
   尚未逐份手寫型別專屬欄位（`penalty_rules`、`income_tiers`、`contract_terms` 等）。
   標準化條文（管理扣分規定、租賃契約書、不能補正事項、所得級距表）可沿用
   `dongming/` 或 `nangangdepot1/` 已撰寫好的內容，但 `pages[]` 必須保留各 PDF 自身逐字文字。
2. **`entities` 尚未填值**，全為空陣列。
3. **跨目錄相同內容仍保留。** 聯合招租案之間共用的標準附件若官方路徑、基地或公告脈絡不同，
   本輪依來源可追溯原則保留；只有上方列出的兩個明確重複發布被排除。
4. **無文字層的 PDF** 會被標記 `structured_data.requires_ocr: true` 並附 `ocr_note`，
   預設不做 OCR。若要 OCR 走 `scripts/ocr_vision.py`，並依 SKILL.md 改寫
   `metadata.parser` 為 `macos-vision-ocr`、清理文字時用 `scripts/clean_ocr_text.py`。
5. **尚未完成遠端 PR 交付。** 依 SKILL.md 規則不可直接推 main，需依規劃分批開
   squash-merge PR；執行前需修復 `gh` 的 GitHub 登入憑證。

## 分級參考

`portal_inventory.json` 的 `tier` 欄位是**依檔名關鍵字自動判定**，僅供排序參考、非官方分類：

- `high`（核心）：規約手冊、招租手冊、租賃契約書、所得級距與租金補貼表、應備文件、
  管理扣分規定、不能補正事項、切結書、招租公告、選屋手冊、徵件簡章等。
- `low`（次要）：評點分數公告、排序結果、複查申請表、已配租清冊、有線電視／網路方案、
  幼兒園簡章、評選結果、懶人包、平面圖等時效性或非結構化文件。
