"""
Parse CUHK "My Weekly Schedule" page HTML (saved from CUSIS browser)
into a list of class meeting dicts compatible with the exporter.

Usage pattern:
- 用户登录 CUSIS，打开 Manage Classes → "My Weekly Schedule" 页面
- 用浏览器 "另存为 → 网页，全部" 保存整个页面
- 本模块解析保存的 HTML（自动检测 iframe 引用并读取 iframe 内容）

The real HTML structure:
- WEEKLY_SCHED_HTMLAREA table: a grid with Time column + 7 day columns.
  Course blocks are <td> cells with rowspan + background-color style,
  containing <span> with lines like:
    "ROSE 5770 - -\nLecture\n18:30 - 21:15\nLi Koon Chun Hall LT1"
- STDNT_WK_NO_MTG table: courses without meeting info, with Start/End dates.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import date, timedelta

from bs4 import BeautifulSoup, Tag  # type: ignore[import]


# ──────────────────────────────────────────────────────────────────
#  Day / Time helpers
# ──────────────────────────────────────────────────────────────────

_DAY_MAP = {
    "mo": "Mon", "mon": "Mon", "monday": "Mon",
    "tu": "Tue", "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "we": "Wed", "wed": "Wed", "weds": "Wed", "wednesday": "Wed",
    "th": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thursday": "Thu",
    "fr": "Fri", "fri": "Fri", "friday": "Fri",
    "sa": "Sat", "sat": "Sat", "saturday": "Sat",
    "su": "Sun", "sun": "Sun", "sunday": "Sun",
}

_WEEKDAY_INDEX = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
}


def _normalize_day(text: str) -> str | None:
    t = text.strip().lower()
    if t in _DAY_MAP:
        return _DAY_MAP[t]
    for key, val in _DAY_MAP.items():
        if t.startswith(key):
            return val
    return None


def _first_date_for_weekday(start: date, weekday_name: str) -> date:
    target_idx = _WEEKDAY_INDEX.get(weekday_name)
    if target_idx is None:
        return start
    offset = (target_idx - start.weekday()) % 7
    return start + timedelta(days=offset)


def _parse_time_range(text: str) -> tuple[str, str] | None:
    """Parse time range like '18:30 - 21:15' or '10:30AM - 11:15AM'."""
    m = re.search(
        r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\s*[-–]\s*"
        r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?",
        text,
    )
    if not m:
        return None
    h1, m1, ap1, h2, m2, ap2 = m.groups()

    def to_24(h: str, mm: str, ap: str | None) -> str:
        hour = int(h)
        if ap:
            ap_u = ap.upper()
            if ap_u == "AM" and hour == 12:
                hour = 0
            elif ap_u == "PM" and hour != 12:
                hour += 12
        return f"{hour:02d}:{int(mm):02d}"

    return to_24(h1, m1, ap1), to_24(h2, m2, ap2)


def _split_class_code(code: str) -> tuple[str, str, str]:
    """Split e.g. 'CSCI3100' → ('CSCI', '3100', ''), 'ROSE5770' → ('ROSE', '5770', '')."""
    m = re.match(r"^([A-Z]{2,6})(\d{3,4})(.*)$", code.strip())
    if not m:
        return "", code.strip(), ""
    return m.group(1), m.group(2), m.group(3)


def _parse_day_pattern(text: str) -> List[str]:
    """Parse day patterns like 'MoWeFr', 'TuTh', 'Mon, Wed, Fri'."""
    if not text or not text.strip():
        return []
    text = text.strip()
    days: List[str] = []
    # Two-letter concatenated: MoWeFr, TuTh
    if re.match(r"^[A-Z][a-z]([A-Z][a-z])*$", text):
        for i in range(0, len(text), 2):
            d = _normalize_day(text[i:i + 2])
            if d:
                days.append(d)
        if days:
            return days
    # Comma or space separated
    for token in re.split(r"[,\s]+", text):
        d = _normalize_day(token)
        if d and d not in days:
            days.append(d)
    return days


# ──────────────────────────────────────────────────────────────────
#  iframe resolution
# ──────────────────────────────────────────────────────────────────

def _resolve_iframe_html(html_path: Path, soup: BeautifulSoup) -> Optional[str]:
    """
    If the HTML contains an iframe pointing to the schedule content,
    load the iframe source from the associated _files/ directory.
    """
    iframe = soup.find("iframe", id="main_target_win0")
    if not iframe:
        iframe = soup.find("iframe", src=re.compile(r"SSR_SSENRL_SCHD", re.I))
    if not iframe:
        return None

    src = iframe.get("src", "")
    if not src:
        return None

    # Resolve relative path from the HTML file's location
    iframe_path = html_path.parent / src
    if iframe_path.exists():
        return iframe_path.read_text(encoding="utf-8", errors="ignore")

    # Try common _files directory naming
    stem = html_path.stem
    files_dir = html_path.parent / f"{stem}_files"
    if files_dir.is_dir():
        fname = Path(src).name
        candidate = files_dir / fname
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="ignore")

    return None


# ──────────────────────────────────────────────────────────────────
#  Strategy 1: WEEKLY_SCHED_HTMLAREA table (primary)
# ──────────────────────────────────────────────────────────────────

def _parse_weekly_grid(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Parse the WEEKLY_SCHED_HTMLAREA table.

    Structure:
    - Header row: Time | Monday (Feb 23) | Tuesday (Feb 24) | ... | Sunday (Mar 1)
    - Data rows: <td> with time label (08:00, 09:00, etc.)
      and <td> with rowspan + background-color for course blocks.

    Course block <span> text (lines separated by <br>):
        ROSE 5770 - -
        Lecture
        18:30 - 21:15
        Li Koon Chun Hall LT1
    """
    table = soup.find("table", id="WEEKLY_SCHED_HTMLAREA")
    if not table:
        return []

    records: List[Dict[str, str]] = []

    # Parse header to get day names for each column index
    day_columns: Dict[int, str] = {}  # col_index -> day name
    header_row = table.find("tr")
    if header_row:
        headers = header_row.find_all("th")
        for i, th in enumerate(headers):
            text = th.get_text(separator=" ", strip=True)
            # Match "Monday Feb 23", "Tuesday Feb 24", etc.
            day = _normalize_day(text.split()[0]) if text.split() else None
            if day:
                day_columns[i] = day

    if not day_columns:
        return []

    # Walk all <td> cells with background-color style (course blocks)
    for td in table.find_all("td"):
        style = td.get("style", "")
        if "background-color" not in style:
            continue

        # Get span text content
        span = td.find("span")
        if not span:
            continue

        # Get text with <br> as newlines
        text = span.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 3:
            continue

        # Parse the structured format:
        # Line 0: Course code like "ROSE 5770 - -" or "CSCI 3100 - A"
        # Line 1: Type like "Lecture", "Tutorial", "Laboratory"
        # Line 2: Time like "18:30 - 21:15"
        # Line 3+: Location
        course_line = lines[0]
        class_type = lines[1] if len(lines) > 1 else ""
        time_line = ""
        location_lines = []

        for line in lines[1:]:
            if _parse_time_range(line):
                time_line = line
            elif line != class_type:
                location_lines.append(line)

        if not time_line:
            # Try line[2] directly
            if len(lines) > 2:
                time_line = lines[2]

        times = _parse_time_range(time_line)
        if not times:
            continue

        # Parse course code: "ROSE 5770 - -" → subject=ROSE, catalog=5770, section=-
        # Remove spaces in the code part
        code_match = re.match(
            r"^([A-Z]{2,6})\s*(\d{3,4})\s*[-–]?\s*(.*)$",
            course_line.strip(),
        )
        if code_match:
            subj = code_match.group(1)
            catalog = code_match.group(2)
            section = code_match.group(3).strip().rstrip("-").strip()
        else:
            # Fallback: remove spaces and split
            code_clean = course_line.replace(" ", "")
            subj, catalog, section = _split_class_code(code_clean)

        location = " ".join(location_lines) if location_lines else ""
        if not location and len(lines) > 3:
            location = lines[3]

        # Determine which day column this cell belongs to
        day_name = _determine_day_for_cell(td, table, day_columns)
        if not day_name:
            continue

        records.append({
            "SUBJECT": subj,
            "CATALOG_NBR": catalog,
            "CLASS_SECTION": section if section and section != "-" else "",
            "CLASS_CODE_RAW": f"{subj}{catalog}",
            "CLASS_NBR": "",
            "DESCR": class_type,
            "INSTRUCTORS": "",
            "FDESCR": location,
            "DAY": day_name,
            "TIME_RANGE": time_line,
            "TIME_START": times[0],
            "TIME_END": times[1],
        })

    return records


