"""Tests for schedule_html.py – My Weekly Schedule parser."""
import pytest
from datetime import date

from cuhk_timetable_export.schedule_html import (
    _normalize_day,
    _parse_day_pattern,
    _parse_time_range,
    _split_class_code,
    _parse_cusis_date,
    _resolve_iframe_html,
    parse_schedule_html,
)


# ── Day / time helpers ─────────────────────────────────────────

class TestNormalizeDay:
    def test_exact(self):
        assert _normalize_day("Mon") == "Mon"
        assert _normalize_day("Tue") == "Tue"

    def test_case_insensitive(self):
        assert _normalize_day("MON") == "Mon"
        assert _normalize_day("tuesday") == "Tue"

    def test_unknown(self):
        assert _normalize_day("xyz") is None


class TestParseDayPattern:
    def test_two_letter_concat(self):
        assert _parse_day_pattern("MoWeFr") == ["Mon", "Wed", "Fri"]
        assert _parse_day_pattern("TuTh") == ["Tue", "Thu"]

    def test_single_day(self):
        assert _parse_day_pattern("Mo") == ["Mon"]
        assert _parse_day_pattern("Sa") == ["Sat"]

    def test_comma_separated(self):
        assert _parse_day_pattern("Mon, Wed, Fri") == ["Mon", "Wed", "Fri"]

    def test_space_separated(self):
        assert _parse_day_pattern("Tue Thu") == ["Tue", "Thu"]

    def test_empty(self):
        assert _parse_day_pattern("") == []
        assert _parse_day_pattern("  ") == []


class TestParseTimeRange:
    def test_24h(self):
        assert _parse_time_range("10:30 - 11:15") == ("10:30", "11:15")

    def test_12h_pm(self):
        assert _parse_time_range("06:30PM - 09:15PM") == ("18:30", "21:15")

    def test_12h_am(self):
        assert _parse_time_range("08:30AM - 11:15AM") == ("08:30", "11:15")

    def test_noon(self):
        assert _parse_time_range("12:00PM - 01:15PM") == ("12:00", "13:15")

    def test_midnight(self):
        assert _parse_time_range("12:00AM - 01:15AM") == ("00:00", "01:15")

    def test_no_match(self):
        assert _parse_time_range("no time here") is None

    def test_en_dash(self):
        assert _parse_time_range("10:30AM\u201311:45AM") == ("10:30", "11:45")


class TestParseCusisDate:
    def test_normal(self):
        assert _parse_cusis_date("2026/01/05") == date(2026, 1, 5)
        assert _parse_cusis_date("2026/05/04") == date(2026, 5, 4)

    def test_invalid(self):
        assert _parse_cusis_date("not a date") is None
        assert _parse_cusis_date("") is None


# ── Weekly grid parsing (real CUSIS structure) ──────────────────

class TestParseWeeklyGrid:
    """Test with HTML structure matching real CUSIS WEEKLY_SCHED_HTMLAREA."""

    def _make_grid_html(self, course_blocks: list[tuple[int, str]]) -> str:
        """
        Build a minimal WEEKLY_SCHED_HTMLAREA table.
        course_blocks: list of (column_index, span_content)
        column_index: 1=Mon, 2=Tue, ..., 7=Sun
        """
        html = """<html><body>
        <span class="PSEDITBOX_DISPONLY" id="STDNT_WK_NO_MTG_START_DT$0">2026/01/05</span>
        <span class="PSEDITBOX_DISPONLY" id="STDNT_WK_NO_MTG_END_DT$0">2026/05/04</span>
        <table id="WEEKLY_SCHED_HTMLAREA" cellspacing="0" cellpadding="2" width="100%">
        <tr>
            <th>Time</th>
            <th>Monday<br>Feb 23</th>
            <th>Tuesday<br>Feb 24</th>
            <th>Wednesday<br>Feb 25</th>
            <th>Thursday<br>Feb 26</th>
            <th>Friday<br>Feb 27</th>
            <th>Saturday<br>Feb 28</th>
            <th>Sunday<br>Mar 1</th>
        </tr>
        """
        # Row at 18:00 with course blocks
        html += '<tr><td rowspan="2" scope="row"><span>18:00</span></td>'
        for col in range(1, 8):
            block = None
            for bc, content in course_blocks:
                if bc == col:
                    block = content
                    break
            if block:
                html += f'<td rowspan="6" style="color:rgb(0,0,0);background-color:rgb(182,209,146);text-align:center;">'
                html += f'<span style="color:rgb(0,0,0);background-color:rgb(182,209,146);">{block}</span></td>'
            else:
                html += '<td>&nbsp;</td>'
        html += '</tr>'
        # Add empty row for 18:30 half-hour
        html += '<tr>'
        for col in range(1, 8):
            has_block = any(bc == col for bc, _ in course_blocks)
            if not has_block:
                html += '<td>&nbsp;</td>'
        html += '</tr>'
        html += '</table></body></html>'
        return html

    def test_single_course_monday(self):
        html = self._make_grid_html([
            (1, "ROSE 5770 - -<br>Lecture<br>18:30 - 21:15<br>Li Koon Chun Hall LT1"),
        ])
        courses = parse_schedule_html(html_content=html)
        assert len(courses) == 1
        c = courses[0]
        assert c["SUBJECT"] == "ROSE"
        assert c["CATALOG_NBR"] == "5770"
        assert c["MEETING_TIME_START"] == "18:30"
        assert c["MEETING_TIME_END"] == "21:15"
        assert c["FDESCR"] == "Li Koon Chun Hall LT1"
        assert c["START_DT"] == "2026-01-05"  # Mon in first week
        assert c["END_DT"] == "2026-05-04"

    def test_multiple_courses(self):
        html = self._make_grid_html([
            (1, "ROSE 5770 - -<br>Lecture<br>18:30 - 21:15<br>Li Koon Chun Hall LT1"),
            (2, "ROSE 5720 - -<br>Lecture<br>18:30 - 21:15<br>Lee Shau Kee Building LT2"),
            (5, "ROSE 5730 - -<br>Lecture<br>18:30 - 21:15<br>William M W Mong Eng Bldg 407"),
        ])
        courses = parse_schedule_html(html_content=html)
        assert len(courses) == 3

        by_code = {c["CLASS_CODE_RAW"]: c for c in courses}
        assert "ROSE5770" in by_code
        assert "ROSE5720" in by_code
        assert "ROSE5730" in by_code

        assert by_code["ROSE5770"]["FDESCR"] == "Li Koon Chun Hall LT1"
        assert by_code["ROSE5730"]["FDESCR"] == "William M W Mong Eng Bldg 407"

    def test_no_data_raises(self):
        html = "<html><body><p>Nothing here</p></body></html>"
        with pytest.raises(ValueError, match="Could not extract"):
            parse_schedule_html(html_content=html, start_date="2026-01-13", end_date="2026-05-09")


