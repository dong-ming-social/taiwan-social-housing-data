# Taiwan Social Housing Data

臺灣社會住宅公開文件的結構化 JSON 資料集。目前收錄臺北市東明社會住宅相關文件，方便程式查詢、資料分析、搜尋與公共資訊應用。

## 收錄範圍

目前共收錄 12 份官方文件、95 頁：

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

每個 JSON 檔名均沿用原始 PDF 名稱，僅將副檔名改為 `.json`。

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

path = Path("附件3_所得級距分級標準表及租金補貼表.json")
data = json.loads(path.read_text(encoding="utf-8"))

for rent in data["structured_data"]["rent_after_subsidy"]:
    print(rent["room_type"], rent["tier_1_twd"], rent["source_pages"])
```

## 資料來源與品質

- 來源：[臺北市政府安心樂租網－東明社會住宅](https://rent.thurc.org.taipei/Attachments/dongming)
- 發布單位：臺北市住宅及都市更新中心
- 網站主管機關：臺北市政府都市發展局
- 原始 PDF 的來源網址與 SHA-256 均記錄於各 JSON。
- 所有 PDF 均已確認未加密，並完成逐頁文字、表格及圖像核對。

本資料集是官方文件的結構化整理成果，不是政府機關的正式法律解釋或申請審查依據。若內容與最新公告不同，應以發布單位的最新官方文件為準。

## 授權

本 repository 的資料選編、JSON schema、欄位整理與結構化成果採 [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) 授權，詳見 [LICENSE](LICENSE)。

官方文件原始內容不因收錄於本 repository 而被重新授權；其使用條件仍以[臺北市政府政府網站資料開放宣告](https://www.gov.taipei/News_Content.aspx?n=10FDEA7683714512&s=3B6C92FD22C01611&sms=AA987E1C50412097)及個別文件的權利聲明為準。使用或散布時請保留官方來源與本資料集出處。
