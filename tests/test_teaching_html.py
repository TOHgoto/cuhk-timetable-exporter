import pytest
from datetime import date
from cuhk_timetable_export.teaching_html import (
    _parse_time_range,
    _normalize_day,
    _split_class_code,
    _record_matches_selected,
)

def test_parse_time_range():
    # 24-hour exact
    assert _parse_time_range("10:30 - 11:15") == ("10:30", "11:15")
    assert _parse_time_range("14:30 - 16:15") == ("14:30", "16:15")
    
    # 12-hour AM/PM
    assert _parse_time_range("06:30PM - 09:15PM") == ("18:30", "21:15")
    assert _parse_time_range("08:30AM - 11:15AM") == ("08:30", "11:15")
    assert _parse_time_range("12:00PM - 01:15PM") == ("12:00", "13:15")
    assert _parse_time_range("12:00AM - 01:15AM") == ("00:00", "01:15")

def test_normalize_day():
    # Exact matches
    assert _normalize_day("Mon") == "Mon"
    assert _normalize_day("Monday") == "Mon"
    assert _normalize_day("th") == "Thu"
    assert _normalize_day("thur") == "Thu"
    assert _normalize_day("tuesday") == "Tue"
    assert _normalize_day("tu") == "Tue"

    # Case insensitivity
    assert _normalize_day("MON") == "Mon"
    assert _normalize_day(" TUESday ") == "Tue"
    assert _normalize_day("Unknown") is None


def test_split_class_code():
    # 4-letter subject
    assert _split_class_code("ROSE5720") == ("ROSE", "5720", "")
    assert _split_class_code("ROSE5720-") == ("ROSE", "5720", "-")
    assert _split_class_code("MATH1010A") == ("MATH", "1010", "A")

    # 2-6 letter edge cases
    assert _split_class_code("CS202") == ("CS", "202", "")
    assert _split_class_code("CHLL1900") == ("CHLL", "1900", "")
    assert _split_class_code("UGEA1000") == ("UGEA", "1000", "")
    
    # Invalid codes
    assert _split_class_code("12345") == ("", "12345", "")


def test_record_matches_selected():
    # Match by Class Nbr
    assert _record_matches_selected({"CLASS_NBR": "9578", "CLASS_CODE_RAW": "ROSE5720"}, ["9578"]) is True
    assert _record_matches_selected({"CLASS_NBR": "9578", "CLASS_CODE_RAW": "ROSE5720"}, ["1234"]) is False

    # Match by Class Code Exact
    assert _record_matches_selected({"CLASS_NBR": "9578", "CLASS_CODE_RAW": "ROSE5720-"}, ["ROSE5720-"]) is True
    
    # Match by Class Code prefix
    assert _record_matches_selected({"CLASS_NBR": "9578", "CLASS_CODE_RAW": "ROSE5720-"}, ["ROSE5720"]) is True

    # Empty selected means false here, though parser handles empty independently
    assert _record_matches_selected({"CLASS_NBR": "9578", "CLASS_CODE_RAW": "ROSE5720-"}, []) is False