class TestParseRealHtml:
    """Test with the actual saved CUSIS HTML file."""

    def test_parse_real_iframe_html(self):
        real_path = (
            "/Users/toh/Documents/Dev/TOHgoto/cuhk-timetable-exporter/"
            "examples/My Weekly Schedule_files/"
            "SSR_STUDENT_FL.SSR_SSENRL_SCHD_W.html"
        )
        from pathlib import Path
        if not Path(real_path).exists():
            pytest.skip("Real iframe HTML file not available")

        courses = parse_schedule_html(html_path=real_path)

        # Should have 5 courses (Mon-Fri)
        assert len(courses) == 5

        codes = sorted(c["CLASS_CODE_RAW"] for c in courses)
        assert codes == ["ROSE5720", "ROSE5730", "ROSE5760", "ROSE5770", "ROSE5780"]

        # All start at 18:30 and end at 21:15
        for c in courses:
            assert c["MEETING_TIME_START"] == "18:30"
            assert c["MEETING_TIME_END"] == "21:15"

        # Term dates from STDNT_WK_NO_MTG table
        for c in courses:
            assert c["END_DT"] == "2026-05-04"

    def test_parse_outer_html_with_iframe(self):
        """Test that the outer HTML auto-resolves the iframe content."""
        real_path = (
            "/Users/toh/Documents/Dev/TOHgoto/cuhk-timetable-exporter/"
            "examples/My Weekly Schedule.html"
        )
        from pathlib import Path
        if not Path(real_path).exists():
            pytest.skip("Real outer HTML file not available")

        courses = parse_schedule_html(html_path=real_path)
        assert len(courses) == 5


class TestIframeResolution:
    def test_resolve_iframe_from_saved_page(self, tmp_path):
        """Test that iframe content is loaded from _files/ directory."""
        main_html = """
        <html><body>
        <iframe id="main_target_win0" src="./test_page_files/schedule.html"></iframe>
        </body></html>
        """
        main_file = tmp_path / "test_page.html"
        main_file.write_text(main_html, encoding="utf-8")

        files_dir = tmp_path / "test_page_files"
        files_dir.mkdir()
        iframe_html = """<html><body>
        <span id="STDNT_WK_NO_MTG_START_DT$0">2026/01/13</span>
        <span id="STDNT_WK_NO_MTG_END_DT$0">2026/05/09</span>
        <table id="WEEKLY_SCHED_HTMLAREA">
        <tr>
            <th>Time</th><th>Monday<br>Jan 13</th><th>Tuesday<br>Jan 14</th>
            <th>Wednesday<br>Jan 15</th><th>Thursday<br>Jan 16</th>
            <th>Friday<br>Jan 17</th><th>Saturday<br>Jan 18</th>
            <th>Sunday<br>Jan 19</th>
        </tr>
        <tr>
            <td rowspan="2" scope="row"><span>14:00</span></td>
            <td>&nbsp;</td>
            <td>&nbsp;</td>
            <td rowspan="4" style="background-color:rgb(182,209,146);text-align:center;">
                <span style="background-color:rgb(182,209,146);">PHYS 1110 - -<br>Lecture<br>14:30 - 16:15<br>SC L1</span>
            </td>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
        </tr>
        </table></body></html>
        """
        (files_dir / "schedule.html").write_text(iframe_html, encoding="utf-8")

        courses = parse_schedule_html(html_path=str(main_file))
        assert len(courses) == 1
        assert courses[0]["SUBJECT"] == "PHYS"
        assert courses[0]["CATALOG_NBR"] == "1110"
        assert courses[0]["MEETING_TIME_START"] == "14:30"
        assert courses[0]["MEETING_TIME_END"] == "16:15"


