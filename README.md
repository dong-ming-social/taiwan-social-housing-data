# Taiwan Social Housing Data

臺灣社會住宅公開文件的結構化 JSON 資料集。目前收錄臺北市住宅及都市更新中心安心樂租網公開的社宅基地、聯合招租、青年創新回饋計畫及全市通用文件，方便程式查詢、資料分析、搜尋與公共資訊應用。

## 收錄範圍

目前共收錄 **365 份官方文件、4,292 頁**，分布於 39 個來源資料夾。`citywide/` 收錄沒有基地 slug 的全市通用附件；聯合招租與專案文件則保留官方網址中的 bucket 名稱。

| 資料夾 | 文件數 | 頁數 | 待 OCR 文件數 |
| --- | ---: | ---: | ---: |
| `16-in-one/` | 10 | 71 | 2 |
| `19-in-one-zhangxinshuian/` | 12 | 331 | 1 |
| `2025/` | 4 | 11 | 2 |
| `4-in-one-xinglong_a/` | 30 | 467 | 1 |
| `5-in-one-xinglong_D1/` | 10 | 55 | 1 |
| `7-in-one-2/` | 11 | 52 | 1 |
| `aboriginal-rental/` | 9 | 94 | 3 |
| `apply/` | 1 | 12 | 0 |
| `citywide/` | 30 | 365 | 4 |
| `dalongdong/` | 1 | 33 | 0 |
| `dongming/` | 17 | 151 | 2 |
| `elder-project/` | 6 | 35 | 1 |
| `four-in-one-rental/` | 15 | 355 | 2 |
| `guangci_3/` | 2 | 37 | 0 |
| `guangci_d_e/` | 2 | 71 | 0 |
| `hesingshueian/` | 1 | 35 | 0 |
| `huarong/` | 2 | 21 | 0 |
| `immediate/` | 14 | 120 | 0 |
| `jiankang/` | 8 | 57 | 0 |
| `jiuzong/` | 1 | 37 | 0 |
| `juguang/` | 26 | 269 | 2 |
| `ming-lun/` | 9 | 96 | 2 |
| `mydata/` | 1 | 12 | 0 |
| `nangangdepot1/` | 22 | 214 | 1 |
| `qingnian/` | 7 | 62 | 1 |
| `qingnian-2/` | 1 | 34 | 0 |
| `qingnian_1_joyful/` | 16 | 130 | 1 |
| `ruiguang/` | 13 | 112 | 4 |
| `svenly3/` | 7 | 25 | 1 |
| `three-in-one-rental/` | 5 | 96 | 1 |
| `xiaowan/` | 11 | 191 | 3 |
| `xinglong/` | 14 | 117 | 0 |
| `xinglong-1/` | 3 | 44 | 2 |
| `xinglong_e/` | 11 | 99 | 1 |
| `xingshan/` | 1 | 45 | 0 |
| `xinqiyan/` | 6 | 87 | 2 |
| `yir/` | 19 | 165 | 8 |
| `yongping/` | 1 | 21 | 0 |
| `zhongnan/` | 6 | 63 | 1 |

JSON 檔名原則上沿用原始 PDF 名稱，僅將副檔名改為 `.json`。不同官方路徑出現同名 PDF 時，檔名會加入文件標題以避免覆寫；同名標準附件則以來源資料夾區隔。

## JSON 結構

所有檔案使用一致的頂層欄位：

| 欄位 | 說明 |
| --- | --- |
| `metadata` | 文件名稱、版本、語言、頁數、PDF 雜湊與解析工具資訊 |
| `source` | 官方 PDF 網址、發布單位、出處及權利說明 |
| `sections` | 章節、條款、內容及來源頁碼 |
| `structured_data` | 資格、應備文件、租金、契約、規範、費用、時段及聯絡資訊等結構化內容 |
| `pages` | 逐頁文字、表格、圖片標記與空白頁資訊 |

結構化資料均保留 `source_pages`，可回溯至原始 PDF 頁面。無文字層的圖像內容僅標記所在頁面，不臆測圖中資訊。

## 使用範例

