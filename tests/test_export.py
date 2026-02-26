import pytest
from datetime import datetime
from pathlib import Path
from cuhk_timetable_export.export import export_ics

def test_export_ics(tmp_path):
    out_path = tmp_path / "test.ics"
    courses = [{
        "START_DT": "2026-01-05",
        "MEETING_TIME_START": "10:30",
        "MEETING_TIME_END": "12:15",
        "END_DT": "2026-04-18",
        "SUBJECT": "ROSE",
        "CATALOG_NBR": "5720",
        "CLASS_SECTION": "-",
        "DESCR": "Test Course",
        "INSTRUCTORS": "Prof. Smith",
        "FDESCR": "Room A"
    }]
    
    export_ics(courses, out_path)
    
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    
    # Verify standard ICS elements
    assert "BEGIN:VCALENDAR" in content
    assert "BEGIN:VEVENT" in content
    assert "END:VEVENT" in content
    assert "END:VCALENDAR" in content
    
    # Verify Timezone is applied correctly (should contain TZID=Asia/Hong_Kong)
    assert "DTSTART;TZID=Asia/Hong_Kong:20260105T103000" in content
    assert "DTEND;TZID=Asia/Hong_Kong:20260105T121500" in content
    
    # Verify UID is present
    assert "UID:" in content
    assert "@cuhk-timetable-export" in content
    
    # Verify RRULE
    # 2026-04-18 is localized to UTC for UNTIL block
    assert "UNTIL=20260418T235959Z" in content
    assert "FREQ=WEEKLY" in content