def _determine_day_for_cell(
    td: Tag, table: Tag, day_columns: Dict[int, str]
) -> str | None:
    """
    Determine which day-of-week column a <td> cell belongs to.
    
    In the WEEKLY_SCHED_HTMLAREA table, the first column is Time, then
    Mon-Sun. We need to account for rowspan cells that make some rows
    have fewer <td> elements.
    
    Strategy: find the parent <tr> and determine the column position
    of this cell by looking at cells in the row and tracking rowspans.
    """
    tr = td.find_parent("tr")
    if not tr:
        return None

    # Simple approach: count position of this td within its row,
    # accounting for the fact that rowspan cells from previous rows
    # take up positions.
    #
    # Build a position map for all rows in the table.
    rows = table.find_all("tr")
    if not rows:
        return None

    # Build a grid tracking which cells occupy which positions
    # This handles rowspan correctly.
    grid: Dict[int, Dict[int, Tag]] = {}  # row_idx -> col_idx -> td
    rowspan_remaining: Dict[int, int] = {}  # col_idx -> remaining rowspan

    for row_idx, row in enumerate(rows):
        if row_idx == 0:
            continue  # Skip header row (th)
        grid[row_idx] = {}
        # Find next available column for each cell in this row
        cells = row.find_all("td")
        col = 0
        cell_idx = 0

        while cell_idx < len(cells):
            # Skip columns occupied by rowspan from previous rows
            while col in rowspan_remaining and rowspan_remaining[col] > 0:
                rowspan_remaining[col] -= 1
                if rowspan_remaining[col] <= 0:
                    del rowspan_remaining[col]
                col += 1

            cell = cells[cell_idx]
            rowspan = int(cell.get("rowspan", 1))
            grid[row_idx][col] = cell

            # Track rowspan for future rows
            if rowspan > 1:
                rowspan_remaining[col] = rowspan - 1

            # Check if this is our target cell
            if cell is td:
                return day_columns.get(col)

            col += 1
            cell_idx += 1

    return None


