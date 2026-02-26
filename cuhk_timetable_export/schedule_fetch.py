"""
Fetch "My Weekly Schedule" from CUSIS via Selenium browser automation.

Workflow:
1. Open Chrome → user manually logs in and navigates to "My Weekly Schedule"
2. User presses Enter when on the schedule page
3. Script detects the schedule grid, infers term dates
4. Iterate week-by-week, parsing each week's schedule grid
5. Return per-date course events (no RRULE)
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

from .schedule_html import (
    parse_weekly_grid_dated,
    _parse_week_label,
    _parse_no_meeting_table,
)
from bs4 import BeautifulSoup


# ──────────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────────

# We open the CUSIS base page; user does the rest manually.
CUSIS_BASE_URL = "https://cusis.cuhk.edu.hk/"

# PeopleSoft element IDs (inside the schedule iframe)
DATE_INPUT_ID = "DERIVED_CLASS_S_START_DT"
REFRESH_BTN_ID = "DERIVED_CLASS_S_SSR_REFRESH_CAL$8$"
NEXT_WEEK_BTN_ID = "DERIVED_CLASS_S_SSR_NEXT_WEEK"
SCHEDULE_TABLE_ID = "WEEKLY_SCHED_HTMLAREA"
IFRAME_ID = "main_target_win0"

# Time range controls
TIME_START_ID = "DERIVED_CLASS_S_MEETING_TIME_START"
TIME_END_ID = "DERIVED_CLASS_S_MEETING_TIME_END"


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────

def _create_driver() -> webdriver.Chrome:
    """Create a Chrome WebDriver instance."""
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1200,900")
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(
            f"Could not start Chrome. Install Chrome and run again.\nError: {e}"
        ) from e


def _try_find_schedule_table(driver: webdriver.Chrome) -> bool:
    """
    Try to find the WEEKLY_SCHED_HTMLAREA table.
    Checks both the main page and inside the iframe.
    Returns True if found.
    """
    # First try: check current context
    try:
        driver.find_element(By.ID, SCHEDULE_TABLE_ID)
        return True
    except NoSuchElementException:
        pass

    # Second try: switch to iframe and check
    try:
        driver.switch_to.default_content()
        iframe = driver.find_element(By.ID, IFRAME_ID)
        driver.switch_to.frame(iframe)
        driver.find_element(By.ID, SCHEDULE_TABLE_ID)
        return True
    except (NoSuchElementException, Exception):
        pass

    # Third try: try any iframe
    try:
        driver.switch_to.default_content()
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                driver.find_element(By.ID, SCHEDULE_TABLE_ID)
                return True
            except (NoSuchElementException, Exception):
                driver.switch_to.default_content()
    except Exception:
        pass

    return False


def _wait_for_schedule_table(driver: webdriver.Chrome, timeout: int = 30) -> bool:
    """Wait for the WEEKLY_SCHED_HTMLAREA table to appear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, SCHEDULE_TABLE_ID))
        )
        return True
    except TimeoutException:
        return False


def _get_current_page_html(driver: webdriver.Chrome) -> str:
    """Get the current page HTML."""
    return driver.page_source


def _set_date_and_refresh(driver: webdriver.Chrome, target_date: date) -> None:
    """Set the date picker to target_date and click Refresh Calendar."""
    date_str = target_date.strftime("%Y/%m/%d")
    date_input = driver.find_element(By.ID, DATE_INPUT_ID)
    date_input.clear()
    date_input.send_keys(date_str)

    refresh_btn = driver.find_element(By.ID, REFRESH_BTN_ID)
    refresh_btn.click()

    time.sleep(1.5)
    _wait_for_schedule_table(driver, timeout=20)
    time.sleep(0.5)


def _click_next_week(driver: webdriver.Chrome) -> None:
    """Click the Next Week button and wait for reload."""
    btn = driver.find_element(By.ID, NEXT_WEEK_BTN_ID)
    btn.click()
    time.sleep(1.5)
    _wait_for_schedule_table(driver, timeout=20)
    time.sleep(0.5)


def _expand_time_range(driver: webdriver.Chrome) -> None:
    """
    Set the display time range to 06:00-23:00 to ensure all classes
    (including evening courses) are visible in the grid.
    CUSIS defaults to 08:00-18:00 which hides evening courses.
    """
    try:
        start_input = driver.find_element(By.ID, TIME_START_ID)
        end_input = driver.find_element(By.ID, TIME_END_ID)

        current_start = start_input.get_attribute("value") or "08:00"
        current_end = end_input.get_attribute("value") or "18:00"

        needs_update = False
        if current_start != "06:00":
            start_input.clear()
            start_input.send_keys("06:00")
            needs_update = True
        if current_end != "23:00":
            end_input.clear()
            end_input.send_keys("23:00")
            needs_update = True

        if needs_update:
            # Click Refresh Calendar to apply the new time range
            refresh_btn = driver.find_element(By.ID, REFRESH_BTN_ID)
            refresh_btn.click()
            time.sleep(2)
            _wait_for_schedule_table(driver, timeout=20)
            time.sleep(0.5)
            print(f"  时间范围: {current_start}-{current_end} → 06:00-23:00")
        else:
            print("  时间范围已覆盖全天")
    except NoSuchElementException:
        print("  ⚠️ 未找到时间范围控件，使用当前设置")


