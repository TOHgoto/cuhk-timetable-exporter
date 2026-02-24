"""
Export timetable data to ICS, CSV, and JSON.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import icalendar

# Hong Kong timezone for calendar
TZ_HK = "Asia/Hong_Kong"


def _parse_time(date_str: str, time_str: str) -> datetime:
    """Parse START_DT/END_DT (e.g. 2025-01-13) and MEETING_TIME_START/END (e.g. 10:30)."""
    if not date_str or not time_str:
        raise ValueError("Missing date or time")
    # time_str might be "10:30" or "10:30:00"
    if len(time_str) == 5 and ":" in time_str:
        time_str = time_str + ":00"
    dt_str = f"{date_str.strip()} {time_str.strip()}"
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")


def export_ics(courses: list[dict], out_path: str | Path) -> None:
    """Export timetable to iCalendar (.ics) for Apple/Google calendar."""
    cal = icalendar.Calendar()
    cal.add("prodid", "-//CUHK Timetable Export//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "CUHK Timetable")
    cal.add("x-wr-timezone", TZ_HK)

    for c in courses:
        try:
            # First meeting date for this class
            start = _parse_time(
                c.get("START_DT", ""), c.get("MEETING_TIME_START", "")
            )
            # Same day, but using meeting end time
            end = _parse_time(c.get("START_DT", ""), c.get("MEETING_TIME_END", ""))
        except (ValueError, KeyError):
            continue

        # Event title: course code + optional section (no trailing dashes)
        subj = c.get("SUBJECT", "") or ""
        catalog = c.get("CATALOG_NBR", "") or ""
        section = (c.get("CLASS_SECTION") or "").strip()
        if section and section != "-":
            summary = f"{subj}{catalog}-{section}"
        else:
            summary = f"{subj}{catalog}"

        desc = f"Instructors: {c.get('INSTRUCTORS', '')}\nCourse: {c.get('DESCR', '')}"
        location = c.get("FDESCR", "")

        event = icalendar.Event()
        event.add("summary", summary)
        event.add("description", desc)
        event.add("location", location)
        event.add("dtstart", start)
        event.add("dtend", end)
        event.add("dtstamp", datetime.now())
        # Weekly recurrence until end date (ICAL UNTIL is date in UTC)
        end_date = c.get("END_DT", "")
        if end_date:
            until_ical = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%dT235959Z")
            event.add("rrule", f"FREQ=WEEKLY;UNTIL={until_ical}")
        cal.add_component(event)

    Path(out_path).write_text(cal.to_ical().decode("utf-8"), encoding="utf-8")


def export_csv(courses: list[dict], out_path: str | Path) -> None:
    """Export timetable to CSV."""
    if not courses:
        Path(out_path).write_text("", encoding="utf-8")
        return
    keys = list(courses[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(courses)


def export_json(courses: list[dict], out_path: str | Path) -> None:
    """Export timetable to JSON."""
    Path(out_path).write_text(
        json.dumps(courses, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def export(courses: list[dict], out_path: str | Path, fmt: str) -> None:
    """Export to the given format: ics, csv, or json."""
    fmt = fmt.lower()
    if fmt == "ics":
        export_ics(courses, out_path)
    elif fmt == "csv":
        export_csv(courses, out_path)
    elif fmt == "json":
        export_json(courses, out_path)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Use ics, csv, or json.")
