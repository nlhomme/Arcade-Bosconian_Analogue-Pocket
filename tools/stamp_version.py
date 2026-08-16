#!/usr/bin/env python3
"""Stamp a core.json's version and release date from the build's git ref.

The openFPGA cores inventory reads `metadata.version` to decide whether an
installed core is out of date, and the Pocket shows it in the core's info
screen. Editing it by hand drifts: v0.1.1 shipped while core.json still
said 0.1.0. This makes the packaged copy follow the tag automatically.

Tagged builds get the tag with any leading "v" removed. Untagged builds get
a clearly non-release string so a development zip can never be mistaken for
a published version.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# The Pocket shows this string; keep it short and obviously a version.
MAX_VERSION_LEN = 31


def version_from_ref(ref, sha=None, today=None):
    """Return (version, date) for a git ref name.

    `ref` is GITHUB_REF_NAME: a tag like "v0.1.2" on a tag build, or a
    branch name otherwise.
    """
    today = today or datetime.date.today().isoformat()
    if ref and re.fullmatch(r"v?\d+\.\d+\.\d+[A-Za-z0-9.\-]*", ref):
        return ref.lstrip("v"), today
    # Not a release build. Say so plainly rather than inventing a number.
    short = (sha or "unknown")[:7]
    return f"dev-{short}", today


def stamp(path, ref, sha=None, today=None):
    path = Path(path)
    data = json.loads(path.read_text())
    meta = data["core"]["metadata"]
    version, date = version_from_ref(ref, sha, today)
    if len(version) > MAX_VERSION_LEN:
        raise ValueError(f"version {version!r} exceeds {MAX_VERSION_LEN} chars")
    meta["version"] = version
    meta["date_release"] = date
    path.write_text(json.dumps(data, indent=4) + "\n")
    return version, date


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("core_json", type=Path, help="path to the packaged core.json")
    ap.add_argument("--ref", default=None, help="git ref name (default: $GITHUB_REF_NAME)")
    ap.add_argument("--sha", default=None, help="commit sha (default: $GITHUB_SHA)")
    args = ap.parse_args(argv)

    import os

    ref = args.ref if args.ref is not None else os.environ.get("GITHUB_REF_NAME", "")
    sha = args.sha if args.sha is not None else os.environ.get("GITHUB_SHA", "")
    try:
        version, date = stamp(args.core_json, ref, sha)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"stamped {args.core_json}: version={version} date_release={date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
