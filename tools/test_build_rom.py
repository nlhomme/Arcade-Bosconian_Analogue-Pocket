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


def test_parse_mra_rejects_nested_parts():
    """Nested parts (e.g., <interleave><part/></interleave>) are silently skipped
    by findall("part"). Detect this discrepancy and raise ValueError."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        data_a = b"AAAA"
        with zipfile.ZipFile(tmp / "test.zip", "w") as z:
            z.writestr("a.bin", data_a)
        mra = tmp / "test.mra"
        mra.write_text(
            f"""<misterromdescription>
  <name>Test</name>
  <rom index="0" md5="none" zip="test.zip">
    <part crc="{crc32_hex(data_a)}" name="a.bin"/>
    <interleave>
      <part crc="{crc32_hex(data_a)}" name="a.bin"/>
    </interleave>
  </rom>
</misterromdescription>
"""
        )
        try:
            parse_mra(mra)
        except ValueError as exc:
            assert "nested" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError on nested parts")


def test_parse_mra_requires_crc_attribute():
    """A part with no crc attribute skips integrity checking. This is an error."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        data_a = b"AAAA"
        with zipfile.ZipFile(tmp / "test.zip", "w") as z:
            z.writestr("a.bin", data_a)
        mra = tmp / "test.mra"
        mra.write_text(
            """<misterromdescription>
  <name>Test</name>
  <rom index="0" md5="none" zip="test.zip">
    <part name="a.bin"/>
  </rom>
</misterromdescription>
"""
        )
        try:
            parse_mra(mra)
        except ValueError as exc:
            assert "crc" in str(exc).lower() and "a.bin" in str(exc)
        else:
            raise AssertionError("expected ValueError on missing crc")


def test_parse_mra_rejects_unsupported_attributes():
    """Parts with unsupported attributes (map, repeat, offset, length) raise ValueError."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        data_a = b"AAAA"
        with zipfile.ZipFile(tmp / "test.zip", "w") as z:
            z.writestr("a.bin", data_a)
        mra = tmp / "test.mra"
        mra.write_text(
            f"""<misterromdescription>
  <name>Test</name>
  <rom index="0" md5="none" zip="test.zip">
    <part crc="{crc32_hex(data_a)}" name="a.bin" repeat="2"/>
  </rom>
</misterromdescription>
"""
        )
        try:
            parse_mra(mra)
        except ValueError as exc:
            assert "repeat" in str(exc) and "a.bin" in str(exc)
        else:
            raise AssertionError("expected ValueError on unsupported attribute")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
