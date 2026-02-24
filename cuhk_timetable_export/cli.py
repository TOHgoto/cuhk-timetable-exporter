"""
Command-line interface: fetch CUHK timetable and export to file.
"""
from __future__ import annotations

import argparse
import warnings

# Suppress urllib3/OpenSSL warning on systems with LibreSSL (no impact on functionality)
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*", module="urllib3")
import sys
from pathlib import Path

from . import __version__
from .export import export
from .teaching_fetch import fetch_teaching_timetable_html
from .teaching_html import parse_teaching_html


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export CUHK timetable to ICS / CSV / JSON.\n"
            "- Teaching Timetable mode: fetch from CUHK Teaching Timetable page or parse saved HTML (no CUSIS login needed)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-o",
        "--output",
        default="cuhk_timetable",
        help="Output path (without extension). Default: cuhk_timetable",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["ics", "csv", "json"],
        default="ics",
        help="Export format. Default: ics",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fetch-teaching",
        action="store_true",
        help="Fetch Teaching Timetable from CUHK website: open captcha, you enter code, then export. Requires --selected-file (e.g. my_courses.txt).",
    )
    mode.add_argument(
        "--teaching-html",
        metavar="HTML_PATH",
        help="Use Teaching Timetable HTML file instead of SID/password. No login required.",
    )

    # Teaching Timetable mode options
    parser.add_argument(
        "--term-start",
        metavar="YYYY-MM-DD",
        help="(Teaching Timetable mode) First teaching day of the term, e.g. 2025-09-02.",
    )
    parser.add_argument(
        "--term-end",
        metavar="YYYY-MM-DD",
        help="(Teaching Timetable mode) Last teaching day of the term, e.g. 2025-12-05.",
    )
    parser.add_argument(
        "--subject-hint",
        help="(Teaching Timetable mode) Optional subject code to show in summary, e.g. CSCI.",
    )
    parser.add_argument(
        "--selected",
        metavar="LIST",
        help="(Teaching Timetable mode) Comma-separated list of classes to include (e.g. ROSE5720,9578,ROSE5730). "
        "Use Class Code (ROSE5720) or Class Nbr (9578). If omitted, all classes in the HTML are exported.",
    )
    parser.add_argument(
        "--selected-file",
        metavar="PATH",
        help="(Teaching Timetable mode) Path to a file with one class identifier per line (same format as --selected).",
    )
    parser.add_argument(
        "--list-classes",
        action="store_true",
        help="(Teaching Timetable mode) List all classes in the HTML (Class Code, Class Nbr, Title) then exit. Use to build your --selected list.",
    )
    args = parser.parse_args()

    # Fetch Teaching Timetable from website (captcha only manual step)
    if args.fetch_teaching:
        selected_classes: list[str] = []
        if args.selected:
            selected_classes.extend(s.strip() for s in args.selected.split(",") if s.strip())
        if args.selected_file:
            p = Path(args.selected_file)
            if not p.exists():
                print(f"Error: --selected-file not found: {p}", file=sys.stderr)
                return 1
            selected_classes.extend(
                line.strip()
                for line in p.read_text(encoding="utf-8").splitlines()
                if (s := line.strip()) and not s.startswith("#")
            )
        if not selected_classes:
            print(
                "Error: --fetch-teaching requires course list. Use --selected-file my_courses.txt (one course code per line, e.g. ROSE5720).",
                file=sys.stderr,
            )
            return 1
        try:
            print("Fetching Teaching Timetable page...")
            result_html = fetch_teaching_timetable_html(course_codes=selected_classes)
        except Exception as e:
            print(f"Error fetching timetable: {e}", file=sys.stderr)
            return 1
        try:
            courses = parse_teaching_html(
                html_content=result_html,
                start_date=args.term_start,
                end_date=args.term_end,
                subject_hint=args.subject_hint,
                selected_classes=selected_classes,
            )
        except Exception as e:
            print(f"Error parsing result: {e}", file=sys.stderr)
            return 1
        ext = {"ics": ".ics", "csv": ".csv", "json": ".json"}[args.format]
        out_path = Path(args.output).with_suffix(ext) if Path(args.output).suffix else Path(args.output + ext)
        export(courses, out_path, args.format)
        print(f"Exported {len(courses)} course(s) to {out_path}")
        return 0

    # Teaching Timetable mode from saved HTML (no login)
    elif args.teaching_html:
        # term-start/term-end are optional: auto-inferred from Meeting Date column when omitted
        selected_classes: list[str] = []
        if args.selected:
            selected_classes.extend(s.strip() for s in args.selected.split(",") if s.strip())
        if args.selected_file:
            p = Path(args.selected_file)
            if not p.exists():
                print(f"Error: --selected-file not found: {p}", file=sys.stderr)
                return 1
            selected_classes.extend(
                line.strip()
                for line in p.read_text(encoding="utf-8").splitlines()
                if (s := line.strip()) and not s.startswith("#")
            )
        try:
            courses = parse_teaching_html(
                html_path=args.teaching_html,
                start_date=args.term_start,
                end_date=args.term_end,
                subject_hint=args.subject_hint,
                selected_classes=None if args.list_classes else (selected_classes if selected_classes else None),
            )
        except Exception as e:
            print(f"Error parsing Teaching Timetable HTML: {e}", file=sys.stderr)
            return 1

        if args.list_classes:
            seen = set()
            print("Class Code       | Class Nbr | Course Title")
            print("-" * 60)
            for c in courses:
                key = (c.get("CLASS_CODE_RAW") or "", c.get("CLASS_NBR") or "")
                if key in seen or not (key[0] or key[1]):
                    continue
                seen.add(key)
                code = (c.get("CLASS_CODE_RAW") or "").strip()
                nbr = (c.get("CLASS_NBR") or "").strip()
                title = (c.get("DESCR") or "").strip()[:40]
                print(f"{code:<16} | {nbr:<9} | {title}")
            print("\nUse: --selected ROSE5720,9578,ROSE5730  (or put identifiers in a file and use --selected-file)")
            return 0
    else:
        print(
            "No mode specified. Use --fetch-teaching to fetch from Teaching Timetable website "
            "or --teaching-html for a saved HTML file.",
            file=sys.stderr,
        )
        return 1

    ext = {"ics": ".ics", "csv": ".csv", "json": ".json"}[args.format]
    out_path = Path(args.output).with_suffix(ext) if Path(args.output).suffix else Path(args.output + ext)
    export(courses, out_path, args.format)
    print(f"Exported {len(courses)} course(s) to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
