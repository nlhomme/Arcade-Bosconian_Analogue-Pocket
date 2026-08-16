#!/usr/bin/env python3
"""Convert a 521x165 PNG to an Analogue Pocket platform banner, and back.

Format, determined by inspecting shipping platform images:

  521 x 165 pixels, 2 bytes per pixel, 171930 bytes total.
  Low byte  = the pixel value, 0-255.
  High byte = always 0x00.

So it is an 8-bit mask, not a colour image, exactly like the core icon:
0 is transparent, 255 fully lit, which is why Pocket artwork reads as
light shapes on a dark background.

Unlike the icon, the banner is stored ROW-major - index = y * 521 + x.
That was established by measuring how similar neighbouring pixels are in
each reading: row-major scores 4.1, column-major 24.6, so the row-major
reading is the coherent image and the other is scrambled.

  make_banner.py encode art.png bosconian.bin
  make_banner.py decode bosconian.bin preview.png    # check an existing one

Stdlib only. The PNG reader and writer are shared with make_icon.py.
"""
import argparse
import sys
from pathlib import Path

from make_icon import read_png, write_png

BANNER_W = 521
BANNER_H = 165
BANNER_BYTES = BANNER_W * BANNER_H * 2


def pixel_value(px, source):
    r, g, b, a = px
    if source == "alpha":
        return a
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if source == "luma":
        return lum
    # auto: transparent pixels are background; otherwise use brightness
    return lum if a == 255 else a


def encode(png_path, out_path, source="auto", column_major=False):
    w, h, px = read_png(png_path)
    if (w, h) != (BANNER_W, BANNER_H):
        raise ValueError(
            f"{png_path}: banner must be exactly {BANNER_W}x{BANNER_H}, got {w}x{h}"
        )
    if source == "auto":
        source = "alpha" if any(p[3] != 255 for p in px) else "luma"
    buf = bytearray()
    for i in range(BANNER_W * BANNER_H):
        if column_major:
            x, y = i % BANNER_W, i // BANNER_W
            j = x * BANNER_H + y
        else:
            j = i
        buf += bytes((pixel_value(px[j], source), 0x00))
    Path(out_path).write_bytes(bytes(buf))
    return source, len(buf)


def decode(bin_path, png_path, column_major=False):
    raw = Path(bin_path).read_bytes()
    if len(raw) != BANNER_BYTES:
        raise ValueError(
            f"{bin_path}: expected {BANNER_BYTES} bytes for a "
            f"{BANNER_W}x{BANNER_H} banner, got {len(raw)}"
        )
    vals = list(raw[0::2])
    if column_major:
        vals = [
            vals[x * BANNER_H + y] for y in range(BANNER_H) for x in range(BANNER_W)
        ]
    write_png(png_path, BANNER_W, BANNER_H, vals)
    return len(set(vals))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help=f"{BANNER_W}x{BANNER_H} PNG -> banner .bin")
    e.add_argument("png", type=Path)
    e.add_argument("out", type=Path)
    e.add_argument(
        "--source",
        choices=("auto", "alpha", "luma"),
        default="auto",
        help="which channel becomes the pixel value (default: auto)",
    )
    e.add_argument(
        "--column-major",
        action="store_true",
        help="store column-major instead of the banner default",
    )

    d = sub.add_parser("decode", help="banner .bin -> PNG, to inspect an existing one")
    d.add_argument("bin", type=Path)
    d.add_argument("out", type=Path)
    d.add_argument(
        "--column-major",
        action="store_true",
        help="read as column-major instead of the banner default",
    )

    args = ap.parse_args(argv)
    try:
        if args.cmd == "encode":
            source, n = encode(args.png, args.out, args.source, args.column_major)
            print(
                f"wrote {args.out} ({n} bytes, {BANNER_W}x{BANNER_H}, from {source})"
            )
        else:
            n = decode(args.bin, args.out, args.column_major)
            print(f"wrote {args.out} ({BANNER_W}x{BANNER_H}, {n} distinct values)")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
