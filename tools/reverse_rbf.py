#!/usr/bin/env python3
"""Convert a Quartus .rbf into the bit-reversed .rbf_r the Pocket loads."""
import sys
from pathlib import Path

REVERSE = bytes(int(format(b, "08b")[::-1], 2) for b in range(256))

# A real Cyclone V 5CEBA4F23C8 .rbf for this design is ~790 KB. Anything
# under this is a truncated or empty file -- catch it here rather than
# packaging and shipping a broken bitstream.
MIN_RBF_SIZE = 100_000


def main(argv):
    if len(argv) != 3:
        print(f"usage: {argv[0]} <in.rbf> <out.rbf_r>", file=sys.stderr)
        return 1
    src, dst = Path(argv[1]), Path(argv[2])
    data = src.read_bytes()
    if len(data) < MIN_RBF_SIZE:
        print(
            f"error: {src} is {len(data)} bytes, expected at least "
            f"{MIN_RBF_SIZE} for a real Cyclone V bitstream -- refusing "
            "to package a truncated or empty .rbf",
            file=sys.stderr,
        )
        return 1
    dst.write_bytes(data.translate(REVERSE))
    print(f"wrote {dst} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