# ──────────────────────────────────────────────────────────────────
#  Strategy 2: STDNT_WK_NO_MTG table (no-meeting courses for dates)
# ──────────────────────────────────────────────────────────────────

def _parse_no_meeting_table(soup: BeautifulSoup) -> tuple[date | None, date | None]:
    """
    Parse the STDNT_WK_NO_MTG table to extract term start/end dates.
    
    Structure:
    | Class                          | Course Title  | Instructor | Start Date  | End Date    |
    | ROSE 5910 - OL01 (Laboratory)  | M.Sc.Projects |            | 2026/01/05  | 2026/05/04  |
    """
    start_dates: List[date] = []
    end_dates: List[date] = []

    # Look for date fields by id pattern
    for el in soup.find_all(id=re.compile(r"STDNT_WK_NO_MTG_START_DT\$\d+", re.I)):
        text = el.get_text(strip=True)
        d = _parse_cusis_date(text)
        if d:
            start_dates.append(d)

    for el in soup.find_all(id=re.compile(r"STDNT_WK_NO_MTG_END_DT\$\d+", re.I)):
        text = el.get_text(strip=True)
        d = _parse_cusis_date(text)
        if d:
            end_dates.append(d)

    start = min(start_dates) if start_dates else None
    end = max(end_dates) if end_dates else None
    return start, end


def _parse_cusis_date(text: str) -> date | None:
    """Parse CUSIS date format: YYYY/MM/DD (e.g. '2026/01/05')."""
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", text.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_week_label(soup: BeautifulSoup) -> tuple[date | None, date | None]:
    """
    Parse the "Week of 2026/2/23 - 2026/3/1" label from the page.
    """
    # Look for the PSGROUPBOXLABEL with "Week of"
    for el in soup.find_all(class_="PSGROUPBOXLABEL"):
        text = el.get_text(strip=True)
        m = re.search(
            r"Week of\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*[-–]\s*(\d{4})/(\d{1,2})/(\d{1,2})",
            text,
        )
        if m:
            try:
                start = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                end = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
                return start, end
            except ValueError:
                pass
    return None, None


