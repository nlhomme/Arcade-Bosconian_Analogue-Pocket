#!/usr/bin/env python3
"""Self-test for reverse_rbf.py. Stdlib only: python3 test_reverse_rbf.py"""
import tempfile
from pathlib import Path

from reverse_rbf import MIN_RBF_SIZE, main


def test_rejects_undersized_rbf():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.rbf"
        dst = Path(d) / "out.rbf_r"
        src.write_bytes(b"\x00" * 1024)
        assert main([__file__, str(src), str(dst)]) == 1
        assert not dst.exists()


def test_accepts_full_size_rbf_and_reverses_bits():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.rbf"
        dst = Path(d) / "out.rbf_r"
        src.write_bytes(b"\x01" * MIN_RBF_SIZE)
        assert main([__file__, str(src), str(dst)]) == 0
        # 0x01 = 0b00000001 reversed is 0b10000000 = 0x80
        assert dst.read_bytes()[:1] == b"\x80"
        assert len(dst.read_bytes()) == MIN_RBF_SIZE


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
