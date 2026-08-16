#!/usr/bin/env python3
"""Self-test for stamp_version.py. Stdlib only: python3 test_stamp_version.py"""
import json
import tempfile
from pathlib import Path

from stamp_version import stamp, version_from_ref

CORE_JSON = {
    "core": {
        "magic": "APF_VER_1",
        "metadata": {
            "platform_ids": ["bosconian"],
            "shortname": "Bosconian",
            "version": "0.0.0",
            "date_release": "1970-01-01",
        },
    }
}


def write_core(tmp):
    p = tmp / "core.json"
    p.write_text(json.dumps(CORE_JSON, indent=4))
    return p


def test_tag_becomes_version_without_leading_v():
    assert version_from_ref("v0.1.2", today="2026-01-02") == ("0.1.2", "2026-01-02")
    assert version_from_ref("0.1.2", today="2026-01-02") == ("0.1.2", "2026-01-02")


def test_prerelease_tag_is_kept_whole():
    v, _ = version_from_ref("v1.2.3-beta.1")
    assert v == "1.2.3-beta.1"


def test_branch_build_is_marked_dev_not_a_version():
    v, _ = version_from_ref("analogue", sha="abcdef1234567890")
    assert v == "dev-abcdef1", v  # short sha is 7 chars
    # a development build must never look like a release
    assert not v[0].isdigit()


def test_empty_ref_is_marked_dev():
    v, _ = version_from_ref("", sha="")
    assert v.startswith("dev-")


def test_stamp_rewrites_the_file_and_keeps_other_fields():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = write_core(tmp)
        stamp(p, "v2.0.0", today="2026-03-04")
        meta = json.loads(p.read_text())["core"]["metadata"]
        assert meta["version"] == "2.0.0"
        assert meta["date_release"] != "1970-01-01"
        assert meta["platform_ids"] == ["bosconian"], "unrelated fields must survive"
        assert meta["shortname"] == "Bosconian"


def test_stamp_rejects_an_absurdly_long_version():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = write_core(tmp)
        try:
            stamp(p, "v1.0.0-" + "x" * 60)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on an over-long version")


def test_stamp_reports_a_malformed_core_json():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "core.json"
        p.write_text('{"not_a_core": true}')
        try:
            stamp(p, "v1.0.0")
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError on a core.json with no metadata")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
