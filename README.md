# CUHK Timetable Exporter 香港中文大學課表導出

將香港中文大學課表導出為 ICS、CSV 或 JSON，支援兩種獲取方式。

---

## 兩種方式

| | 方式 A：Teaching Timetable（公開） | 方式 B：My Weekly Schedule（登入） |
|---|---|---|
| **數據來源** | 公開 Teaching Timetable 頁面 | CUSIS 個人課表（My Weekly Schedule） |
| **需要登入？** | ❌ 不需要，只需驗證碼 | ✅ 需要 SID + 密碼 + 2FA |
| **數據精度** | 整學期 RRULE 週重複 | 逐週遍歷，精確到每一天 |
| **課表變動** | 無法反映（取消課、調課等） | ✅ 自動捕捉每週差異 |
| **適用場景** | 快速導出、不想登入 | 需要和官網完全一致的課表 |

---

## 安裝

```bash
git clone https://github.com/TOHgoto/cuhk-timetable-exporter.git
cd cuhk-timetable-exporter
python3 -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 方式 A：Teaching Timetable（無需登入）

從公開的 Teaching Timetable 頁面獲取課表。不需要 CUSIS 帳號。

### A-1. 自動打開瀏覽器

1. 編輯 `my_courses.txt`，每行一個課程代碼（如 `ROSE5720`）
2. 執行：
   ```bash
   python -m cuhk_timetable_export --fetch-teaching --selected-file my_courses.txt -f ics -o my_timetable
   ```
3. 瀏覽器打開後：選擇學期，填寫驗證碼 → 點擊 Search → 等結果載入 → 回終端按 Enter

### A-2. 從已儲存的 HTML 導出

1. 打開 [Teaching Timetable](https://rgsntl.rgs.cuhk.edu.hk/rws_prd_applx2/Public/tt_dsp_timetable.aspx)，查詢後另存為 HTML
2. 列出課程（可選）：
   ```bash
   python -m cuhk_timetable_export --teaching-html "Teaching Timetable.html" --list-classes
   ```
3. 導出：
   ```bash
   python -m cuhk_timetable_export --teaching-html "Teaching Timetable.html" --selected ROSE5720,ROSE5760 -f ics -o my_timetable
   ```

> 學期起訖自動推斷，也可手動指定：`--term-start 2026-01-05 --term-end 2026-04-30`

---

## 方式 B：My Weekly Schedule（需登入 CUSIS）

登入 CUSIS 後，自動逐週遍歷整學期課表，生成精確到每一天的日曆事件。

```bash
python -m cuhk_timetable_export --fetch-schedule -f ics -o my_schedule
```

**操作流程：**
1. 腳本打開 Chrome 瀏覽器
2. 你在瀏覽器中完成：登入 CUSIS → 導航到 Manage Classes → My Weekly Schedule
3. 確認看到週課表後，回終端按 Enter
4. 腳本自動：擴展顯示時間 → 從第 1 週遍歷到學期末 → 導出

也可手動指定學期日期：
```bash
python -m cuhk_timetable_export --fetch-schedule --term-start 2026-01-05 --term-end 2026-05-04 -f ics -o my_schedule
```

### 從已儲存的 HTML 導出（單週快照）

如果只需要導出某一週的快照：
1. 在 CUSIS 的 My Weekly Schedule 頁面，用瀏覽器「另存為 → 網頁，全部」
2. 執行：
   ```bash
   python -m cuhk_timetable_export --schedule-html "My Weekly Schedule.html" -f ics -o my_schedule
   ```

---

## 命令選項

| 選項 | 說明 |
|------|------|
| **方式 A** | |
| `--fetch-teaching` | 打開瀏覽器，從 Teaching Timetable 抓取（需驗證碼） |
| `--teaching-html PATH` | 使用已儲存的 Teaching Timetable HTML |
| `--list-classes` | 列出 HTML 中的課程，不導出 |
| `--selected LIST` | 要導出的課程（逗號分隔，如 `ROSE5720,ROSE5760`） |
| `--selected-file PATH` | 課程列表檔案（每行一個） |
| **方式 B** | |
| `--fetch-schedule` | 登入 CUSIS，逐週遍歷 My Weekly Schedule |
| `--schedule-html PATH` | 使用已儲存的 My Weekly Schedule HTML（單週快照） |
| **通用** | |
| `--term-start` / `--term-end` | 學期起訖 (YYYY-MM-DD)，可選（自動推斷） |
| `-o`, `--output` | 輸出路徑，預設 `cuhk_timetable` |
| `-f`, `--format` | 格式：`ics` / `csv` / `json`，預設 `ics` |

---

## 隱私與安全

- **方式 A** 完全不需要 CUSIS 帳號，僅訪問公開頁面
- **方式 B** 需要登入，但所有操作在你自己的瀏覽器中完成，帳號密碼**不經過本程式**
- 不向任何第三方發送資料
- 完全開源，可查閱 `cuhk_timetable_export/` 原始碼

---

## 依賴

- Python 3.9+
- Chrome 瀏覽器（用於 `--fetch-teaching` 和 `--fetch-schedule`）
- 見 `requirements.txt`：icalendar, beautifulsoup4, selenium, webdriver-manager

---

## License

MIT