def parse_week_dates_from_headers(
    soup: BeautifulSoup, year_hint: int | None = None
) -> Dict[int, date]:
    """
    Parse column header dates from the WEEKLY_SCHED_HTMLAREA table.

    Headers look like: "Monday\\nFeb 23", "Tuesday\\nFeb 24", etc.
    Returns: {col_index: date, ...}
    """
    table = soup.find("table", id="WEEKLY_SCHED_HTMLAREA")
    if not table:
        return {}

    # Try to get year from the week label first
    week_start, _ = _parse_week_label(soup)
    if year_hint is None and week_start:
        year_hint = week_start.year
    if year_hint is None:
        year_hint = date.today().year

    _MONTH_MAP = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    col_dates: Dict[int, date] = {}
    header_row = table.find("tr")
    if not header_row:
        return {}

    for i, th in enumerate(header_row.find_all("th")):
        text = th.get_text(separator=" ", strip=True)
        # Match "Monday Feb 23" or "Tuesday Mar 1"
        m = re.search(r"([A-Za-z]+)\s+(\d{1,2})$", text.strip())
        if m:
            month_str = m.group(1).lower()[:3]
            day_num = int(m.group(2))
            month_num = _MONTH_MAP.get(month_str)
            if month_num:
                try:
                    col_dates[i] = date(year_hint, month_num, day_num)
                except ValueError:
                    pass

    return col_dates


def parse_weekly_grid_dated(
    html_content: str, year_hint: int | None = None
) -> List[Dict]:
    """
    Parse WEEKLY_SCHED_HTMLAREA and return records with concrete SINGLE_DATE
    (instead of DAY name). Used by the dynamic scraper.

    Each returned dict has:
    - SUBJECT, CATALOG_NBR, CLASS_SECTION, CLASS_CODE_RAW, DESCR, FDESCR
    - SINGLE_DATE: "YYYY-MM-DD" (the specific date this class occurs)
    - MEETING_TIME_START, MEETING_TIME_END
    """
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", id="WEEKLY_SCHED_HTMLAREA")
    if not table:
        return []

    # Get column dates
    col_dates = parse_week_dates_from_headers(soup, year_hint)
    if not col_dates:
        return []

    # Also build day_columns for _determine_day_for_cell compatibility
    day_columns: Dict[int, str] = {}
    header_row = table.find("tr")
    if header_row:
        for i, th in enumerate(header_row.find_all("th")):
            text = th.get_text(separator=" ", strip=True)
            day = _normalize_day(text.split()[0]) if text.split() else None
            if day:
                day_columns[i] = day

    records: List[Dict] = []

    for td in table.find_all("td"):
        style = td.get("style", "")
        if "background-color" not in style:
            continue

        span = td.find("span")
        if not span:
            continue

        text = span.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 3:
            continue

        course_line = lines[0]
        class_type = lines[1] if len(lines) > 1 else ""
        time_line = ""
        location_lines = []

        for line in lines[1:]:
            if _parse_time_range(line):
                time_line = line
            elif line != class_type:
                location_lines.append(line)

        if not time_line and len(lines) > 2:
            time_line = lines[2]

        times = _parse_time_range(time_line)
        if not times:
            continue

        code_match = re.match(
            r"^([A-Z]{2,6})\s*(\d{3,4})\s*[-–]?\s*(.*)$",
            course_line.strip(),
        )
        if code_match:
            subj = code_match.group(1)
            catalog = code_match.group(2)
            section = code_match.group(3).strip().rstrip("-").strip()
        else:
            code_clean = course_line.replace(" ", "")
            subj, catalog, section = _split_class_code(code_clean)

        location = " ".join(location_lines) if location_lines else ""
        if not location and len(lines) > 3:
            location = lines[3]

        # Determine column index for this cell to get the specific date
        col_idx = _determine_col_index_for_cell(td, table)
        if col_idx is None or col_idx not in col_dates:
            continue

        specific_date = col_dates[col_idx]

        records.append({
            "SUBJECT": subj,
            "CATALOG_NBR": catalog,
            "CLASS_SECTION": section if section and section != "-" else "",
            "CLASS_CODE_RAW": f"{subj}{catalog}",
            "CLASS_NBR": "",
            "DESCR": class_type,
            "INSTRUCTORS": "",
            "FDESCR": location,
            "SINGLE_DATE": specific_date.isoformat(),
            "MEETING_TIME_START": times[0],
            "MEETING_TIME_END": times[1],
        })

    return records