```python
import json
from pathlib import Path

path = Path("dongming/附件3_所得級距分級標準表及租金補貼表.json")
data = json.loads(path.read_text(encoding="utf-8"))

for rent in data["structured_data"]["rent_after_subsidy"]:
    print(rent["room_type"], rent["tier_1_twd"], rent["source_pages"])
```

## 新增資料

`.claude/skills/housing-doc-to-json/` 收錄可重複使用的轉檔技能，封裝「下載 → anydoc 解析 → 產生 repo schema JSON → 更新 README → 開 PR squash merge」的完整流程。在此 repo 目錄以 Claude Code 開新 session 後，貼上新的 PDF 連結或附件下載頁即可觸發；詳見該資料夾的 `SKILL.md` 與 `reference/schema.md`。

## 資料來源與品質

- 來源：臺北市政府安心樂租網。完整盤點同時使用[社宅基地地圖](https://rent.thurc.org.taipei/housing-sites/map)、各基地 `/Attachments/<slug>` 附件頁，以及[最新消息](https://rent.thurc.org.taipei/news)全 10 頁的公告詳情附件。
- 發布單位：臺北市住宅及都市更新中心
- 網站主管機關：臺北市政府都市發展局
- 每份 JSON 的 `source` 均記錄官方 PDF 網址、發布單位、網站主管機關及來源出處文字；`metadata.pdf_sha256` 可用於核對原始檔內容。
- 多數文件由 [anydoc](https://github.com/firecrawl/anydoc)（firecrawl-anydoc 0.1.9）與 pdfplumber 擷取文字及表格。50 份無文字層的掃描 PDF 只標記 `structured_data.requires_ocr: true`，未臆測影像內容；既有已套用 OCR 的文件則在 `metadata.parser` 與 `structured_data.ocr_applied` 記錄方法與限制。
- 全庫驗證會檢查 JSON 結構、頁數、逐頁編號、SHA-256、官方 URL 唯一性與來源出處欄位；資料仍可能包含 PDF 文字層本身的排版或字元問題，精確引用時請對照 `source.official_pdf_url` 指向的官方 PDF。

本資料集是官方文件的結構化整理成果，不是政府機關的正式法律解釋或申請審查依據。若內容與最新公告不同，應以發布單位的最新官方文件為準。

## 授權

本 repository 的資料選編、JSON schema、欄位整理與結構化成果採 [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) 授權，詳見 [LICENSE](LICENSE)。

官方文件原始內容不因收錄於本 repository 而被重新授權；其使用條件仍以[臺北市政府政府網站資料開放宣告](https://www.gov.taipei/News_Content.aspx?n=10FDEA7683714512&s=3B6C92FD22C01611&sms=AA987E1C50412097)及個別文件的權利聲明為準。依該開放宣告，官方資料可無償、非專屬、得再授權地重製、改作、編輯、公開傳輸及其他利用，**惟使用時應註明出處**。

## 出處標示

使用或散布本資料集（含衍生成果）時，請一併保留「官方原始來源」與「本資料集」兩項出處。

**官方原始來源**

- 發布單位：臺北市住宅及都市更新中心
- 網站主管機關：臺北市政府都市發展局
- 來源網站：臺北市政府安心樂租網（<https://rent.thurc.org.taipei/>）
- 各檔對應之官方 PDF 網址與 SHA-256 均記錄於該 JSON 的 `source` 與 `metadata` 欄位。

**本資料集**

- 名稱：Taiwan Social Housing Data
- 來源：dwhao84/taiwan-social-housing-data（GitHub）
- 授權：資料整理與結構化成果採 CC BY 4.0

**引用範例**

- 官方文件：「資料來源：臺北市住宅及都市更新中心，《東明社會住宅住戶規約手冊（114 年 12 月版）》，臺北市政府安心樂租網，<https://rent.thurc.org.taipei/>。」（引用時網址與句號請勿相連，以免「。」被一併複製而無法開啟）
- 本資料集：「本資料整理自 Taiwan Social Housing Data（dwhao84/taiwan-social-housing-data），採 CC BY 4.0 授權。」

> 提醒：開放宣告之授權僅及於著作權，不含專利、商標及市府標誌；部分經特別聲明之影音、圖像等素材不在授權範圍內。資料中如涉個人資料，使用者應自行遵守《個人資料保護法》。使用時不得惡意變更原始資訊致與原意不符。
