# Taiwan Social Housing Data

臺灣社會住宅公開文件的結構化 JSON 資料集。目前收錄臺北市住宅及都市更新中心安心樂租網公開的社宅基地、聯合招租、青年創新回饋計畫及全市通用文件，方便程式查詢、資料分析、搜尋與公共資訊應用。

## 收錄範圍

目前共收錄 **382 份官方文件、4,406 頁**，分布於 41 個來源資料夾。`citywide/` 收錄沒有基地 slug 的全市通用附件；聯合招租與專案文件則保留官方網址中的 bucket 名稱。

| 資料夾 | 繁體中文說明 | 文件數 | 頁數 | 待 OCR 文件數 |
| --- | --- | ---: | ---: | ---: |
| `16-in-one/` | 小彎等 16 處零星空戶暨候補戶聯合招租 | 10 | 71 | 2 |
| `19-in-one-zhangxinshuian/` | 樟新水岸等社宅與幸福住宅聯合招租 | 12 | 331 | 1 |
| `2025/` | 東明、興隆 E 區青年創新回饋計畫（民國 114 年） | 4 | 11 | 2 |
| `4-in-one-xinglong_a/` | 興隆 A、樟新水岸、經貿及六張犁社宅聯合招租 | 30 | 467 | 1 |
| `5-in-one-xinglong_D1/` | 興隆 D1 區等 5 處零星空戶聯合招租 | 10 | 55 | 1 |
| `7-in-one-2/` | 福星等 7 處隨到隨辦招租 | 11 | 52 | 1 |
| `aboriginal-rental/` | 社會住宅原住民族專案招租 | 9 | 94 | 3 |
| `apply/` | 安心樂租網申請操作說明 | 1 | 12 | 0 |
| `citywide/` | 全市通用契約、申請書與專案附件 | 30 | 365 | 4 |
| `dalongdong/` | 大龍峒社會住宅 | 1 | 33 | 0 |
| `dongming/` | 東明社會住宅 | 17 | 151 | 2 |
| `elder-project/` | 社會住宅青銀換居計畫 | 6 | 35 | 1 |
| `four-in-one-rental/` | 廣慈、行善及斯文里三期等聯合招租 | 15 | 355 | 2 |
| `guangci_3/` | 廣慈博愛園區社會住宅 3 區 | 2 | 37 | 0 |
| `guangci_d_e/` | 廣慈博愛園區社會住宅 1、2 區 | 2 | 71 | 0 |
| `hesingshueian/` | 和興水岸社會住宅 | 1 | 35 | 0 |
| `huarong/` | 華榮社會住宅 | 2 | 21 | 0 |
| `immediate/` | 興隆 D1 區等 11 處零星空戶暨候補戶招租 | 14 | 120 | 0 |
| `jiankang/` | 健康社會住宅 | 8 | 57 | 0 |
| `jiuzong/` | 舊宗社會住宅 | 1 | 37 | 0 |
| `juguang/` | 莒光社會住宅 | 26 | 269 | 2 |
| `lixing-jingfeng-1/` | lixing-jingfeng-1 | 10 | 91 | 1 |
| `ming-lun/` | 明倫社會住宅 | 9 | 96 | 2 |
| `mydata/` | MyData 線上申請操作說明 | 1 | 12 | 0 |
| `nangangdepot1/` | 南港機廠社會住宅 1 區 | 22 | 214 | 1 |
| `only-news/` | only-news | 7 | 23 | 1 |
| `qingnian/` | 青年社會住宅 1 區 | 7 | 62 | 1 |
| `qingnian-2/` | 青年社會住宅 2 區 | 1 | 34 | 0 |
| `qingnian_1_joyful/` | 青年 1 區暨洲美等幸福住宅聯合招租 | 16 | 130 | 1 |
| `ruiguang/` | 瑞光社會住宅 | 13 | 112 | 4 |
| `svenly3/` | 斯文里三期整宅及中繼住宅 | 7 | 25 | 1 |
| `three-in-one-rental/` | 木柵、金龍及大橋頭等社宅聯合招租 | 5 | 96 | 1 |
| `xiaowan/` | 小彎社會住宅 | 11 | 191 | 3 |
| `xinglong/` | 興隆社會住宅 D2 區 | 14 | 117 | 0 |
| `xinglong-1/` | 興隆社會住宅 D1 區 | 3 | 44 | 2 |
| `xinglong_e/` | 興隆社會住宅 E 區 | 11 | 99 | 1 |
| `xingshan/` | 行善社會住宅 | 1 | 45 | 0 |
| `xinqiyan/` | 新奇岩社會住宅 | 6 | 87 | 2 |
| `yir/` | 青年創新回饋計畫跨基地公告 | 19 | 165 | 8 |
| `yongping/` | 永平社會住宅 | 1 | 21 | 0 |
| `zhongnan/` | 中南社會住宅及永平聯合招租 | 6 | 63 | 1 |

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

