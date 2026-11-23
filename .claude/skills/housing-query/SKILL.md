---
name: housing-query
description: 查詢臺北市社會住宅資料集（Taiwan Social Housing Data）回答社宅問題並附官方出處：各基地招租公告、資格、應備文件、租金與補貼級距、租賃契約、住戶規約、管理扣分、社宅位置與地址、行政區清單、《臺北市社會住宅出租辦法》條文與修法沿革。當使用者問到臺北社宅、社會住宅、公宅、安心樂租、東明／南港機廠／興隆／青年／莒光等基地、聯合招租、青年創新回饋計畫、社宅租金或申請條件時使用。不用於新增或轉檔資料（那是 housing-doc-to-json）。
---

# 社宅資料查詢

用 `scripts/query.py` 從資料集挑出需要的片段來回答，不要整份讀入 JSON（單檔可達 700KB）。
每個回答都要附官方出處。

## 資料來源

`query.py` 依序找資料：`--repo` 或環境變數 `HOUSING_DATA_REPO` → 從目前目錄往上找 repo clone →
GitHub Raw（`dong-ming-social/taiwan-social-housing-data` 的 `main`）。輸出的 `source` 欄位會標示實際來源。
在 repo 裡（例如 `develop` 或功能分支）會讀本機檔案；要以已發布資料為準時加 `--remote`。
沒有網路又不在 repo 裡時只剩隨附的 `reference/catalog.json`，能列出有哪些文件，但讀不到內容，要跟使用者說明。

```bash
Q=".claude/skills/housing-query/scripts/query.py"   # 安裝在 ~/.claude/skills 時改成該路徑
python3 $Q folders --keyword 東明                          # 找資料夾（基地／專案）
python3 $Q docs --folder dongming --type rent_table        # 篩選文件
python3 $Q docs --keyword "契約 自建"                       # 標題關鍵字（空白分隔＝都要符合）
python3 $Q search "寵物" --folder dongming                  # 全文搜尋，回傳頁碼與片段
python3 $Q show <path> --field rent_after_subsidy          # 結構化欄位
python3 $Q show <path> --pages 8,10-11                     # 指定頁原文與表格
python3 $Q show <path> --sections                          # 全部章節內容
python3 $Q locations --district 文山 --status 已完工        # 社宅位置
python3 $Q law                                             # 出租辦法版本列表
python3 $Q law --article 3,23 --changes                    # 最新版條文與修法前後對照
python3 $Q law --version 3 --article 5                     # 指定舊版條文
```

## 怎麼找到對的檔案

1. **先判斷問題類型**
   - 地點、地址、哪一區有社宅、施工進度 → `locations`
   - 法規條文、修法、哪一條改了什麼 → `law`
   - 其他（招租、資格、租金、契約、規約、扣分、應備文件）→ 文件，往下走
2. **找資料夾**：`folders --keyword <基地名>`。資料夾名稱沿用官網網址 slug，看 `label` 對中文名。
   - 單一基地的招租附件在該基地資料夾，例如 `dongming/`、`nangangdepot1/`。
   - 多處基地一起招租放在聯合招租資料夾（`*-in-one*`、`immediate/`、`zhongnan/` 等），問某基地時這些也要查。
   - 全市通用的契約範本、申請書放在 `citywide/`；青年創新回饋計畫在 `yir/`、`2025/`。
3. **挑文件**：`docs --folder <folder>`，依 `document_type` 和 `title` 挑。
   | document_type | 內容 |
   | --- | --- |
   | `announcement` | 招租公告、評點結果、抽籤公告 |
   | `rent_table` / `reference_table` | 租金、所得級距、補貼對照 |
   | `required_documents` / `form` / `declaration` | 應備文件、申請書、切結書 |
   | `lease_contract` | 租賃契約書範本 |
   | `regulation` / `guidance` | 管理扣分規定、須知、作業要點 |
   | `resident_handbook` / `rental_handbook` | 住戶規約手冊、招租手冊 |
   | `floor_plan` | 平面圖 |
   有 `structured_fields` 的文件（例如 `rent_after_subsidy`、`income_tiers`）先用 `show --field` 取，不用自己解析表格。
4. **找不到標題時**：用 `search`，在本機可搜全庫。遠端模式一次最多 15 份文件，要先用 `--folder`、`--type` 或 `--title` 縮小範圍。
5. **核對頁面**：用 `show --pages` 讀命中頁的完整文字與表格，再回答。不要只靠搜尋片段下結論。

## 回答規則

- **出處**：每個事實附文件標題、頁碼（`page` 或 `source_pages`）和 `citation.official_pdf_url`。
  位置資料附 `address_source_url`；法規附 `source_url` 和版本日期。
- **地址精度**：`address_precision` 為 `nearby` 時要說明是依官方座標配對的最近門牌（距離 `address_distance_m` 公尺），
  官方原始地號在 `official_location`。
- **版本與時效**：同一基地常有多期文件，比較 `version` 和標題年份，以最新的為準，並寫出用的是哪一期。
  `locations` 要提 `updated_at`。資料集是官方文件的整理，不是即時資料。
- **OCR**：`requires_ocr: true` 的文件是掃描檔，沒有文字內容。直接說資料集裡沒有文字，請使用者看官方 PDF，不要猜。
- **不臆測**：資料裡沒有的資訊（例如尚未公告的租金）就說沒有，不要用其他基地的數字推估。
- **免責**：涉及申請資格、租金或法律效果時，提醒「正式申請以臺北市住宅及都市更新中心最新公告為準」；
  法規提醒「正式引用以臺北市政府公報為準」。
- **轉載出處**：使用者要把結果拿去發布時，提醒兩項出處都要標示：
  「資料來源：臺北市住宅及都市更新中心（安心樂租網）」與「本資料整理自 Taiwan Social Housing Data，採 CC BY 4.0 授權」。

## 維護

`reference/catalog.json` 由 `scripts/build_catalog.py` 從資料集產生，每日更新 workflow 會重建；
PR 驗證用 `--check` 確認它沒有過期。新增或修改文件 JSON 之後要重新執行：

```bash
python .claude/skills/housing-query/scripts/build_catalog.py
```