def _determine_col_index_for_cell(td: Tag, table: Tag) -> int | None:
    """Determine the column index of a <td> cell, handling rowspans."""
    tr = td.find_parent("tr")
    if not tr:
        return None

    rows = table.find_all("tr")
    if not rows:
        return None

    rowspan_remaining: Dict[int, int] = {}

    for row_idx, row in enumerate(rows):
        if row_idx == 0:
            continue
        cells = row.find_all("td")
        col = 0
        cell_idx = 0

        while cell_idx < len(cells):
            while col in rowspan_remaining and rowspan_remaining[col] > 0:
                rowspan_remaining[col] -= 1
                if rowspan_remaining[col] <= 0:
                    del rowspan_remaining[col]
                col += 1

            cell = cells[cell_idx]
            rowspan = int(cell.get("rowspan", 1))

            if rowspan > 1:
                rowspan_remaining[col] = rowspan - 1

            if cell is td:
                return col

            col += 1
            cell_idx += 1

    return None


# ──────────────────────────────────────────────────────────────────
#  Strategy 3: Scroll area fields (fallback for different layouts)
# ──────────────────────────────────────────────────────────────────

def _parse_scroll_area(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Parse PeopleSoft scroll area patterns with indexed field IDs."""
    records: List[Dict[str, str]] = []

    course_name_els = soup.find_all(
        id=re.compile(r"CLASSNAME|CLS_LINK|CLASS_NAME", re.I)
    )

    for el in course_name_els:
        idx_match = re.search(r"\$(\d+)$", el.get("id", ""))
        if not idx_match:
            continue
        idx = idx_match.group(1)

        course_text = el.get_text(strip=True)
        if not course_text:
            continue

        def _find_field(pattern: str) -> str:
            full_re = r"(?:" + pattern + r").*\$" + re.escape(idx) + r"$"
            found = soup.find(id=re.compile(full_re, re.I))
            return found.get_text(strip=True) if found else ""

        time_str = _find_field(r"CLASS_TIME|MTG_TIME|MEETING_TIME")
        day_str = _find_field(r"MTG_PAT|CLASS_DAY|DAY_OF_WEEK|MEETING_DAY")
        room_str = _find_field(r"ROOM|FACILITY|LOCATION|BLDG")
        instructor_str = _find_field(r"INSTR|INSTRUCTOR|TEACHER")

        parts = re.split(r"\s*[-–]\s*", course_text, maxsplit=1)
        course_code_part = parts[0].strip()
        course_title = parts[1].strip() if len(parts) > 1 else ""

        subj, catalog, section = _split_class_code(
            course_code_part.replace(" ", "")
        )

        days = _parse_day_pattern(day_str)
        times = _parse_time_range(time_str) if time_str else None

        if days and times:
            for day_name in days:
                records.append({
                    "SUBJECT": subj,
                    "CATALOG_NBR": catalog,
                    "CLASS_SECTION": section,
                    "CLASS_CODE_RAW": course_code_part.replace(" ", ""),
                    "CLASS_NBR": "",
                    "DESCR": course_title,
                    "INSTRUCTORS": instructor_str,
                    "FDESCR": room_str,
                    "DAY": day_name,
                    "TIME_RANGE": time_str,
                    "TIME_START": times[0],
                    "TIME_END": times[1],
                })

    return records


# ──────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────

def parse_schedule_html(
    html_path: str | Path | None = None,
    html_content: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict]:
    """
    Parse a saved "My Weekly Schedule" HTML page from CUSIS.

    :param html_path: Path to the saved HTML file.
    :param html_content: Raw HTML string (alternative to html_path).
    :param start_date: First teaching day (YYYY-MM-DD). Auto-inferred if omitted.
    :param end_date: Last teaching day (YYYY-MM-DD). Auto-inferred if omitted.
    :returns: List of course dicts compatible with export.py.
    """
    if html_content is not None:
        html = html_content
        resolved_path = None
    elif html_path is not None:
        resolved_path = Path(html_path)
        html = resolved_path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError("Provide either html_path or html_content.")

    soup = BeautifulSoup(html, "html.parser")

    # Check if this is the outer page with an iframe reference
    if resolved_path:
        iframe_html = _resolve_iframe_html(resolved_path, soup)
        if iframe_html:
            soup = BeautifulSoup(iframe_html, "html.parser")

    # Try strategies in order of reliability
    raw_records: List[Dict[str, str]] = []

    # Strategy 1: WEEKLY_SCHED_HTMLAREA table (the real schedule grid)
    raw_records = _parse_weekly_grid(soup)

    # Strategy 2: Scroll area fields (alternative layout)
    if not raw_records:
        raw_records = _parse_scroll_area(soup)

    if not raw_records:
        raise ValueError(
            "Could not extract any course data from the HTML.\n"
            "Possible causes:\n"
            "  1. The iframe content was not saved (use 'Save As → Complete Webpage')\n"
            "  2. The schedule is empty for the displayed week\n"
            "Please check that the saved file includes the actual schedule content."
        )

    # Infer term dates if not provided
    if start_date is None or end_date is None:
        # Try the STDNT_WK_NO_MTG table first (most reliable for term dates)
        inferred_start, inferred_end = _parse_no_meeting_table(soup)
        if start_date is None and inferred_start:
            start_date = inferred_start.isoformat()
        if end_date is None and inferred_end:
            end_date = inferred_end.isoformat()

    # Fallback: use week label
    if start_date is None or end_date is None:
        week_start, week_end = _parse_week_label(soup)
        # We need term dates, not just week dates; use semester heuristic
        if not start_date and not end_date:
            today = date.today()
            if today.month >= 8:
                start_date = start_date or f"{today.year}-09-02"
                end_date = end_date or f"{today.year}-12-05"
            else:
                start_date = start_date or f"{today.year}-01-13"
                end_date = end_date or f"{today.year}-05-10"

    if not start_date or not end_date:
        raise ValueError(
            "Could not determine term start/end dates. "
            "Please provide --term-start and --term-end (YYYY-MM-DD)."
        )

    term_start = date.fromisoformat(start_date)

    # Convert raw records to exporter-compatible format
    final_records: List[Dict] = []
    seen: set[tuple] = set()

    for raw in raw_records:
        day_name = raw.get("DAY", "")
        time_start = raw.get("TIME_START", "")
        time_end = raw.get("TIME_END", "")

        if not day_name or not time_start or not time_end:
            # Try re-parsing from TIME_RANGE
            time_range = raw.get("TIME_RANGE", "")
            times = _parse_time_range(time_range) if time_range else None
            if times:
                time_start, time_end = times
            else:
                continue
            days = _parse_day_pattern(day_name) if day_name else []
            if not days:
                continue
            day_name = days[0]

        slot_key = (raw.get("CLASS_CODE_RAW", ""), day_name, time_start, time_end)
        if slot_key in seen:
            continue
        seen.add(slot_key)

        first_class_date = _first_date_for_weekday(term_start, day_name)
        record = {
            "SUBJECT": raw.get("SUBJECT", ""),
            "CATALOG_NBR": raw.get("CATALOG_NBR", ""),
            "CLASS_SECTION": raw.get("CLASS_SECTION", ""),
            "CLASS_CODE_RAW": raw.get("CLASS_CODE_RAW", ""),
            "CLASS_NBR": raw.get("CLASS_NBR", ""),
            "DESCR": raw.get("DESCR", ""),
            "INSTRUCTORS": raw.get("INSTRUCTORS", ""),
            "FDESCR": raw.get("FDESCR", ""),
            "COMDESC": raw.get("SUBJECT", ""),
            "START_DT": first_class_date.isoformat(),
            "END_DT": end_date,
            "MEETING_TIME_START": time_start,
            "MEETING_TIME_END": time_end,
        }
        final_records.append(record)

    if not final_records:
        raise ValueError(
            "Found course elements in HTML but could not extract "
            "valid day/time information."
        )

    return final_records
