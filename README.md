# CUHK Timetable Exporter 香港中文大學課表導出

將香港中文大學 **Teaching Timetable** 課表導出為 ICS、CSV 或 JSON。  
**完全本地運行**，無需 CUSIS 登入，不向第三方發送任何資料。

---

## 功能

- **兩種使用方式**：自動打開瀏覽器輸入驗證碼，或從已儲存的 HTML 導出
- **篩選課程**：只導出你選的課，或導出整張課表
- **多格式**：ICS（Apple / Google 日曆）、CSV、JSON

---

## 安裝

```bash
cd cuhk-timetable-exporter
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 使用

### 方式一：自動打開瀏覽器（推薦）

1. 建立 `my_courses.txt`，每行一個課程代碼（如 `ROSE5720`）
2. 執行：
   ```bash
   python -m cuhk_timetable_export --fetch-teaching --selected-file my_courses.txt -f ics -o my_timetable
   ```
3. 瀏覽器打開後：輸入驗證碼 → 點擊 Search → 等待結果載入 → 回到終端按 Enter

學期起訖從結果頁「Meeting Date」自動推斷。

### 方式二：從已儲存的 HTML 導出

1. 打開 [Teaching Timetable](https://rgsntl.rgs.cuhk.edu.hk/rws_prd_applx2/Public/tt_dsp_timetable.aspx)，查詢後**另存為網頁 (HTML)**
2. 列出課程（可選）：
   ```bash
   python -m cuhk_timetable_export --teaching-html "Teaching Timetable.html" --list-classes
   ```
3. 導出（可只導出指定課程）：
   ```bash
   python -m cuhk_timetable_export --teaching-html "Teaching Timetable.html" --selected ROSE5720,ROSE5760 -f ics -o my_timetable
   ```
   或使用課程列表檔案：`--selected-file my_courses.txt`

若自動推斷學期日期失敗，可手動指定：`--term-start 2026-01-05 --term-end 2026-04-30`

---

## 命令選項

| 選項 | 說明 |
|------|------|
| `--fetch-teaching` | 打開瀏覽器抓取課表，需配合 `--selected-file` |
| `--teaching-html PATH` | 使用已儲存的 HTML 檔案 |
| `--term-start` / `--term-end` | 學期起訖 (YYYY-MM-DD)，可選 |
| `--list-classes` | 只列出 HTML 中的課程，不導出 |
| `--selected LIST` | 要導出的課程（逗號分隔） |
| `--selected-file PATH` | 課程列表檔案（每行一個） |
| `-o`, `--output` | 輸出路徑，預設 `cuhk_timetable` |
| `-f`, `--format` | 格式：`ics` / `csv` / `json`，預設 `ics` |

---

## 隱私與安全

- 僅處理 Teaching Timetable 頁面或其 HTML 檔案，**不需要 SID 或 CUSIS 密碼**
- 不向任何第三方發送帳號、密碼等敏感資訊
- 無日誌、無統計，可查閱 `cuhk_timetable_export/` 原始碼

---

## 依賴

- Python 3.9+
- Chrome 瀏覽器（用於 `--fetch-teaching`）
- 見 `requirements.txt`：icalendar, beautifulsoup4, selenium, webdriver-manager

---

## License

MIT
