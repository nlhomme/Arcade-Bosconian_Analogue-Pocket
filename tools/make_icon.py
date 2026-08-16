#!/usr/bin/env python3
"""Convert a 36x36 PNG to an Analogue Pocket core icon (icon.bin), and back.

Format, determined by inspecting shipping cores' icon.bin files:

  36 x 36 pixels, 2 bytes per pixel, 2592 bytes total.
  Low byte  = the pixel value, 0-255.
  High byte = always 0x00.

So it is an 8-bit mask, not a colour image. Icons render as light artwork
on a transparent background: 0 is transparent, 255 is fully lit. Several
shipping icons contain only 0 and 255.
Pixels are stored COLUMN-major - index = x * 36 + y. That was established
by decoding shipping icons both ways: one reading is a clean symmetric
glyph, the other is incoherent. (Note the 521x165 platform banner uses the
opposite, row-major, order.) Pass --row-major if you need the other.

By default the value is taken from the PNG's alpha channel when it has
one, and from luminance otherwise - which is what you want for artwork
drawn as opaque shapes on a transparent background.

  make_icon.py encode art.png icon.bin
  make_icon.py decode icon.bin preview.png     # to check an existing icon

Stdlib only; includes a minimal PNG reader/writer.
"""
import argparse
import struct
import sys
import zlib
from pathlib import Path

ICON_W = ICON_H = 36
ICON_BYTES = ICON_W * ICON_H * 2

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------
# minimal PNG reader: 8-bit, non-interlaced, colour types 0/2/3/4/6
# --------------------------------------------------------------------------
def read_png(path):
    """Return (width, height, pixels) where pixels is a list of (r,g,b,a)."""
    data = Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        raise ValueError(f"{path}: not a PNG file")

    pos = 8
    w = h = depth = ctype = interlace = None
    idat = bytearray()
    palette = None
    trns = None
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        ctag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif ctag == b"PLTE":
            palette = [tuple(body[i : i + 3]) for i in range(0, len(body), 3)]
        elif ctag == b"tRNS":
            trns = body
        elif ctag == b"IDAT":
            idat += body
        elif ctag == b"IEND":
            break

    if depth != 8:
        raise ValueError(f"{path}: only 8-bit PNGs are supported (got {depth}-bit)")
    if interlace:
        raise ValueError(f"{path}: interlaced PNGs are not supported")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise ValueError(f"{path}: unsupported PNG colour type {ctype}")

    raw = zlib.decompress(bytes(idat))
    stride = w * channels
    out = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        f = raw[pos]
        line = bytearray(raw[pos + 1 : pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
            elif f != 0:
                raise ValueError(f"{path}: bad PNG filter {f}")
        for x in range(w):
            px = line[x * channels : (x + 1) * channels]
            if ctype == 0:
                out.append((px[0], px[0], px[0], 255))
            elif ctype == 2:
                out.append((px[0], px[1], px[2], 255))
            elif ctype == 3:
                r, g, b = palette[px[0]]
                a = trns[px[0]] if trns and px[0] < len(trns) else 255
                out.append((r, g, b, a))
            elif ctype == 4:
                out.append((px[0], px[0], px[0], px[1]))
            else:
                out.append((px[0], px[1], px[2], px[3]))
        prev = line
    return w, h, out


def write_png(path, w, h, gray):
    """Write an 8-bit greyscale PNG from a flat list of 0-255 values."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: none
        raw += bytes(gray[y * w : (y + 1) * w])

    def chunk(tag, body):
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    Path(path).write_bytes(
        PNG_SIG
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------
def pixel_value(px, source):
    r, g, b, a = px
    if source == "alpha":
        return a
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if source == "luma":
        return lum
    # auto: transparent pixels are background; otherwise use brightness
    return lum if a == 255 else a


def encode(png_path, out_path, source="auto", column_major=True):
    w, h, px = read_png(png_path)
    if (w, h) != (ICON_W, ICON_H):
        raise ValueError(
            f"{png_path}: icon must be exactly {ICON_W}x{ICON_H}, got {w}x{h}"
        )
    if source == "auto":
        source = "alpha" if any(p[3] != 255 for p in px) else "luma"
    buf = bytearray()
    for i in range(ICON_W * ICON_H):
        x, y = i % ICON_W, i // ICON_W
        j = (x * ICON_H + y) if column_major else i
        buf += bytes((pixel_value(px[j], source), 0x00))
    Path(out_path).write_bytes(bytes(buf))
    return source, len(buf)


def decode(bin_path, png_path, column_major=True):
    raw = Path(bin_path).read_bytes()
    if len(raw) != ICON_BYTES:
        raise ValueError(
            f"{bin_path}: expected {ICON_BYTES} bytes for a {ICON_W}x{ICON_H} icon, "
            f"got {len(raw)}"
        )
    vals = list(raw[0::2])
    if column_major:
        vals = [vals[x * ICON_H + y] for y in range(ICON_H) for x in range(ICON_W)]
    write_png(png_path, ICON_W, ICON_H, vals)
    return len(set(vals))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help="36x36 PNG -> icon.bin")
    e.add_argument("png", type=Path)
    e.add_argument("out", type=Path)
    e.add_argument(
        "--source",
        choices=("auto", "alpha", "luma"),
        default="auto",
        help="which channel becomes the icon value (default: auto)",
    )
    e.add_argument("--row-major", action="store_true",
                   help="store row-major instead of the icon default")

    d = sub.add_parser("decode", help="icon.bin -> PNG, to inspect an existing icon")
    d.add_argument("bin", type=Path)
    d.add_argument("out", type=Path)
    d.add_argument("--row-major", action="store_true",
                   help="read as row-major instead of the icon default")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "encode":
            source, n = encode(args.png, args.out, args.source, not args.row_major)
            print(f"wrote {args.out} ({n} bytes, {ICON_W}x{ICON_H}, from {source})")
        else:
            n = decode(args.bin, args.out, not args.row_major)
            print(f"wrote {args.out} ({ICON_W}x{ICON_H}, {n} distinct values)")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
