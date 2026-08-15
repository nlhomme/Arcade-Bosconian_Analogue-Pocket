#!/usr/bin/env python3
"""Fail the build when a Quartus .sta.rpt reports negative slack.

quartus_sh --flow compile exits 0 even when the design misses timing, so
this is the only thing standing between a failing bitstream and a green CI
run. It parses the "Multicorner Timing Analysis Summary" table, which looks
like:

    ; Clock            ; Setup  ; Hold  ; Recovery ; Removal ; Minimum Pulse Width ;
    ; Worst-case Slack ; 6.852  ; 0.126 ; N/A      ; N/A     ; 0.830               ;
    ;  clk_74a         ; 6.852  ; 0.126 ; N/A      ; N/A     ; 5.159               ;

Any negative number in that table is a failure. A report whose format is not
recognised is also a failure: silence must never be read as "timing met".
"""
import argparse
import sys
from pathlib import Path

TABLE_TITLE = "Multicorner Timing Analysis Summary"
WORST_CASE_ROW = "Worst-case Slack"


def split_row(line):
    """Split a '; a ; b ; c ;' report row into stripped cells, or None."""
    stripped = line.strip()
    if not stripped.startswith(";") or not stripped.endswith(";"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split(";")]


def parse_summary(text):
    """Return (columns, [(label, [values...]), ...]) for the timing summary.

    Values are floats, or None for N/A. Raises ValueError if the table is
    missing or does not look the way we expect.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        cells = split_row(line)
        if cells and cells[0] == TABLE_TITLE:
            break
    else:
        raise ValueError(
            f"no {TABLE_TITLE!r} table found; the report format is not "
            "recognised, so timing cannot be confirmed"
        )

    columns = None
    rows = []
    for line in lines[index + 1:]:
        cells = split_row(line)
        if cells is None:
            if rows:
                break  # closing rule: end of table
            continue  # +---+---+ rules around the header row
        if columns is None:
            if cells[0] != "Clock":
                raise ValueError(
                    f"{TABLE_TITLE}: expected a 'Clock' header row, got "
                    f"{cells[0]!r}"
                )
            columns = cells[1:]
            continue
        label, values = cells[0], cells[1:]
        if len(values) != len(columns):
            raise ValueError(
                f"{TABLE_TITLE}: row {label!r} has {len(values)} values but "
                f"the header has {len(columns)} columns"
            )
        parsed = []
        for column, value in zip(columns, values):
            if value.upper() == "N/A":
                parsed.append(None)
                continue
            try:
                parsed.append(float(value))
            except ValueError:
                raise ValueError(
                    f"{TABLE_TITLE}: cannot read {column} value {value!r} for "
                    f"{label!r}"
                ) from None
        rows.append((label, parsed))

    if columns is None:
        raise ValueError(f"{TABLE_TITLE}: table has no header row")
    if not rows:
        raise ValueError(f"{TABLE_TITLE}: table has no data rows")
    if not any(label == WORST_CASE_ROW for label, _ in rows):
        raise ValueError(f"{TABLE_TITLE}: no {WORST_CASE_ROW!r} row")
    return columns, rows


def check_timing(path):
    """Return the summary line to print, or raise ValueError on failure."""
    columns, rows = parse_summary(Path(path).read_text(errors="replace"))

    failures = [
        f"{label}: {column} slack {value}"
        for label, values in rows
        for column, value in zip(columns, values)
        if value is not None and value < 0
    ]
    if failures:
        raise ValueError(
            "timing not met in "
            + str(path)
            + ":\n  "
            + "\n  ".join(failures)
        )

    worst = next(values for label, values in rows if label == WORST_CASE_ROW)
    return ", ".join(
        f"{column} {'N/A' if value is None else value}"
        for column, value in zip(columns, worst)
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path, help="path to the Quartus .sta.rpt")
    args = ap.parse_args(argv)

    if not args.report.is_file():
        print(f"error: {args.report}: no such file", file=sys.stderr)
        return 1

    try:
        worst = check_timing(args.report)
    except ValueError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"Timing met. Worst-case slack: {worst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
