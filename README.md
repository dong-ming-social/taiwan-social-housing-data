# Taiwan Social Housing Data

臺灣社會住宅公開文件的結構化 JSON 資料集。目前收錄臺北市東明社會住宅、南港機廠社會住宅 1 區相關文件，方便程式查詢、資料分析、搜尋與公共資訊應用。

## 收錄範圍

目前共收錄 2 個社宅基地、26 份官方文件、215 頁。檔案依社宅基地分子資料夾存放。

### 東明社會住宅（`dongming/`，12 份、95 頁）

- 東明社會住宅住戶規約手冊（114 年 12 月版）
- 115 年東明社宅重新招租手冊
- 附件 2：租期及住宅相關補貼切結書
- 附件 3：所得級距分級標準表及租金補貼表
- 附件 5：臺北市歷次社宅其他特殊情形身分戶評點制辦理情形
- 附件 6：申請書封套
- 附件 7：申請社會住宅應備文件
- 附件 8：撤案申請書
- 附件 9：申請案不能補正與應補正事項
- 附件 10：管理扣分規定
- 附件 11：臺北市社會住宅租賃契約書
- 附件 12：免附家庭成員財稅資料

### 南港機廠社會住宅 1 區（`nangangdepot1/`，14 份、120 頁）

- 南港機廠社宅 1 區招租手冊
- 南港機廠社會住宅 1 區招租公告（掃描影像 PDF，內文以 macOS Vision OCR 擷取，詳見「資料來源與品質」）
- 附件 2：租期及住宅相關補貼切結書
- 附件 3：所得級距及分級補貼租金表
- 附件 4-1：申請書填寫範例（一般、低收入、原住民）
- 附件 4-2：申請書填寫範例（其他特殊情形身分戶）
- 附件 5：臺北市歷次社宅其他特殊情形身分戶評點制辦理情形（114.03）
- 附件 6：申請社會住宅應備文件
- 附件 9：申請案不能補正與應補正事項
- 附件 10：管理扣分規定
- 附件 11：臺北市社會住宅租賃契約書
- 附件 12：南港機廠社會住宅 1 區周邊教育及公共服務資源一覽表
- 附件 13：免附家庭成員財稅資料切結書
- 南港機廠社會住宅住戶規約手冊（115 年 1 月版）

每個 JSON 檔名均沿用原始 PDF 名稱，僅將副檔名改為 `.json`。同名附件（如各社宅的附件 10、11）以社宅資料夾區隔，內容各自對應該基地的官方 PDF。

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

- 來源：臺北市政府安心樂租網（[東明社會住宅](https://rent.thurc.org.taipei/Attachments/dongming)、[南港機廠社會住宅 1 區](https://rent.thurc.org.taipei/Attachments/nangangdepot1)）
- 發布單位：臺北市住宅及都市更新中心
- 網站主管機關：臺北市政府都市發展局
- 原始 PDF 的來源網址與 SHA-256 均記錄於各 JSON。
- 所有 PDF 均已確認未加密，並完成逐頁文字、表格及圖像核對。
- 多數文件的文字由 anydoc（firecrawl-anydoc 0.1.9）解析、pdfplumber 逐頁核對。**南港機廠社會住宅 1 區招租公告**為掃描影像 PDF、無文字層，anydoc 與 pdfplumber 均無法擷取，改以 **macOS Vision OCR（繁體中文）** 擷取內文（`metadata.parser.name` 為 `macos-vision-ocr`、`structured_data.ocr_applied` 為 `true`）。OCR 文字已再清理：濾除裝訂線／騎縫殘留（單一字元行，共 75 行）與「第N頁，共N頁」頁尾（23 行），並將硬斷行接回段落；`structured_data.full_text` 另提供跨頁接續之連續全文（`structured_data.ocr_cleaning` 記錄清理內容）。惟 OCR 仍可能含少量字元辨識誤差，如需精確引用請對照官方 PDF。

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
