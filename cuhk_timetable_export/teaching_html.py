"""
Parse CUHK Teaching Timetable HTML (saved from browser) into a list of
class meeting dicts compatible with the exporter.

Usage pattern:
- User opens Teaching Timetable in browser,查询某个 subject 的课表。
- 浏览器里用 “另存为网页（HTML）” 保存结果页面。
- 本模块读取该 HTML，解析出每一节课的星期、时间、教室等。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict
from datetime import date, timedelta

from bs4 import BeautifulSoup  # type: ignore[import]


def _guess_timetable_table(soup: BeautifulSoup):
    """
    Pick the main timetable table: prefer table with id gv_detail (CUHK page),
    else heuristically by headers (Period, Class Code, Room, etc.).
    """
    # CUHK Teaching Timetable result table
    by_id = soup.find("table", id="gv_detail")
    if by_id:
        return by_id

    wanted = {
        "subject", "course", "catalog", "section", "class",
        "day", "time", "period", "room", "venue",
        "instructor", "teacher", "teaching",
    }
    candidates = []
    for table in soup.find_all("table"):
        headers = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if cells:
                headers = [c.get_text(strip=True) for c in cells]
                break
        if not headers:
            continue
        header_keys = {h.lower() for h in headers}
        if "period" not in header_keys and "time" not in header_keys:
            continue
        score = len(wanted.intersection(header_keys))
        if score:
            candidates.append((score, table))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _parse_time_range(text: str) -> tuple[str, str] | None:
    """
    Parse time range like '10:30 - 11:15' or
    '06:30PM - 09:15PM' into 24-hour ('HH:MM', 'HH:MM').
    """
    m = re.search(
        r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\s*-\s*"
        r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?",
        text,
    )
    if not m:
        return None
    h1, m1, ap1, h2, m2, ap2 = m.groups()

    def to_24(h: str, mm: str, ap: str | None) -> str:
        hour = int(h)
        minute = int(mm)
        if ap:
            ap_u = ap.upper()
            if ap_u == "AM":
                if hour == 12:
                    hour = 0
            elif ap_u == "PM":
                if hour != 12:
                    hour += 12
        return f"{hour:02d}:{minute:02d}"

    start = to_24(h1, m1, ap1)
    end = to_24(h2, m2, ap2)
    return start, end


def _normalize_day(text: str) -> str | None:
    """
    Normalize day of week text (e.g. 'Mon', 'MON', 'Monday') to 3-letter English.
    """
    t = text.strip().lower()
    mapping = {
        "mo": "Mon",
        "mon": "Mon",
        "monday": "Mon",
        "tu": "Tue",
        "tue": "Tue",
        "tues": "Tue",
        "tuesday": "Tue",
        "we": "Wed",
        "wed": "Wed",
        "weds": "Wed",
        "wednesday": "Wed",
        "th": "Thu",
        "thu": "Thu",
        "thur": "Thu",
        "thurs": "Thu",
        "thursday": "Thu",
        "fr": "Fri",
        "fri": "Fri",
        "friday": "Fri",
        "sa": "Sat",
        "sat": "Sat",
        "saturday": "Sat",
        "su": "Sun",
        "sun": "Sun",
        "sunday": "Sun",
    }
    for key, val in mapping.items():
        if t.startswith(key):
            return val
    return None


_WEEKDAY_INDEX = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


def _first_date_for_weekday(start: date, weekday_name: str) -> date:
    """
    Given a start date and a weekday name like 'Tue',
    return the first date on/after start with that weekday.
    """
    target_idx = _WEEKDAY_INDEX.get(weekday_name)
    if target_idx is None:
        return start
    offset = (target_idx - start.weekday()) % 7
    return start + timedelta(days=offset)


def _split_class_code(code: str) -> tuple[str, str, str]:
    """
    Split class code like 'ROSE5720-' or 'ROSE5910A' into
    (SUBJECT, CATALOG_NBR, CLASS_SECTION).
    """
    m = re.match(r"^([A-Z]{4})(\d{4})(.*)$", code.strip())
    if not m:
        return "", code.strip(), ""
    subj, catalog, section = m.groups()
    return subj, catalog, section


def _parse_meeting_date_token(token: str, year_hint: int | None) -> date | None:
    """
    Parse a single date token from Meeting Date column.
    Supports: dd/mm/yyyy, d/m/yyyy, d/m (with year_hint).
    HK format is day/month/year.
    """
    token = token.strip()
    if not token:
        return None
    # dd/mm/yyyy or d/m/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", token)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    # d/m - need year
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", token)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = year_hint or date.today().year
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def _parse_meeting_dates_cell(cell_text: str, year_hint: int | None) -> List[date]:
    """
    Parse a Meeting Date cell: "6/1, 13/1, 20/1" or "05/01/2026 - 09/02/2026".
    Returns list of date objects.
    """
    cell_text = (cell_text or "").strip()
    if not cell_text:
        return []
    dates: List[date] = []
    # Full range format: dd/mm/yyyy - dd/mm/yyyy
    if " - " in cell_text:
        parts = cell_text.split(" - ", 1)
        for p in parts:
            d = _parse_meeting_date_token(p.strip(), year_hint)
            if d:
                dates.append(d)
        return dates
    # Comma-separated: 6/1, 13/1, 20/1
    for token in cell_text.split(","):
        d = _parse_meeting_date_token(token, year_hint)
        if d:
            dates.append(d)
    return dates


def _infer_term_dates_from_table(
    table,
    header_keys: List[str],
) -> tuple[date | None, date | None]:
    """
    Scan all rows for 'Meeting Date' column and return (min_date, max_date).
    Used to auto-detect term start/end when user does not provide them.
    """
    meeting_idx = next(
        (i for i, k in enumerate(header_keys) if "meeting" in k and "date" in k),
        None,
    )
    if meeting_idx is None:
        return None, None

    # First pass: find year from any dd/mm/yyyy in the column (for d/m tokens)
    year_hint: int | None = None
    cell_texts: List[str] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells or len(cells) <= meeting_idx:
            continue
        cell_texts.append(cells[meeting_idx].get_text(strip=True))
    for text in cell_texts:
        if " - " in text:
            for part in text.split(" - ", 1):
                m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", part.strip())
                if m:
                    year_hint = int(m.group(3))
                    break
        if year_hint is not None:
            break
    if year_hint is None:
        year_hint = date.today().year

    # Second pass: parse all cells with year_hint
    all_dates: List[date] = []
    for text in cell_texts:
        for d in _parse_meeting_dates_cell(text, year_hint):
            all_dates.append(d)

    if not all_dates:
        return None, None
    return min(all_dates), max(all_dates)


def _record_matches_selected(record: Dict[str, str], selected: List[str]) -> bool:
    """
    Return True if this record matches any of the selected class identifiers.
    Identifiers can be Class Code (e.g. ROSE5720, ROSE5720-) or Class Nbr (e.g. 9578).
    """
    code_raw = (record.get("CLASS_CODE_RAW") or "").strip()
    nbr = (record.get("CLASS_NBR") or "").strip()
    for s in selected:
        t = s.strip()
        if not t:
            continue
        if nbr and nbr == t:
            return True
        if code_raw and (t == code_raw or code_raw.startswith(t) or t in code_raw):
            return True
    return False


def parse_teaching_html(
    html_path: str | Path | None = None,
    html_content: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    subject_hint: str | None = None,
    selected_classes: List[str] | None = None,
) -> List[Dict]:
    """
    Parse a saved Teaching Timetable HTML file or HTML string.

    :param html_path: Path to HTML file saved from browser. Omit if html_content is provided.
    :param html_content: Raw HTML string (e.g. from fetch). Used when html_path is not provided.
    :param start_date: First teaching day of term (YYYY-MM-DD). Optional: auto-inferred from Meeting Date column if omitted.
    :param end_date: Last teaching day of term (YYYY-MM-DD). Optional: auto-inferred from Meeting Date column if omitted.
    :param subject_hint: Optional subject code to include in SUMMARY (e.g. 'CSCI').
    :param selected_classes: If provided, only include rows matching these identifiers
        (Class Code e.g. ROSE5720, or Class Nbr e.g. 9578). Empty = include all.

    Returns a list of dicts using the same keys as the CUSIS API where possible.
    """
    if html_content is not None:
        html = html_content
    elif html_path is not None:
        html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError("Provide either html_path or html_content.")
    soup = BeautifulSoup(html, "html.parser")

    table = _guess_timetable_table(soup)
    if table is None:
        raise ValueError("Could not find timetable table in HTML. Please check the file.")

    header_row = None
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if cells:
            header_row = [c.get_text(strip=True) for c in cells]
            break
    if not header_row:
        raise ValueError("Timetable table has no header row.")

    header_keys = [h.lower() for h in header_row]

    # Auto-infer term start/end from Meeting Date column when not provided
    if start_date is None or end_date is None:
        inferred_start, inferred_end = _infer_term_dates_from_table(table, header_keys)
        if start_date is None:
            start_date = inferred_start.isoformat() if inferred_start else None
        if end_date is None:
            end_date = inferred_end.isoformat() if inferred_end else None

    if not start_date or not end_date:
        raise ValueError(
            "Could not infer term dates from HTML (Meeting Date column). "
            "Please provide --term-start and --term-end (YYYY-MM-DD)."
        )

    term_start = date.fromisoformat(start_date)
    _ = date.fromisoformat(end_date)

    selected_set = [s.strip() for s in (selected_classes or []) if s and s.strip()]
    records: List[Dict] = []
    # Carry over class identity and display info for continuation rows
    current_class_code_raw = ""
    current_class_nbr = ""
    current_subj = ""
    current_catalog = ""
    current_section = ""
    current_title = ""
    current_instructor = ""
    # One event per (class, weekday, time) — skip duplicate rows (same course, same period)
    seen_slot: set[tuple[str, str, str, str]] = set()

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells or len(cells) != len(header_keys):
            continue
        row = [c.get_text(strip=True) for c in cells]
        data: Dict[str, str] = {}

        subj = ""
        catalog = ""
        section = ""
        title = ""
        instructor = ""
        day = ""
        time_range = ""
        room = ""
        class_code_raw = ""
        class_nbr = ""

        for key, val in zip(header_keys, row):
            if "class code" in key and val:
                class_code_raw = val
                if not (subj or catalog or section):
                    subj, catalog, section = _split_class_code(val)
            elif "class nbr" in key and val:
                class_nbr = val
            elif "subject" in key and not subj:
                subj = val
            elif ("course title" in key or "title" in key or "descr" in key) and not title:
                title = val
            elif ("course" in key or "catalog" in key) and not catalog and "class nbr" not in key:
                catalog = val
            elif ("section" in key or "class" in key) and not section and "class nbr" not in key:
                section = val
            elif ("instructor" in key or "teacher" in key or "teaching staff" in key) and not instructor:
                instructor = val
            elif "period" in key:
                time_range = val
                parts = val.split()
                if parts:
                    day = parts[0]
            elif "day" in key and not day:
                day = val
            elif "time" in key and not time_range:
                time_range = val
            elif ("room" in key or "venue" in key or "location" in key) and not room:
                room = val

        if class_code_raw or class_nbr:
            current_class_code_raw = class_code_raw
            current_class_nbr = class_nbr
            if subj or catalog or section:
                current_subj, current_catalog, current_section = subj, catalog, section
            if title:
                current_title = title
            if instructor:
                current_instructor = instructor
        data["CLASS_CODE_RAW"] = current_class_code_raw
        data["CLASS_NBR"] = current_class_nbr

        day_norm = _normalize_day(day) if day else None
        times = _parse_time_range(time_range) if time_range else None
        if not day_norm or not times:
            continue

        # One event per (class, day, time) — same course at same weekday/time only once
        slot_key = (current_class_code_raw, current_class_nbr, day_norm, time_range)
        if slot_key in seen_slot:
            continue
        seen_slot.add(slot_key)

        start_time, end_time = times

        data["SUBJECT"] = (subj or current_subj) or (subject_hint or "")
        data["CATALOG_NBR"] = catalog or current_catalog
        data["CLASS_SECTION"] = section or current_section
        data["DESCR"] = title or current_title or data["CATALOG_NBR"]
        data["INSTRUCTORS"] = instructor or current_instructor
        data["FDESCR"] = room
        data["COMDESC"] = data["SUBJECT"] or subject_hint or ""

        first_class_date = _first_date_for_weekday(term_start, day_norm)
        data["START_DT"] = first_class_date.isoformat()
        data["END_DT"] = end_date
        data["MEETING_TIME_START"] = start_time
        data["MEETING_TIME_END"] = end_time

        if selected_set and not _record_matches_selected(data, selected_set):
            continue
        records.append(data)

    if not records:
        raise ValueError("No class rows with valid day/time found in the HTML file.")

    return records

