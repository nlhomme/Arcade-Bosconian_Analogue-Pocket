#!/usr/bin/env python3
"""Self-test for build_rom.py. Stdlib only: python3 test_build_rom.py"""
import binascii
import tempfile
import zipfile
from pathlib import Path

from build_rom import build_rom, crc32_hex, parse_mra

MRA_TEMPLATE = """<misterromdescription>
  <name>Test</name>
  <rom index="0" md5="none" zip="first.zip|second.zip">
    <part crc="{crc_a}" name="a.bin"/>
    <part crc="{crc_b}" name="b.bin"/>
    <part crc="{crc_a}" name="a.bin"/>
  </rom>
</misterromdescription>
"""


def make_fixture(tmp, crc_b_override=None):
    """Build a synthetic .mra plus two zips. Part 'a' appears twice, and
    lives in the second zip, so this exercises both repetition and the
    zip search order."""
    data_a = b"AAAA"
    data_b = b"BBBBBBBB"

    with zipfile.ZipFile(tmp / "first.zip", "w") as z:
        z.writestr("b.bin", data_b)
    with zipfile.ZipFile(tmp / "second.zip", "w") as z:
        z.writestr("a.bin", data_a)

    mra = tmp / "test.mra"
    mra.write_text(
        MRA_TEMPLATE.format(
            crc_a=crc32_hex(data_a),
            crc_b=crc_b_override or crc32_hex(data_b),
        )
    )
    return mra, data_a, data_b


def test_crc32_hex_is_padded_lowercase():
    assert crc32_hex(b"") == "00000000"
    assert crc32_hex(b"AAAA") == format(binascii.crc32(b"AAAA") & 0xFFFFFFFF, "08x")


def test_parse_mra_reads_zips_and_parts_in_order():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        mra, _, _ = make_fixture(tmp)
        zips, parts = parse_mra(mra)
        assert zips == ["first.zip", "second.zip"]
        assert [name for name, _ in parts] == ["a.bin", "b.bin", "a.bin"]


def test_build_rom_concatenates_in_document_order():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        mra, data_a, data_b = make_fixture(tmp)
        out = tmp / "out.rom"
        written = build_rom(mra, [tmp], out)
        assert written == len(data_a) * 2 + len(data_b)
        assert out.read_bytes() == data_a + data_b + data_a


def test_build_rom_rejects_bad_crc():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        mra, _, _ = make_fixture(tmp, crc_b_override="deadbeef")
        try:
            build_rom(mra, [tmp], tmp / "out.rom")
        except ValueError as exc:
            assert "b.bin" in str(exc)
        else:
            raise AssertionError("expected ValueError on CRC mismatch")


def test_build_rom_reports_missing_part():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        mra, _, _ = make_fixture(tmp)
        (tmp / "second.zip").unlink()
        try:
            build_rom(mra, [tmp], tmp / "out.rom")
        except ValueError as exc:
            assert "a.bin" in str(exc)
        else:
            raise AssertionError("expected ValueError on missing part")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