## 社宅位置 API

`api/v1/` 提供不需要 API key、可直接由 GitHub Raw 讀取的臺北市社宅位置靜態 API。資料涵蓋已完工、施工中、待開工及規劃中的個別住宅基地，並依行政區提供拆分檔案。

| 端點 | 說明 |
| --- | --- |
| [`api/v1/index.json`](api/v1/index.json) | API 版本、資料來源與端點索引 |
| [`api/v1/housing-locations.json`](api/v1/housing-locations.json) | 全部社宅位置 |
| [`api/v1/districts.json`](api/v1/districts.json) | 12 個行政區、筆數與區域端點 |
| `api/v1/districts/{district-code}.json` | 指定行政區，例如 `wenshan.json` |

每筆位置都包含可閱讀的 `address`。`address_precision` 說明地址精度：`exact` 是官方門牌、`intersection` 是官方路口、`nearby` 則是依官方基地座標配對的最近門牌；後者會同時提供 `address_distance_m`。政府原始地址或地號保留於 `official_location`，不會與整理後地址混淆。

```python
import json
from urllib.request import urlopen

url = (
    "https://raw.githubusercontent.com/dong-ming-social/"
    "taiwan-social-housing-data/main/api/v1/districts/wenshan.json"
)
with urlopen(url) as response:
    data = json.load(response)

for housing in data["items"]:
    print(housing["name"], housing["address"], housing["address_precision"])
```

位置清單每日與官方[臺北市社會住宅興建工程進度](https://data.taipei/dataset/detail?id=659c3565-df41-4f80-915f-95e83071bdcd)同步；只有地號或缺少門牌時，使用每月更新的[臺北市門牌位置數值資料](https://data.taipei/dataset/detail?id=b7c8e724-1e98-45ee-a0bd-f3840623ed97)補成可導航地址。規劃案若尚無座標，則以有官方出處的人工覆寫資料補齊。這些靜態檔案沒有即時查詢伺服器的可用性保證，正式申請或法律用途仍應以政府最新公告為準。

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

## 每日自動更新

GitHub Actions 於每天 **06:20（Asia/Taipei）** 執行「每日更新社宅官方文件」，也可從 Actions 頁面手動執行。流程會重新盤點基地地圖、基地附件頁、最新消息公告與全站下載頁，並重新下載目前在線的 PDF 比對 SHA-256，因此能偵測「網址不變、內容被官方替換」的情況。

- 新 PDF 會自動轉成 JSON；同一網址內容更新時會重建原 JSON。
- 官網不再連結的文件只在 inventory 標記 `active: false`，不會自動刪除歷史資料。
- 若本次找到的文件少於上次有效盤點的 90%，流程會失敗並停止，不會大量誤標下架。
- 全庫驗證通過且確實有差異時，才會以 `dwhao84/automated-housing-update` 建立或更新 PR；**不會自動合併**。
- 自動 commit 使用 `Da Wei Hao <dawei84@hotaileasing.com.tw>`，不加入 AI 共同作者。

首次啟用時，repository 管理者需在 **Settings → Actions → General → Workflow permissions** 允許 GitHub Actions 建立 pull request。workflow 僅申請 `contents: write` 與 `pull-requests: write`。

本機可用下列命令先做唯讀盤點，或完整演練：

```bash
# 只盤點官方連結，不下載 PDF、不修改 repo
./.venv/bin/python .claude/skills/housing-doc-to-json/scripts/daily_update.py --discover-only

# 完整更新與 SHA 比對
./.venv/bin/python .claude/skills/housing-doc-to-json/scripts/daily_update.py
```

## 資料來源與品質

- 來源：臺北市政府安心樂租網。完整盤點同時使用[社宅基地地圖](https://rent.thurc.org.taipei/housing-sites/map)、各基地 `/Attachments/<slug>` 附件頁，以及[最新消息](https://rent.thurc.org.taipei/news)全 10 頁的公告詳情附件。
- 發布單位：臺北市住宅及都市更新中心
- 網站主管機關：臺北市政府都市發展局
- 每份 JSON 的 `source` 均記錄官方 PDF 網址、發布單位、網站主管機關及來源出處文字；`metadata.pdf_sha256` 可用於核對原始檔內容。
- 多數文件由 [anydoc](https://github.com/firecrawl/anydoc)（firecrawl-anydoc 0.1.9）與 pdfplumber 擷取文字及表格。52 份無文字層的掃描 PDF 只標記 `structured_data.requires_ocr: true`，未臆測影像內容；既有已套用 OCR 的文件則在 `metadata.parser` 與 `structured_data.ocr_applied` 記錄方法與限制。
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
