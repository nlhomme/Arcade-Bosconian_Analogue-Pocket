#!/usr/bin/env python3
"""Self-test for make_icon.py. Stdlib only: python3 test_make_icon.py"""
import struct
import tempfile
import zlib
from pathlib import Path

from make_icon import ICON_BYTES, ICON_H, ICON_W, decode, encode, read_png, write_png

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def write_rgba_png(path, w, h, pixels):
    """Minimal RGBA PNG writer, used only to build test inputs."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(pixels[y * w + x])

    def chunk(tag, body):
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    Path(path).write_bytes(
        PNG_SIG
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def a_test_icon():
    """A deliberately asymmetric pattern, so a transpose bug cannot hide."""
    px = []
    for y in range(ICON_H):
        for x in range(ICON_W):
            on = x < 8 and y < 20          # a tall block in one corner only
            px.append((255, 255, 255, 255) if on else (0, 0, 0, 0))
    return px


def test_encode_produces_the_exact_file_size():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "i.png", ICON_W, ICON_H, a_test_icon())
        _, n = encode(tmp / "i.png", tmp / "i.bin")
        assert n == ICON_BYTES, n
        assert (tmp / "i.bin").stat().st_size == ICON_BYTES


def test_high_byte_of_every_pixel_is_zero():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "i.png", ICON_W, ICON_H, a_test_icon())
        encode(tmp / "i.png", tmp / "i.bin")
        raw = (tmp / "i.bin").read_bytes()
        assert set(raw[1::2]) == {0}, "odd bytes must all be 0x00"


def test_round_trip_preserves_the_image_including_orientation():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        px = a_test_icon()
        write_rgba_png(tmp / "i.png", ICON_W, ICON_H, px)
        encode(tmp / "i.png", tmp / "i.bin")
        decode(tmp / "i.bin", tmp / "back.png")
        _, _, got = read_png(tmp / "back.png")
        want = [p[3] for p in px]                 # alpha was the source
        assert [g[0] for g in got] == want, "round trip changed the image"


def test_transposing_actually_changes_the_bytes():
    # guards against the orientation flag silently doing nothing
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "i.png", ICON_W, ICON_H, a_test_icon())
        encode(tmp / "i.png", tmp / "col.bin", column_major=True)
        encode(tmp / "i.png", tmp / "row.bin", column_major=False)
        assert (tmp / "col.bin").read_bytes() != (tmp / "row.bin").read_bytes()


def test_alpha_is_preferred_when_present():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # bright white but fully transparent: alpha source must give 0
        px = [(255, 255, 255, 0)] * (ICON_W * ICON_H)
        write_rgba_png(tmp / "i.png", ICON_W, ICON_H, px)
        source, _ = encode(tmp / "i.png", tmp / "i.bin")
        assert source == "alpha", source
        assert set((tmp / "i.bin").read_bytes()) == {0}


def test_wrong_size_png_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "small.png", 8, 8, [(0, 0, 0, 255)] * 64)
        try:
            encode(tmp / "small.png", tmp / "i.bin")
        except ValueError as exc:
            assert "36x36" in str(exc), exc
        else:
            raise AssertionError("expected ValueError on a wrong-size PNG")


def test_wrong_size_bin_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "bad.bin").write_bytes(b"\x00" * 100)
        try:
            decode(tmp / "bad.bin", tmp / "o.png")
        except ValueError as exc:
            assert "2592" in str(exc), exc
        else:
            raise AssertionError("expected ValueError on a wrong-size bin")


def test_non_png_input_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "nope.png").write_bytes(b"this is not a png")
        try:
            read_png(tmp / "nope.png")
        except ValueError as exc:
            assert "not a PNG" in str(exc), exc
        else:
            raise AssertionError("expected ValueError on a non-PNG file")


def test_png_writer_and_reader_agree():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        vals = [(x * 7 + y * 3) % 256 for y in range(ICON_H) for x in range(ICON_W)]
        write_png(tmp / "g.png", ICON_W, ICON_H, vals)
        w, h, px = read_png(tmp / "g.png")
        assert (w, h) == (ICON_W, ICON_H)
        assert [p[0] for p in px] == vals


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
