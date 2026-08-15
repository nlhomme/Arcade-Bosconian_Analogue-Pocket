#!/usr/bin/env python3
"""Self-test for check_timing.py. Stdlib only: python3 test_check_timing.py"""
import tempfile
from pathlib import Path

from check_timing import check_timing, main, parse_summary

# Reproduces the real Quartus table, including the two leading spaces on
# clock rows and the Design-wide TNS block that follows the slack block.
REPORT_TEMPLATE = """+----------------------------------------------------------------+
; Multicorner Timing Analysis Summary                            ;
+--------------------------------+--------+-------+----------+---------+---------------------+
; Clock                          ; Setup  ; Hold  ; Recovery ; Removal ; Minimum Pulse Width ;
+--------------------------------+--------+-------+----------+---------+---------------------+
; Worst-case Slack               ; {setup} ; {hold} ; N/A      ; N/A     ; {mpw} ;
;  bridge_spiclk                 ; 10.781 ; 0.170 ; N/A      ; N/A     ; 5.950               ;
;  clk_74a                       ; {clk_setup} ; 0.126 ; N/A      ; N/A     ; 5.159               ;
;  ic|mp1|gpll~FRACTIONAL_PLL|vc ; N/A    ; N/A   ; N/A      ; N/A     ; 0.830               ;
; Design-wide TNS                ; 0.0    ; 0.0   ; 0.0      ; 0.0     ; 0.0                 ;
;  clk_74a                       ; 0.000  ; 0.000 ; N/A      ; N/A     ; 0.000               ;
+--------------------------------+--------+-------+----------+---------+---------------------+


+------------------+
; Some Other Table ;
+------------------+
"""


def make_report(setup="6.852", hold="0.126", mpw="0.830", clk_setup="6.852"):
    return REPORT_TEMPLATE.format(
        setup=setup, hold=hold, mpw=mpw, clk_setup=clk_setup
    )


def write(tmp, text):
    path = Path(tmp) / "ap_core.sta.rpt"
    path.write_text(text)
    return path


def test_parse_summary_reads_columns_and_indented_clock_rows():
    columns, rows = parse_summary(make_report())
    assert columns == ["Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"]
    labels = [label for label, _ in rows]
    assert labels[0] == "Worst-case Slack"
    assert "bridge_spiclk" in labels
    assert rows[1][1][0] == 10.781


def test_passing_report_passes_and_reports_worst_case():
    with tempfile.TemporaryDirectory() as d:
        report = write(d, make_report())
        worst = check_timing(report)
        assert "Setup 6.852" in worst
        assert "Recovery N/A" in worst
        assert main([str(report)]) == 0


def test_negative_setup_slack_fails_and_names_the_clock():
    with tempfile.TemporaryDirectory() as d:
        report = write(d, make_report(setup="-0.412", clk_setup="-0.412"))
        try:
            check_timing(report)
        except ValueError as exc:
            assert "clk_74a" in str(exc) and "Setup" in str(exc)
        else:
            raise AssertionError("expected ValueError on negative Setup slack")
        assert main([str(report)]) == 1


def test_negative_slack_outside_setup_column_fails():
    with tempfile.TemporaryDirectory() as d:
        report = write(d, make_report(mpw="-1.250"))
        try:
            check_timing(report)
        except ValueError as exc:
            assert "Minimum Pulse Width" in str(exc)
            assert "Worst-case Slack" in str(exc)
        else:
            raise AssertionError("expected ValueError on negative pulse width")


def test_na_values_are_not_failures():
    with tempfile.TemporaryDirectory() as d:
        report = write(d, make_report(hold="N/A"))
        assert "Hold N/A" in check_timing(report)


def test_unrecognised_report_fails_rather_than_passing():
    with tempfile.TemporaryDirectory() as d:
        report = write(d, "Quartus ran, and said nothing useful at all.\n")
        try:
            check_timing(report)
        except ValueError as exc:
            assert "Multicorner Timing Analysis Summary" in str(exc)
        else:
            raise AssertionError("expected ValueError on unrecognised report")
        assert main([str(report)]) == 1


def test_truncated_table_fails():
    """A report cut off after the title must not count as timing met."""
    text = make_report().split("; Clock")[0]
    with tempfile.TemporaryDirectory() as d:
        report = write(d, text)
        try:
            check_timing(report)
        except ValueError as exc:
            assert "header" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError on truncated table")


def test_unreadable_value_fails():
    text = make_report().replace("; 10.781 ;", "; oops   ;")
    with tempfile.TemporaryDirectory() as d:
        report = write(d, text)
        try:
            check_timing(report)
        except ValueError as exc:
            assert "oops" in str(exc) and "bridge_spiclk" in str(exc)
        else:
            raise AssertionError("expected ValueError on unreadable value")


def test_missing_file_returns_nonzero():
    with tempfile.TemporaryDirectory() as d:
        assert main([str(Path(d) / "nope.rpt")]) == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
