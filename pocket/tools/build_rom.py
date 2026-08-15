#!/usr/bin/env python3
"""Build an Analogue Pocket .rom image from a MiSTer .mra and MAME zips.

This .mra is a plain ordered concatenation of parts: no interleaving,
no fills, no patches. If a future .mra needs those, this script will
raise rather than silently produce a wrong image.
"""
import argparse
import binascii
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

UNSUPPORTED_ATTRS = ("map", "repeat", "offset", "length")


def crc32_hex(data):
    return format(binascii.crc32(data) & 0xFFFFFFFF, "08x")


def parse_mra(path):
    """Return (zip_names, [(part_name, crc_hex), ...]) for rom index 0."""
    root = ET.parse(path).getroot()
    rom = root.find("./rom[@index='0']")
    if rom is None:
        raise ValueError(f"{path}: no <rom index=\"0\"> element")

    zips = [z.strip() for z in (rom.get("zip") or "").split("|") if z.strip()]
    if not zips:
        raise ValueError(f"{path}: <rom> has no zip attribute")

    parts = []
    for part in rom.findall("part"):
        name = part.get("name")
        if name is None:
            raise ValueError(
                f"{path}: <part> without a name attribute (inline hex data "
                "is not supported)"
            )
        for attr in UNSUPPORTED_ATTRS:
            if part.get(attr) is not None:
                raise ValueError(
                    f"{path}: part {name!r} uses unsupported attribute "
                    f"{attr!r}; this script only does plain concatenation"
                )
        parts.append((name, (part.get("crc") or "").lower()))

    if not parts:
        raise ValueError(f"{path}: <rom> has no parts")
    return zips, parts


def open_archives(zips, rom_dirs):
    """Open each named zip from the first rom_dir that has it. Missing
    zips are not fatal here: a part only needs to exist in one of them."""
    archives = []
    for zip_name in zips:
        for directory in rom_dirs:
            candidate = Path(directory) / zip_name
            if candidate.is_file():
                archives.append((zip_name, zipfile.ZipFile(candidate)))
                break
    return archives


def read_part(archives, name):
    for zip_name, archive in archives:
        try:
            return archive.read(name)
        except KeyError:
            continue
    raise ValueError(
        f"part {name!r} not found in any of: "
        f"{', '.join(z for z, _ in archives) or '(no zips found)'}"
    )


def build_rom(mra_path, rom_dirs, out_path):
    zips, parts = parse_mra(mra_path)
    archives = open_archives(zips, rom_dirs)
    try:
        blob = bytearray()
        for name, expected_crc in parts:
            data = read_part(archives, name)
            actual_crc = crc32_hex(data)
            if expected_crc and actual_crc != expected_crc:
                raise ValueError(
                    f"CRC mismatch for {name!r}: .mra expects {expected_crc}, "
                    f"file is {actual_crc}"
                )
            blob += data
    finally:
        for _, archive in archives:
            archive.close()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return len(blob)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mra", required=True, type=Path)
    ap.add_argument(
        "--roms",
        required=True,
        nargs="+",
        type=Path,
        help="one or more directories containing the MAME zips",
    )
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--expect-size",
        type=lambda s: int(s, 0),
        help="fail if the output is not exactly this many bytes",
    )
    args = ap.parse_args(argv)

    try:
        written = build_rom(args.mra, args.roms, args.out)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.expect_size is not None and written != args.expect_size:
        print(
            f"error: {args.out} is {written} bytes, expected "
            f"{args.expect_size}",
            file=sys.stderr,
        )
        return 1

    print(f"wrote {args.out} ({written} bytes, 0x{written:X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
