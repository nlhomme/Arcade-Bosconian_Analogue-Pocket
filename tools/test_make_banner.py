#!/usr/bin/env python3
"""Self-test for make_banner.py. Stdlib only: python3 test_make_banner.py"""
import struct
import tempfile
import zlib
from pathlib import Path

from make_banner import BANNER_BYTES, BANNER_H, BANNER_W, decode, encode
from make_icon import read_png

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def write_rgba_png(path, w, h, pixels):
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


def a_test_banner():
    """Asymmetric: a bar along the top-left only, so a transpose cannot hide."""
    px = []
    for y in range(BANNER_H):
        for x in range(BANNER_W):
            on = x < 100 and y < 30
            px.append((255, 255, 255, 255) if on else (0, 0, 0, 0))
    return px


def test_encode_produces_the_exact_file_size():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, a_test_banner())
        _, n = encode(tmp / "b.png", tmp / "b.bin")
        assert n == BANNER_BYTES, n
        assert (tmp / "b.bin").stat().st_size == BANNER_BYTES


def test_high_byte_of_every_pixel_is_zero():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, a_test_banner())
        encode(tmp / "b.png", tmp / "b.bin")
        assert set((tmp / "b.bin").read_bytes()[1::2]) == {0}


def test_round_trip_preserves_the_image_including_orientation():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        px = a_test_banner()
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, px)
        encode(tmp / "b.png", tmp / "b.bin")
        decode(tmp / "b.bin", tmp / "back.png")
        _, _, got = read_png(tmp / "back.png")
        assert [g[0] for g in got] == [p[3] for p in px]


def test_default_is_row_major_not_column_major():
    # the banner's order is the opposite of the icon's; guard against a swap
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        px = a_test_banner()
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, px)
        encode(tmp / "b.png", tmp / "b.bin")
        vals = list((tmp / "b.bin").read_bytes()[0::2])
        # with row-major storage, index y*W+x must reproduce the source bar
        assert vals[0 * BANNER_W + 0] == 255, "top-left should be lit"
        assert vals[0 * BANNER_W + 200] == 0, "top-right should be dark"
        assert vals[100 * BANNER_W + 0] == 0, "lower-left should be dark"


def test_column_major_flag_changes_the_bytes():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, a_test_banner())
        encode(tmp / "b.png", tmp / "row.bin", column_major=False)
        encode(tmp / "b.png", tmp / "col.bin", column_major=True)
        assert (tmp / "row.bin").read_bytes() != (tmp / "col.bin").read_bytes()


def test_alpha_is_preferred_when_present():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        px = [(255, 255, 255, 0)] * (BANNER_W * BANNER_H)
        write_rgba_png(tmp / "b.png", BANNER_W, BANNER_H, px)
        source, _ = encode(tmp / "b.png", tmp / "b.bin")
        assert source == "alpha", source
        assert set((tmp / "b.bin").read_bytes()) == {0}


def test_wrong_size_png_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        write_rgba_png(tmp / "small.png", 36, 36, [(0, 0, 0, 255)] * (36 * 36))
        try:
            encode(tmp / "small.png", tmp / "b.bin")
        except ValueError as exc:
            assert "521x165" in str(exc), exc
        else:
            raise AssertionError("expected ValueError on a wrong-size PNG")


def test_wrong_size_bin_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "bad.bin").write_bytes(b"\x00" * 2592)   # an icon, not a banner
        try:
            decode(tmp / "bad.bin", tmp / "o.png")
        except ValueError as exc:
            assert "171930" in str(exc), exc
        else:
            raise AssertionError("expected ValueError on a wrong-size bin")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