def _get_week_range_from_html(html: str) -> tuple[date | None, date | None]:
    """Extract the current week's date range from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    return _parse_week_label(soup)


def _get_term_dates_from_html(html: str) -> tuple[date | None, date | None]:
    """Extract term start/end dates from the STDNT_WK_NO_MTG table."""
    soup = BeautifulSoup(html, "html.parser")
    return _parse_no_meeting_table(soup)


# ──────────────────────────────────────────────────────────────────
#  Main fetch function
# ──────────────────────────────────────────────────────────────────

def fetch_schedule(
    term_start: str | None = None,
    term_end: str | None = None,
) -> List[Dict]:
    """
    Open Chrome, let user manually log in and navigate to
    "My Weekly Schedule", then iterate week-by-week.

    :param term_start: Override term start date (YYYY-MM-DD).
    :param term_end: Override term end date (YYYY-MM-DD).
    :returns: List of per-date course events (with SINGLE_DATE field).
    """
    driver = _create_driver()

    try:
        # ── Step 1: User does login + navigation ──────────────────
        print("\n" + "=" * 60)
        print("  CUSIS My Weekly Schedule 自动抓取")
        print("=" * 60)
        print()
        print("正在打开 Chrome 浏览器…")
        driver.get(CUSIS_BASE_URL)

        print()
        print("请在浏览器中完成以下操作：")
        print("  1. 登录 CUSIS（输入 SID、密码、双因素认证）")
        print("  2. 导航到 Manage Classes → My Weekly Schedule")
        print("  3. 确认页面上已显示本周的课表（周日历视图）")
        print()
        print("⚠️  注意：请不要关闭这个 Chrome 窗口！")
        print()
        input("当你看到 My Weekly Schedule 页面后，按回车键继续 → ")

        # ── Step 2: Detect schedule table ─────────────────────────
        print("\n正在检测课表…")

        if not _try_find_schedule_table(driver):
            print("\n⚠️  未检测到课表。再试一次…")
            print("请确认你在 My Weekly Schedule 页面上，然后按回车。")
            input("按回车键重试 → ")
            if not _try_find_schedule_table(driver):
                raise RuntimeError(
                    "无法检测到 WEEKLY_SCHED_HTMLAREA 课表。\n"
                    "请确保页面上显示的是 My Weekly Schedule 的周日历视图。"
                )

        print("✅ 检测到课表！")

        # ── Step 2.5: Expand time range ───────────────────────────
        print("正在调整显示时间范围…")
        _expand_time_range(driver)

        html = _get_current_page_html(driver)

        # ── Step 3: Determine term date range ─────────────────────
        if term_start and term_end:
            start_dt = date.fromisoformat(term_start)
            end_dt = date.fromisoformat(term_end)
        else:
            inferred_start, inferred_end = _get_term_dates_from_html(html)
            start_dt = date.fromisoformat(term_start) if term_start else inferred_start
            end_dt = date.fromisoformat(term_end) if term_end else inferred_end

            if not start_dt or not end_dt:
                print("\n无法自动检测学期日期范围。")
                if not start_dt:
                    s = input("请输入学期开始日期 (YYYY-MM-DD): ").strip()
                    start_dt = date.fromisoformat(s)
                if not end_dt:
                    e = input("请输入学期结束日期 (YYYY-MM-DD): ").strip()
                    end_dt = date.fromisoformat(e)

        print(f"\n学期范围: {start_dt} → {end_dt}")

        # ── Step 4: Navigate to the first week ────────────────────
        first_monday = start_dt - timedelta(days=start_dt.weekday())
        print(f"从第一周开始: {first_monday}")

        _set_date_and_refresh(driver, first_monday)
        time.sleep(1)

        # ── Step 5: Iterate week by week ──────────────────────────
        all_events: List[Dict] = []
        seen: set[tuple] = set()
        week_count = 0
        max_weeks = 25  # Safety limit

        current_monday = first_monday

        while current_monday <= end_dt and week_count < max_weeks:
            week_count += 1
            html = _get_current_page_html(driver)

            # Verify current week from label
            week_start, week_end = _get_week_range_from_html(html)
            if week_start:
                current_monday = week_start - timedelta(days=week_start.weekday())
                week_label = f"{week_start} → {week_end}"
            else:
                week_label = f"Week {week_count}"

            # Parse this week's grid with concrete dates
            week_events = parse_weekly_grid_dated(
                html, year_hint=current_monday.year
            )

            new_count = 0
            for evt in week_events:
                evt_key = (
                    evt.get("CLASS_CODE_RAW", ""),
                    evt.get("SINGLE_DATE", ""),
                    evt.get("MEETING_TIME_START", ""),
                    evt.get("MEETING_TIME_END", ""),
                )
                if evt_key not in seen:
                    seen.add(evt_key)
                    evt["COMDESC"] = evt.get("SUBJECT", "")
                    evt["START_DT"] = evt.get("SINGLE_DATE", "")
                    all_events.append(evt)
                    new_count += 1

            sys.stdout.write(
                f"\r  [{week_count:>2}] {week_label} — "
                f"{len(week_events)} 节课, {new_count} 新增"
            )
            sys.stdout.flush()

            # Advance to next week
            current_monday += timedelta(days=7)
            if current_monday > end_dt:
                break

            try:
                _click_next_week(driver)
            except (NoSuchElementException, Exception) as e:
                # Fallback: set date directly
                try:
                    _set_date_and_refresh(driver, current_monday)
                except Exception:
                    print(f"\n\n⚠️  无法翻页到 {current_monday}: {e}")
                    break

        print(f"\n\n✅ 完成！共遍历 {week_count} 周，收集 {len(all_events)} 个课程事件")
        return all_events

    finally:
        driver.quit()
