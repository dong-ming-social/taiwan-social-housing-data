# 每日更新命名衝突修正與驗證

## 重現

以 upstream/main `3cd14e0` 的暫存副本執行完整更新，使用專案指定依賴。
發現 365 個連結，合併後 inventory 401 筆（36 筆 inactive、2 筆 dupe）。
新增 17 份文件後，驗證器拒絕 `yir/簡報評選結果.json`。
該輸出內的來源為：

https://rent.thurc.org.taipei/documents/yir/minglun/簡報評選結果.pdf

## 修正

- `output_rules.py` 共用原有三個禁用路徑，驗證要求維持不變。
- 新文件預設採原始檔名；占用或禁用時採來源父目錄前綴，仍衝突則從 `_2` 起遞增。
- 明確的 output_stem 若占用或禁用，回報來源與原因並停止，保留既有檔案。
- 既有來源以原輸出名稱更新，公開 JSON schema 與 API 路徑維持不變。
- `HOUSING_CONVERSION_LOG` 指定 JSONL 紀錄位置，預設 `/tmp/housing-conversions.jsonl`。
  記錄來源 URL、輸出、開始／完成／失敗／拒絕狀態及完成時的 SHA-256。
- CI 即使失敗仍展示已產生摘要並保存摘要與紀錄；提交與 PR 步驟仍受成功條件限制。

## Action 相容性

採官方 Node.js 24 穩定版本：checkout v5、setup-python v6、cache v5、upload-artifact v6。
需要 Actions Runner >= 2.327.1；現有 GitHub-hosted ubuntu-latest 符合要求。

官方說明：
- https://github.com/actions/checkout/tree/v5
- https://github.com/actions/setup-python/tree/v6
- https://github.com/actions/cache/tree/v5
- https://github.com/actions/upload-artifact/tree/v6

## 驗證結果

- 17 項 tests/ 測試、5 項位置 API 測試、6 項全臺來源測試通過。
- 基準資料集：382 文件、4,406 頁，驗證通過。
- 修正版在獨立暫存副本使用重現時相同的 discovery 與下載 PDF：新增 17、更新 0。
- 更新後：399 文件、4,703 頁、399 個唯一官方 URL，完整資料驗證通過。
- 17 筆完成紀錄的 URL 均與實際 JSON source.official_pdf_url 相同。
- 問題文件改為 `yir/minglun_簡報評選結果.json`。
- 相同 discovery/PDF 再次執行：新增 0、更新 0。
- 目前尚無 api/v2/index.json，依 workflow 執行 audit-only 通過：992 筆發現、950 筆選入、142 筆 resolved、808 筆 unresolved。
  額外試跑 v2 正式產製會因這 808 筆未確認地址而拒絕輸出；現行 workflow 僅稽核，不受影響，未放寬驗證。
- 位置 API 實際更新及 validate-only 通過：79 個位置。
- 臺北市法規沿革實際更新通過：4 個版本、state=unchanged。

本機 Python 為 3.14；CI 維持 Python 3.12。合併後仍須手動執行每日 workflow，
確認 GitHub runner 上全部驗證與自動提交／PR 步驟；不自動合併修正 PR。
