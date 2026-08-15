#!/usr/bin/env python3
"""Convert a Quartus .rbf into the bit-reversed .rbf_r the Pocket loads."""
import sys
from pathlib import Path

REVERSE = bytes(int(format(b, "08b")[::-1], 2) for b in range(256))


def main(argv):
    if len(argv) != 3:
        print(f"usage: {argv[0]} <in.rbf> <out.rbf_r>", file=sys.stderr)
        return 1
    src, dst = Path(argv[1]), Path(argv[2])
    data = src.read_bytes()
    dst.write_bytes(data.translate(REVERSE))
    print(f"wrote {dst} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