class TestScrollAreaFallback:
    def test_basic_scroll_area(self):
        """Test fallback to scroll area parsing."""
        html = """
        <html><body>
        <span id="DERIVED_REGFRM1_SSR_CLASSNAME_35$0">CSCI3100 - Software Engineering</span>
        <span id="PSXS_CLS_SCHD_SCD_CLASS_TIME$0">10:30AM - 11:45AM</span>
        <span id="PSXS_CLS_SCHD_SCD_CLASS_MTG_PAT$0">TuTh</span>
        <span id="PSXS_CLS_SCHD_SCD_ROOM$0">ERB 407</span>

        <span id="DERIVED_REGFRM1_SSR_CLASSNAME_35$1">MATH1010 - Linear Algebra</span>
        <span id="PSXS_CLS_SCHD_SCD_CLASS_TIME$1">09:30AM - 10:15AM</span>
        <span id="PSXS_CLS_SCHD_SCD_CLASS_MTG_PAT$1">MoWeFr</span>
        <span id="PSXS_CLS_SCHD_SCD_ROOM$1">LSB LT1</span>
        </body></html>
        """
        courses = parse_schedule_html(
            html_content=html,
            start_date="2026-01-13",
            end_date="2026-05-09",
        )
        assert len(courses) >= 2
        csci = [c for c in courses if c["SUBJECT"] == "CSCI"]
        assert len(csci) == 2  # Tue + Thu

        math = [c for c in courses if c["SUBJECT"] == "MATH"]
        assert len(math) == 3  # Mon + Wed + Fri


class TestParseDatedGrid:
    """Test parse_weekly_grid_dated() which returns SINGLE_DATE."""

    def test_returns_concrete_dates(self):
        html = """<html><body>
        <td class="PSGROUPBOXLABEL" align="CENTER">Week of 2026/2/23 - 2026/3/1</td>
        <table id="WEEKLY_SCHED_HTMLAREA">
        <tr>
            <th>Time</th>
            <th>Monday<br>Feb 23</th><th>Tuesday<br>Feb 24</th>
            <th>Wednesday<br>Feb 25</th><th>Thursday<br>Feb 26</th>
            <th>Friday<br>Feb 27</th><th>Saturday<br>Feb 28</th>
            <th>Sunday<br>Mar 1</th>
        </tr>
        <tr>
            <td rowspan="2"><span>18:00</span></td>
            <td rowspan="6" style="background-color:rgb(182,209,146);text-align:center;">
                <span style="background-color:rgb(182,209,146);">ROSE 5770 - -<br>Lecture<br>18:30 - 21:15<br>Hall LT1</span>
            </td>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            <td rowspan="6" style="background-color:rgb(182,209,146);text-align:center;">
                <span style="background-color:rgb(182,209,146);">ROSE 5730 - -<br>Lecture<br>18:30 - 21:15<br>Eng Bldg 407</span>
            </td>
            <td>&nbsp;</td><td>&nbsp;</td>
        </tr>
        </table></body></html>
        """
        from cuhk_timetable_export.schedule_html import parse_weekly_grid_dated
        records = parse_weekly_grid_dated(html, year_hint=2026)
        assert len(records) == 2

        by_code = {r["CLASS_CODE_RAW"]: r for r in records}
        assert by_code["ROSE5770"]["SINGLE_DATE"] == "2026-02-23"  # Monday
        assert by_code["ROSE5730"]["SINGLE_DATE"] == "2026-02-27"  # Friday

    def test_no_rrule_in_single_date_export(self, tmp_path):
        """SINGLE_DATE events should NOT have RRULE in ICS."""
        from cuhk_timetable_export.export import export_ics

        courses = [
            {
                "SUBJECT": "ROSE",
                "CATALOG_NBR": "5770",
                "CLASS_SECTION": "",
                "SINGLE_DATE": "2026-02-23",
                "MEETING_TIME_START": "18:30",
                "MEETING_TIME_END": "21:15",
                "INSTRUCTORS": "",
                "DESCR": "Lecture",
                "FDESCR": "Hall LT1",
            }
        ]
        out = tmp_path / "test.ics"
        export_ics(courses, out)
        content = out.read_text()

        assert "RRULE" not in content
        assert "20260223T183000" in content
        assert "ROSE5770" in content

