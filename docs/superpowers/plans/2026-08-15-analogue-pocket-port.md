# Analogue Pocket Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing Bosconian arcade core on the Analogue Pocket via the openFPGA framework, without modifying `rtl/` or breaking the MiSTer build.

**Architecture:** Vendor `agg23/openfpga-template` (Analogue's APF framework plus the standard MIT utility modules) into `pocket/`. A thin `core_top.v` owns the APF bridge and hands a narrow interface to `bosconian_pocket.sv`, which contains the PLL, video retiming, audio conversion, input mapping, and the `bosconian` VHDL instantiation. ROM images are built from the existing `.mra` by a standalone Python script. All gateware compilation happens in GitHub Actions because Quartus cannot run on the development machine.

**Tech Stack:** Verilog/SystemVerilog (glue), VHDL (existing core, unmodified), Quartus Prime 17.1 Lite targeting Cyclone V `5CEBA4F23C8`, Python 3 stdlib (ROM tooling), GitHub Actions with `ghcr.io/raetro/quartus:17.1`.

## Global Constraints

- Target device is **Cyclone V `5CEBA4F23C8`**, family `Cyclone V`. Never change these.
- **`rtl/` is read-only.** No task in this plan modifies any file under `rtl/`. If a change there seems necessary, stop and report it.
- **The MiSTer build must keep working.** `Arcade-Bosconian.qpf`, `Arcade-Bosconian.qsf`, `Arcade-Bosconian.sv`, `files.qip`, and `sys/` are not touched by any task.
- **Quartus cannot run locally.** The dev machine is arm64 macOS; Quartus is x86 Linux/Windows only. Every gateware change is verified by pushing to CI. Do not add steps that assume a local Quartus.
- Core identifier is **`nlhomme.Bosconian`** throughout (folder name, `core.json` author field).
- Platform id is **`bosconian`** throughout (`Platforms/bosconian.json`, `Assets/bosconian/`, `core.json` `platform_ids`).
- Expected ROM image size is exactly **58,880 bytes (0xE600)**.
- DIP power-on defaults must be **`dip_a = 0x08`, `dip_b = 0x68`**, matching the `.mra` `default="08,68"`.
- Python is **stdlib only**. No pip installs, no test framework dependencies.
- All vendored third-party files keep their original license headers intact. This repo is GPLv2; vendored APF/agg23 code is permissive and compatible.
- Commit after every task. Work on branch `analogue`.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `pocket/tools/build_rom.py` | `.mra` + MAME zips → single `.rom` image, CRC-verified |
| `pocket/tools/test_build_rom.py` | Stdlib self-test for the above |
| `pocket/tools/reverse_rbf.py` | `.rbf` → `.rbf_r` (bit-reverse each byte) |
| `pocket/src/fpga/apf/**` | Vendored, unmodified APF framework |
| `pocket/src/fpga/core/core_top.v` | Vendored, then edited: owns APF bridge, DIP registers, dataslot |
| `pocket/src/fpga/core/bosconian_pocket.sv` | Our glue: PLL, video, audio, inputs, core instantiation |
| `pocket/src/fpga/core/bosconian_rtl.qip` | Points Quartus at `../../../../rtl/*` |
| `pocket/src/fpga/core/mf_pllbase*` | Vendored PLL, frequency parameters hand-edited |
| `pocket/src/fpga/core/core_constraints.sdc` | Vendored, then edited: clock groups |
| `pocket/dist/Cores/nlhomme.Bosconian/*.json` | Pocket core definition |
| `pocket/dist/Platforms/bosconian.json` | Pocket platform definition |
| `.github/workflows/pocket-build.yml` | Quartus compile + package |

**Modified:** none outside `pocket/`, `docs/`, and `.github/`.

**Boundary that matters:** `core_top.v` is the only file that knows APF exists. `bosconian_pocket.sv` is the only file that knows Bosconian exists. Keeping this split means `core_top.v` stays diffable against the upstream template.

---

### Task 1: ROM build script

Pure Python, no FPGA toolchain, no hardware. This is the one task with a real red/green test cycle, so it goes first — it is also the task most likely to be needed while debugging everything else.

**Files:**
- Create: `pocket/tools/build_rom.py`
- Test: `pocket/tools/test_build_rom.py`

**Interfaces:**
- Consumes: `releases/Bosconian - Star Destroyer (new version).mra` (existing, unmodified)
- Produces:
  - `parse_mra(path) -> (zips: list[str], parts: list[tuple[str, str]])` — returns the zip search list and `(name, crc_hex)` pairs in document order
  - `crc32_hex(data: bytes) -> str` — lowercase, zero-padded to 8 chars
  - `build_rom(mra_path, rom_dirs, out_path) -> int` — returns bytes written, raises `ValueError` on any CRC mismatch or missing part
  - CLI: `python3 pocket/tools/build_rom.py --mra <file> --roms <dir> --out <file>`

- [ ] **Step 1: Write the failing test**

Create `pocket/tools/test_build_rom.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd pocket/tools && python3 test_build_rom.py
```

Expected: `ModuleNotFoundError: No module named 'build_rom'`

- [ ] **Step 3: Write the implementation**

Create `pocket/tools/build_rom.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd pocket/tools && python3 test_build_rom.py
```

Expected: five `ok  test_...` lines then `all passed`.

- [ ] **Step 5: Verify against the real `.mra` structurally**

The real ROM zips may not be present on this machine, so check the parsing path only:

```bash
python3 -c "
import sys; sys.path.insert(0, 'pocket/tools')
from build_rom import parse_mra
zips, parts = parse_mra('releases/Bosconian - Star Destroyer (new version).mra')
print('zips:', zips)
print('parts:', len(parts))
"
```

Expected, verified against the real file:

```
zips: ['bosco.zip', 'boscomd.zip', 'namco50.zip', 'namco51.zip', 'namco52.zip', 'namco54.zip']
parts: 19
```

If `parts` is not 19, the `.mra` was misparsed — stop and investigate before continuing. Note that `bos1_13.5e` legitimately appears twice: the `.mra` doubles it to match Galaga's ROM spacing.

- [ ] **Step 6: Commit**

```bash
git add pocket/tools/build_rom.py pocket/tools/test_build_rom.py
git commit -m "Add .mra to Pocket .rom build script

Plain ordered concatenation with per-part CRC verification. Rejects
.mra features this game does not use (map/repeat/offset/length) rather
than silently producing a wrong image."
```

---

### Task 2: Vendor the template, create the Quartus project, and get CI building it

The deliverable is a green CI run producing `bitstream.rbf_r` from the *unmodified* template. No Bosconian code yet. This proves the entire toolchain before any custom RTL exists, which matters because the toolchain is the part that cannot be debugged locally.

**Files:**
- Create: `pocket/src/fpga/**` (vendored from `agg23/openfpga-template`)
- Create: `pocket/tools/reverse_rbf.py`
- Create: `.github/workflows/pocket-build.yml`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces:
  - Quartus project at `pocket/src/fpga/ap_core.qpf`, output `pocket/src/fpga/output_files/ap_core.rbf`
  - `reverse_rbf.py` CLI: `python3 pocket/tools/reverse_rbf.py <in.rbf> <out.rbf_r>`
  - CI artifact named `bitstream` containing `bitstream.rbf_r`

- [ ] **Step 1: Vendor the template**

```bash
cd /tmp && rm -rf openfpga-template && \
  git clone --depth 1 https://github.com/agg23/openfpga-template.git && \
  cd /Users/nicolas/git/fpga/Arcade-Bosconian_MiSTer && \
  mkdir -p pocket && \
  cp -R /tmp/openfpga-template/src pocket/src && \
  rm -rf pocket/src/fpga/core/mf_pllbase_sim pocket/src/fpga/core/mf_pllbase_sim.f \
         pocket/src/fpga/core/stp1.stp
```

The `mf_pllbase_sim` tree is vendor simulation collateral for tools we do not use, and `stp1.stp` is a SignalTap capture file. Removing them keeps the vendored tree to what actually builds.

- [ ] **Step 2: Confirm the vendored tree has what we need**

```bash
ls pocket/src/fpga/core/
grep -c "module synch_3" pocket/src/fpga/apf/common.v
grep -n "DEVICE\|FAMILY\|GENERATE_RBF" pocket/src/fpga/ap_core.qsf
```

Expected: `core_top.v`, `core_bridge_cmd.v`, `data_loader.sv`, `data_unloader.sv`, `sound_i2s.sv`, `sync_fifo.sv`, `mf_pllbase*`, `core_constraints.sdc`, `pin_ddio_clk.*` are present; `synch_3` count is `1`; the qsf shows `DEVICE 5CEBA4F23C8`, `FAMILY "Cyclone V"`, `GENERATE_RBF_FILE ON`.

If `DEVICE` is anything other than `5CEBA4F23C8`, stop — the wrong template was cloned.

- [ ] **Step 3: Write the RBF reverse tool**

The Pocket loads a bitstream with the bits reversed within each byte. Create `pocket/tools/reverse_rbf.py`:

```python
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
```

- [ ] **Step 4: Self-check the reverse tool**

```bash
python3 -c "
import sys; sys.path.insert(0, 'pocket/tools')
from reverse_rbf import REVERSE
assert REVERSE[0b00000001] == 0b10000000, 'bit 0 must move to bit 7'
assert REVERSE[0b11110000] == 0b00001111
assert bytes(REVERSE).translate(REVERSE) == bytes(range(256)), 'must be an involution'
print('ok')
"
```

Expected: `ok`

- [ ] **Step 5: Write the CI workflow**

Create `.github/workflows/pocket-build.yml`:

```yaml
name: Pocket Build

on:
  push:
    branches: [analogue]
    paths-ignore: ['**.md']
  pull_request:
    branches: [analogue]
    paths-ignore: ['**.md']
  workflow_dispatch:

jobs:
  synthesis:
    runs-on: ubuntu-latest
    container: ghcr.io/raetro/quartus:17.1

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Compile
        working-directory: pocket/src/fpga
        run: quartus_sh --flow compile ap_core.qpf

      - name: Check timing closure
        working-directory: pocket/src/fpga
        run: |
          report=output_files/ap_core.sta.rpt
          test -f "$report" || { echo "no STA report produced"; exit 1; }
          if grep -qE "^; *(Setup|Hold|Recovery|Removal|Minimum Pulse Width) +; +-" "$report"; then
            echo "::error::Timing not met. Failing slack paths:"
            grep -nE "^; *(Setup|Hold|Recovery|Removal|Minimum Pulse Width) +; +-" "$report"
            exit 1
          fi
          echo "Timing met."

      - name: Reverse bitstream
        run: |
          python3 pocket/tools/reverse_rbf.py \
            pocket/src/fpga/output_files/ap_core.rbf \
            bitstream.rbf_r

      - name: Upload bitstream
        uses: actions/upload-artifact@v4
        with:
          name: bitstream
          path: bitstream.rbf_r
```

The timing check exists because `quartus_sh --flow compile` exits 0 even when timing fails. Without this step CI would go green on a bitstream that does not work, which is the worst possible failure mode given no local toolchain.

- [ ] **Step 6: Commit and push, then confirm CI is green**

```bash
git add pocket/src .github/workflows/pocket-build.yml pocket/tools/reverse_rbf.py
git commit -m "Vendor openFPGA template and add Quartus CI

Unmodified agg23/openfpga-template plus a bit-reverse tool and a
GitHub Actions workflow. The timing-check step is required because
quartus_sh exits 0 on timing failure."
git push fork analogue
gh run watch
```

Expected: the run completes green and the `bitstream` artifact is downloadable. If the container image fails to pull, try `raetro/quartus:17.1` (Docker Hub) instead of the GHCR path.

---

### Task 3: Core definition JSONs and first boot on hardware

Deliverable: `nlhomme.Bosconian` appears in the Pocket menu, launches, and shows the template's grey rectangle test pattern. This validates the JSON tree, the bitstream format, and the reverse step — all before any Bosconian logic is involved.

**Files:**
- Create: `pocket/dist/Cores/nlhomme.Bosconian/{core,data,video,audio,input,interact,variants}.json`
- Create: `pocket/dist/Platforms/bosconian.json`
- Create: `pocket/dist/Assets/bosconian/common/.gitkeep`
- Modify: `.github/workflows/pocket-build.yml` (add packaging step)

**Interfaces:**
- Consumes: `bitstream.rbf_r` from Task 2
- Produces: a release zip laid out for direct extraction to the SD card root; `data.json` slot 1 is the ROM slot consumed by Task 5; `interact.json` is replaced wholesale in Task 8

- [ ] **Step 1: Write `core.json`**

```json
{
  "core": {
    "magic": "APF_VER_1",
    "metadata": {
      "platform_ids": ["bosconian"],
      "shortname": "Bosconian",
      "description": "Namco Bosconian - Star Destroyer (1981). GPLv2.",
      "author": "nlhomme",
      "url": "https://github.com/nlhomme/Arcade-Bosconian_MiSTer",
      "version": "0.1.0",
      "date_release": "2026-08-15"
    },
    "framework": {
      "target_product": "Analogue Pocket",
      "version_required": "1.1",
      "sleep_supported": false,
      "dock": { "supported": true, "analog_output": false },
      "hardware": { "link_port": false, "cartridge_adapter": -1 }
    },
    "cores": [{ "name": "default", "id": 0, "filename": "bitstream.rbf_r" }]
  }
}
```

- [ ] **Step 2: Write the remaining JSONs**

`data.json` — one required slot for the ROM:

```json
{
  "data": {
    "magic": "APF_VER_1",
    "data_slots": [
      {
        "name": "ROM",
        "id": 1,
        "required": true,
        "parameters": 0,
        "extensions": ["rom"],
        "address": "0x00000000"
      }
    ]
  }
}
```

`video.json` — Bosconian is a **horizontal** game (`.mra` says `<rotation>horizontal</rotation>`, MiSTer hardcodes `no_rotate = 1'b1`). Do not copy Galaga's `rotation: 90`:

```json
{
  "video": {
    "magic": "APF_VER_1",
    "scaler_modes": [
      {
        "width": 288,
        "height": 224,
        "aspect_w": 4,
        "aspect_h": 3,
        "rotation": 0,
        "mirror": 0
      }
    ]
  }
}
```

`audio.json`:

```json
{ "audio": { "magic": "APF_VER_1" } }
```

`input.json` — mirrors the Galaga Pocket core's layout:

```json
{
  "input": {
    "magic": "APF_VER_1",
    "controllers": [
      {
        "type": "default",
        "mappings": [
          { "id": 0, "name": "Coin",           "key": "pad_btn_select" },
          { "id": 1, "name": "Start Player 1", "key": "pad_btn_start" },
          { "id": 2, "name": "Start Player 2", "key": "pad_trig_l" },
          { "id": 3, "name": "Fire",           "key": "pad_btn_a" },
          { "id": 4, "name": "Fire",           "key": "pad_btn_b" },
          { "id": 5, "name": "Fire",           "key": "pad_btn_x" },
          { "id": 6, "name": "Fire",           "key": "pad_btn_y" }
        ]
      }
    ]
  }
}
```

`interact.json` — placeholder until Task 8:

```json
{ "interact": { "magic": "APF_VER_1", "variables": [], "messages": [] } }
```

`variants.json`:

```json
{ "variants": { "magic": "APF_VER_1", "variant_list": [] } }
```

`pocket/dist/Platforms/bosconian.json`:

```json
{
  "platform": {
    "category": "Arcade",
    "name": "Bosconian",
    "year": 1981,
    "manufacturer": "Namco"
  }
}
```

- [ ] **Step 3: Validate every JSON parses**

```bash
find pocket/dist -name '*.json' -print0 | xargs -0 -I{} python3 -c "
import json,sys; json.load(open('{}')); print('ok  {}')
"
```

Expected: one `ok` line per file, no tracebacks. A malformed JSON here produces a core the Pocket silently refuses to list, which is very hard to diagnose on-device.

- [ ] **Step 4: Add packaging to CI**

In `.github/workflows/pocket-build.yml`, replace the `Upload bitstream` step with:

```yaml
      - name: Package core
        run: |
          mkdir -p package
          cp -R pocket/dist/* package/
          mkdir -p package/Assets/bosconian/common
          cp bitstream.rbf_r package/Cores/nlhomme.Bosconian/bitstream.rbf_r
          ( cd package && zip -r ../nlhomme.Bosconian.zip . )

      - name: Upload core package
        uses: actions/upload-artifact@v4
        with:
          name: pocket-core
          path: nlhomme.Bosconian.zip
```

- [ ] **Step 5: Commit, push, confirm CI is green**

```bash
git add pocket/dist .github/workflows/pocket-build.yml
git commit -m "Add Pocket core definition JSONs and CI packaging"
git push fork analogue
gh run watch
```

Expected: green run, `pocket-core` artifact contains `Cores/nlhomme.Bosconian/` with all seven JSONs plus `bitstream.rbf_r`, and `Platforms/bosconian.json`.

- [ ] **Step 6: Test on hardware**

Download the `pocket-core` artifact, unzip it to the SD card root, and boot the Pocket.

Expected:
- Bosconian appears in the core list
- Launching it does not error
- The screen shows a grey rectangle on black (the template's test pattern)

The core will ask for a ROM because `data.json` marks slot 1 required; the test pattern is what the template's `core_top.v` renders regardless. If the core does not appear, the JSON tree is wrong. If it appears but fails to launch, the bitstream or the reverse step is wrong.

---

### Task 4: Clocks, core instantiation, and video

Deliverable: real Bosconian video timing on the Pocket screen. Without a ROM the picture will be garbage or black, but sync must be stable and the scaler must lock to 288×224.

**Files:**
- Create: `pocket/src/fpga/core/bosconian_pocket.sv`
- Create: `pocket/src/fpga/core/bosconian_rtl.qip`
- Modify: `pocket/src/fpga/core/mf_pllbase/mf_pllbase_0002.v` (frequency parameters)
- Modify: `pocket/src/fpga/core/core_constraints.sdc` (clock groups)
- Modify: `pocket/src/fpga/core/core_top.v` (instantiate our glue, remove the test pattern)
- Modify: `pocket/src/fpga/ap_core.qsf` (add our sources)

**Interfaces:**
- Consumes: the vendored template from Task 2
- Produces:
  - `bosconian_pocket` module with these ports, relied on by Tasks 5–8:
    ```
    input  wire        clk_74a
    input  wire        reset_n
    input  wire [15:0] dn_addr
    input  wire  [7:0] dn_data
    input  wire        dn_wr
    input  wire        dn_active
    input  wire  [7:0] dip_a, dip_b
    input  wire        self_test, service
    input  wire [15:0] cont1_key, cont2_key
    output wire [23:0] video_rgb
    output wire        video_de, video_hs, video_vs, video_skip
    output wire        video_rgb_clock, video_rgb_clock_90
    output wire [15:0] audio_l, audio_r
    ```
  - Internal clocks `clk_18432` and `clk_6144`, both exported implicitly through the video clock outputs

- [ ] **Step 1: Edit the PLL frequencies**

In `pocket/src/fpga/core/mf_pllbase/mf_pllbase_0002.v`, change the output clock parameters. Leave `number_of_clocks(5)`, `fractional_vco_multiplier("true")`, and `reference_clock_frequency("74.25 MHz")` alone — changing the structure risks breaking the IP in a way that cannot be checked locally.

All five outputs must stay in one frequency family or the PLL has no solution. Set outputs 3 and 4 to duplicates rather than leaving them at 133 MHz:

| Parameter | New value | Was |
|---|---|---|
| `output_clock_frequency0` | `"18.432000 MHz"` | `"12.287999 MHz"` |
| `phase_shift0` | `"0 ps"` | `"0 ps"` |
| `output_clock_frequency1` | `"6.144000 MHz"` | `"12.287999 MHz"` |
| `phase_shift1` | `"0 ps"` | `"20345 ps"` |
| `output_clock_frequency2` | `"6.144000 MHz"` | `"133.119993 MHz"` |
| `phase_shift2` | `"40690 ps"` | `"0 ps"` |
| `output_clock_frequency3` | `"18.432000 MHz"` | `"133.119992 MHz"` |
| `phase_shift3` | `"0 ps"` | `"6573 ps"` |
| `output_clock_frequency4` | `"6.144000 MHz"` | (133 MHz) |
| `phase_shift4` | `"0 ps"` | (varies) |

Phase shift is in **picoseconds**, not degrees. 90° at 6.144 MHz is a quarter period: `(1 / 6_144_000) / 4 = 40.690104 ns` → `40690 ps`.

This resolves as VCO = 737.28 MHz (18.432 × 40, and 737.28 / 6.144 = 120 exactly), comfortably inside the Cyclone V VCO range.

- [ ] **Step 2: Point Quartus at the shared RTL**

Create `pocket/src/fpga/core/bosconian_rtl.qip`. Paths in a `.qip` resolve relative to the `.qip` file itself. This deliberately omits `rtl/pll*` (we use `mf_pllbase`), `rtl/hiscore.v`, and `rtl/pause.v` (out of scope for v1):

```tcl
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80se.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80_Reg.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80_Pack.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80_MCode.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80_ALU.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/cpu/T80.vhd

set_global_assignment -name VHDL_FILE ../../../../rtl/namco/namco_03xx/n03xx.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/namco/namco_05xx/n05xx.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/namco/namco_07xx/c07_syncgen.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/namco/namco_07xx/c07_syncgen_pack.vhd

set_global_assignment -name VHDL_FILE ../../../../rtl/luts/rom_2r.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/luts/rom_4m.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/luts/rom_6b.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/luts/rom_7h.vhd

set_global_assignment -name VHDL_FILE ../../../../rtl/mb88.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/namco_06xx.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/sound_seq.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/sound_samples.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/sound_lpf.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/rgb.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/bg_palette.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/sp_palette.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/dpram.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/sound_machine.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/gen_ram.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/bosco_video_render.vhd
set_global_assignment -name VHDL_FILE ../../../../rtl/bosconian.vhd

set_global_assignment -name SYSTEMVERILOG_FILE bosconian_pocket.sv
```

Note `sp_palette.vhd` is included here even though the MiSTer `files.qip` omits it — confirm during the first compile whether it is required. If Quartus reports it as an unused duplicate entity, remove the line.

- [ ] **Step 3: Register the qip in the project**

Append to `pocket/src/fpga/ap_core.qsf`:

```tcl
set_global_assignment -name QIP_FILE core/bosconian_rtl.qip
```

- [ ] **Step 4: Write the glue module**

Create `pocket/src/fpga/core/bosconian_pocket.sv`:

```systemverilog
//
// Bosconian glue for the Analogue Pocket.
//
// Knows nothing about APF: core_top.v owns the bridge and hands us an
// already-decoded interface. Everything here is clocks, video retiming,
// audio conversion, input mapping, and the VHDL core instantiation.
//
`default_nettype none

module bosconian_pocket (
    input wire clk_74a,
    input wire reset_n,

    // ROM stream from the APF dataslot, ioctl-compatible
    input wire [15:0] dn_addr,
    input wire  [7:0] dn_data,
    input wire        dn_wr,
    input wire        dn_active,

    // DIP switches, same polarity as the MiSTer .mra values
    input wire [7:0] dip_a,
    input wire [7:0] dip_b,
    input wire       self_test,
    input wire       service,

    input wire [15:0] cont1_key,
    input wire [15:0] cont2_key,

    output wire [23:0] video_rgb,
    output wire        video_de,
    output wire        video_hs,
    output wire        video_vs,
    output wire        video_skip,
    output wire        video_rgb_clock,
    output wire        video_rgb_clock_90,

    output wire [15:0] audio_l,
    output wire [15:0] audio_r
);

  ////////////////////////////////////////////////////////////////////////
  // Clocks
  //
  // 18.432 MHz is the authentic Namco rate; MiSTer runs this core at a
  // flat 18.000 MHz, which is about 2.3% slow.
  ////////////////////////////////////////////////////////////////////////

  wire clk_18432;
  wire clk_6144;
  wire clk_6144_90;
  wire pll_locked;

  mf_pllbase pll (
      .refclk(clk_74a),
      .rst   (1'b0),

      .outclk_0(clk_18432),
      .outclk_1(clk_6144),
      .outclk_2(clk_6144_90),
      .outclk_3(),
      .outclk_4(),

      .locked(pll_locked)
  );

  assign video_rgb_clock    = clk_6144;
  assign video_rgb_clock_90 = clk_6144_90;
  assign video_skip         = 1'b0;

  // Reset while the PLL is unlocked, while APF holds us in reset, and for
  // the whole ROM download.
  wire reset_n_s;
  synch_3 s_reset (reset_n, reset_n_s, clk_18432);

  wire pll_locked_s;
  synch_3 s_lock (pll_locked, pll_locked_s, clk_18432);

  wire dn_active_s;
  synch_3 s_dn (dn_active, dn_active_s, clk_18432);

  wire core_reset = ~reset_n_s | ~pll_locked_s | dn_active_s;

  ////////////////////////////////////////////////////////////////////////
  // Inputs
  //
  // APF cont1_key bit order:
  //   0 up, 1 down, 2 left, 3 right, 4 A, 5 B, 6 X, 7 Y,
  //   8 L1, 9 R1, 10 L2, 11 R2, 12 L3, 13 R3, 14 select, 15 start
  ////////////////////////////////////////////////////////////////////////

  wire [15:0] joy = cont1_key | cont2_key;

  wire m_up    = joy[0];
  wire m_down  = joy[1];
  wire m_left  = joy[2];
  wire m_right = joy[3];
  wire m_fire  = joy[4] | joy[5] | joy[6] | joy[7];

  wire m_coin1  = cont1_key[14];
  wire m_coin2  = cont2_key[14];
  wire m_start1 = cont1_key[15];
  wire m_start2 = cont2_key[15] | cont1_key[8];

  ////////////////////////////////////////////////////////////////////////
  // Core
  ////////////////////////////////////////////////////////////////////////

  wire [2:0] core_r, core_g;
  wire [1:0] core_b;
  wire hsync_n, vsync_n, hblank_n, vblank_n;
  wire [15:0] core_audio;

  bosconian bosconian (
      .clock_18(clk_18432),
      .reset   (core_reset),

      .dn_addr(dn_addr),
      .dn_data(dn_data),
      .dn_wr  (dn_wr),

      .video_r      (core_r),
      .video_g      (core_g),
      .video_b      (core_b),
      .video_hsync_n(hsync_n),
      .video_vsync_n(vsync_n),
      .video_hblank_n(hblank_n),
      .video_vblank_n(vblank_n),

      .audio(core_audio),

      .self_test(self_test),
      .service  (service),

      .coin1(m_coin1),
      .coin2(m_coin2),

      .start1(m_start1),
      .up1(m_up), .down1(m_down), .left1(m_left), .right1(m_right),
      .fire1(m_fire),

      .start2(m_start2),
      .up2(m_up), .down2(m_down), .left2(m_left), .right2(m_right),
      .fire2(m_fire),

      // The core inverts internally, same as the MiSTer top level.
      .dip_switch_a(~dip_a),
      .dip_switch_b(~dip_b),

      // MiSTer analog-output tweaks; meaningless on the Pocket.
      .h_offset(4'd0),
      .v_offset(4'd0),
      .pause   (1'b0)
  );

  ////////////////////////////////////////////////////////////////////////
  // Video retiming
  //
  // The core produces pixels in the 18.432 MHz domain on a 6 MHz enable.
  // clk_6144 is the same PLL VCO divided by 120 while clk_18432 is
  // divided by 40, so they are phase-locked and a single register stage
  // is sufficient. The .sdc must place them in the same clock group.
  //
  // If pixels come out sheared or doubled, the 6.144 MHz clock is
  // sampling on the wrong phase of the core's pixel enable. The core
  // exposes that enable as its `video_ce` output (unconnected here, and
  // also unconnected in the MiSTer top level) — bring it out and use it
  // to qualify this register rather than free-running.
  ////////////////////////////////////////////////////////////////////////

  reg [23:0] rgb_r;
  reg de_r, hs_r, vs_r;

  always @(posedge clk_6144) begin
    // 3:3:2 to 8:8:8 by bit replication, matching MiSTer's arcade_video.
    rgb_r <= {
      core_r, core_r, core_r[2:1],
      core_g, core_g, core_g[2:1],
      core_b, core_b, core_b, core_b
    };
    de_r <= hblank_n & vblank_n;
    hs_r <= ~hsync_n;
    vs_r <= ~vsync_n;
  end

  assign video_rgb = de_r ? rgb_r : 24'h0;
  assign video_de  = de_r;
  assign video_hs  = hs_r;
  assign video_vs  = vs_r;

  ////////////////////////////////////////////////////////////////////////
  // Audio
  //
  // The core emits UNSIGNED samples (MiSTer sets AUDIO_S = 0). I2S wants
  // signed, so flip the high bit. Getting this wrong gives a full-scale
  // DC offset and clipping, not silence.
  ////////////////////////////////////////////////////////////////////////

  wire [15:0] audio_signed = {~core_audio[15], core_audio[14:0]};

  assign audio_l = audio_signed;
  assign audio_r = audio_signed;

endmodule

`default_nettype wire
```

- [ ] **Step 5: Fix the clock groups**

In `pocket/src/fpga/core/core_constraints.sdc`, PLL outputs 0, 1, and 2 are deliberately related — we cross between them. Merge their three `-group` entries into one. Replace the file contents with:

```tcl
#
# user core constraints
#
# PLL outputs 0 (18.432 MHz), 1 (6.144 MHz) and 2 (6.144 MHz, 90 deg) are
# phase-locked off a common 737.28 MHz VCO and the video retiming register
# crosses between them on purpose. They must share a clock group, or
# TimeQuest will treat a real, timed path as asynchronous.
#
set_clock_groups -asynchronous \
 -group { bridge_spiclk } \
 -group { clk_74a } \
 -group { clk_74b } \
 -group { ic|mp1|mf_pllbase_inst|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk \
          ic|mp1|mf_pllbase_inst|altera_pll_i|general[1].gpll~PLL_OUTPUT_COUNTER|divclk \
          ic|mp1|mf_pllbase_inst|altera_pll_i|general[2].gpll~PLL_OUTPUT_COUNTER|divclk }
```

Note the instance path `ic|mp1|...` comes from the template, where the PLL is instantiated as `mp1` inside `ic`. Task 4 moves the PLL into `bosconian_pocket`, so this path changes. After the first CI compile, read the actual clock names out of `output_files/ap_core.sta.rpt` and correct the paths if Quartus reports the clock groups do not match anything.

- [ ] **Step 6: Wire the glue into `core_top.v`**

In `pocket/src/fpga/core/core_top.v`:

1. Delete the video generation block (the `localparam VID_V_BPORCH` declaration through the end of its `always @(posedge clk_core_12288 ...)` block, roughly lines 497–579) and the `assign video_*` lines above it.
2. Delete the `sound_i2s` instantiation and the `wire [15:0] audio_l = 0;` line.
3. Delete the `mf_pllbase mp1 (...)` instantiation and the `clk_core_12288` / `clk_core_12288_90deg` / `pll_core_locked` wire declarations — the PLL now lives inside `bosconian_pocket`.
4. Replace all of that with:

```verilog
  wire [15:0] audio_l;
  wire [15:0] audio_r;

  // Placeholders until Task 5 and Task 8 fill them in.
  wire [15:0] dn_addr = 0;
  wire  [7:0] dn_data = 0;
  wire        dn_wr = 0;
  wire        dn_active = 0;
  wire  [7:0] dip_a = 8'h08;
  wire  [7:0] dip_b = 8'h68;
  wire        self_test = 0;
  wire        service = 0;

  bosconian_pocket bc (
      .clk_74a(clk_74a),
      .reset_n(reset_n),

      .dn_addr  (dn_addr),
      .dn_data  (dn_data),
      .dn_wr    (dn_wr),
      .dn_active(dn_active),

      .dip_a    (dip_a),
      .dip_b    (dip_b),
      .self_test(self_test),
      .service  (service),

      .cont1_key(cont1_key),
      .cont2_key(cont2_key),

      .video_rgb         (video_rgb),
      .video_de          (video_de),
      .video_hs          (video_hs),
      .video_vs          (video_vs),
      .video_skip        (video_skip),
      .video_rgb_clock   (video_rgb_clock),
      .video_rgb_clock_90(video_rgb_clock_90),

      .audio_l(audio_l),
      .audio_r(audio_r)
  );

  sound_i2s #(
      .CHANNEL_WIDTH(16),
      .SIGNED_INPUT (1)
  ) sound_i2s (
      .clk_74a  (clk_74a),
      .clk_audio(video_rgb_clock),

      .audio_l(audio_l),
      .audio_r(audio_r),

      .audio_mclk(audio_mclk),
      .audio_lrck(audio_lrck),
      .audio_dac (audio_dac)
  );
```

5. `pll_core_locked` was feeding `status_boot_done` / `status_setup_done`. Since the PLL moved, replace those two assignments with:

```verilog
  wire status_boot_done = 1'b1;
  wire status_setup_done = 1'b1;
  wire status_running = reset_n;
```

and delete the now-unused `synch_3 s01(pll_core_locked, pll_core_locked_s, clk_74a);` line and its `pll_core_locked_s` wire.

- [ ] **Step 7: Commit, push, confirm CI is green**

```bash
git add pocket/src
git commit -m "Add Pocket glue module, PLL config, and video path

Runs the core at the authentic 18.432 MHz rather than MiSTer's 18.000.
Video retimes from the 18.432 domain into the 6.144 MHz APF video clock;
both are phase-locked off one VCO and share an SDC clock group."
git push fork analogue
gh run watch
```

Expected: green. Watch for two specific failures:
- *PLL cannot achieve requested frequencies* — the Step 1 parameter edit is wrong. Re-check that all five outputs are in the 18.432/6.144 family.
- *Clock groups do not match any clocks* — the instance path in the SDC is stale. Read the real names from `output_files/ap_core.sta.rpt` and fix.

Also read the fit summary in `output_files/ap_core.fit.rpt` and record ALM and M10K usage in the commit message of the next task. The `5CEBA4F23C8` is considerably smaller than MiSTer's Cyclone V SE, and this is the first point where a capacity problem would show up.

- [ ] **Step 8: Test on hardware**

Install the new `pocket-core` artifact and launch.

Expected: the screen is no longer a grey rectangle. With no ROM loaded the picture will be black or garbage — that is fine. What matters is that the display locks and does not roll, flicker, or drop out. A rolling or absent picture means the sync polarity or the `video_de` timing is wrong.

---

### Task 5: ROM loading

Deliverable: the game boots to attract mode. This is the milestone that proves the port works.

**Files:**
- Modify: `pocket/src/fpga/core/core_top.v`

**Interfaces:**
- Consumes: `bosconian_pocket` ports from Task 4; `data.json` slot 1 from Task 3; `build_rom.py` from Task 1
- Produces: a live `dn_addr` / `dn_data` / `dn_wr` / `dn_active` stream

- [ ] **Step 1: Replace the ROM placeholders with a real loader**

In `pocket/src/fpga/core/core_top.v`, delete the four `dn_*` placeholder wires from Task 4 Step 6 and put in their place:

```verilog
  // ROM streaming from dataslot 1.
  //
  // data_loader splits APF's 32-bit bridge writes into bytes in address
  // order, which is exactly the semantics rtl/bosconian.vhd already
  // expects from the MiSTer ioctl interface, so the core needs no change.
  wire [15:0] dn_addr;
  wire  [7:0] dn_data;
  wire        dn_wr;

  // Held high from the first dataslot write until APF says every slot is
  // complete; the core stays in reset for the whole transfer.
  reg  dn_active = 0;
  always @(posedge clk_74a) begin
    if (dataslot_requestwrite) dn_active <= 1;
    else if (dataslot_allcomplete) dn_active <= 0;
  end

  data_loader #(
      .ADDRESS_MASK_UPPER_4(4'h0),
      .ADDRESS_SIZE(16),
      .OUTPUT_WORD_SIZE(1)
  ) rom_loader (
      .clk_74a   (clk_74a),
      .clk_memory(video_rgb_clock),

      .bridge_wr          (bridge_wr),
      .bridge_endian_little(bridge_endian_little),
      .bridge_addr        (bridge_addr),
      .bridge_wr_data     (bridge_wr_data),

      .write_en  (dn_wr),
      .write_addr(dn_addr),
      .write_data(dn_data)
  );
```

`ADDRESS_SIZE(16)` matches the core's `dn_addr[15:0]`. The VHDL entity really is 16 bits wide (`dn_addr : in std_logic_vector(15 downto 0)`), which addresses 65,536 bytes and so covers the 58,880-byte image. `ADDRESS_MASK_UPPER_4(4'h0)` matches `data.json`'s slot address `0x00000000`.

**Do not "fix" this to 17 bits.** The MiSTer top level passes `ioctl_addr[16:0]` — 17 bits — into that 16-bit port, a width mismatch Quartus silently truncates. It is harmless there only because the image fits in 16 bits anyway. This plan connects 16 to 16 deliberately. Anyone comparing against `Arcade-Bosconian.sv` will see the discrepancy; it is intentional.

**Note on `clk_memory`:** `data_loader` synchronises its outputs to this clock, and the core samples `dn_wr` in the 18.432 MHz domain. Using `video_rgb_clock` (6.144 MHz) here means the write pulse is comfortably wide relative to the core clock. If ROM loading proves unreliable on hardware, this is the first thing to change — route `clk_18432` out of `bosconian_pocket` as a new output port and use it instead.

- [ ] **Step 2: Build a real ROM image**

Obtain `bosco.zip`, `namco50.zip`, `namco51.zip`, `namco52.zip`, and `namco54.zip` (MAME 0220 sets), put them in one directory, then:

```bash
python3 pocket/tools/build_rom.py \
  --mra "releases/Bosconian - Star Destroyer (new version).mra" \
  --roms ~/roms \
  --out /tmp/bosco.rom \
  --expect-size 0xE600
```

Expected: `wrote /tmp/bosco.rom (58880 bytes, 0xE600)`

A CRC error here names the offending file — that is a wrong ROM set, not a bug in the script. A size mismatch means the `.mra` part list was misread; stop and investigate before touching hardware.

- [ ] **Step 3: Commit, push, confirm CI is green**

```bash
git add pocket/src/fpga/core/core_top.v
git commit -m "Load ROM from APF dataslot 1

data_loader emits bytes in address order, matching the ioctl semantics
rtl/bosconian.vhd already implements, so the core is unchanged."
git push fork analogue
gh run watch
```

- [ ] **Step 4: Test on hardware**

Copy `bosco.rom` to `Assets/bosconian/common/bosco.rom` on the SD card, install the new core package, launch it, and select the ROM.

Expected: **the game boots to attract mode.** The Bosconian logo appears, the starfield scrolls, and demo gameplay runs.

If the screen stays black: the ROM is not reaching the core. Check that `dn_active` deasserts (a core stuck in reset shows black) and that the slot address in `data.json` is `0x00000000`.

If the picture is corrupt but present: ROM data is arriving at the wrong offsets. Verify the `.rom` is exactly 58,880 bytes.

---

### Task 6: Verify inputs

Input mapping was already written in Task 4. This task only confirms it on hardware and fixes it if wrong — there is no way to test controller mapping without the device.

**Files:**
- Modify (only if a mapping is wrong): `pocket/src/fpga/core/bosconian_pocket.sv`

**Interfaces:**
- Consumes: `input.json` from Task 3, `joy` decode from Task 4
- Produces: nothing new

- [ ] **Step 1: Test each control on hardware**

With the game booted from Task 5, check each in turn:

| Input | Expected |
|---|---|
| Select | Credit added, coin sound plays |
| Start (after 1 credit) | 1-player game begins |
| L trigger (after 2 credits) | 2-player game begins |
| D-pad, 8 directions | Ship moves, including diagonals |
| A, B, X, Y | Ship fires |

- [ ] **Step 2: Fix any wrong mapping**

If a direction is inverted or rotated, the likely cause is that Bosconian's cabinet orientation differs from the `joy` bit order. The APF bit order is fixed and documented in the Task 4 comment; adjust the `m_up` / `m_down` / `m_left` / `m_right` assignments in `bosconian_pocket.sv` to match observed behaviour.

If nothing responds at all, `cont1_key` is not reaching the core — check that `core_top.v` passes it through rather than a placeholder.

- [ ] **Step 3: Commit**

If no changes were needed, record that:

```bash
git commit --allow-empty -m "Verify Pocket control mapping on hardware

Coin, start 1P/2P, 8-way movement and fire all confirmed working."
```

Otherwise commit the corrected mapping with a message naming what was wrong.

---

### Task 7: Verify audio

The audio path was written in Task 4. Like inputs, it can only be confirmed on hardware.

**Files:**
- Modify (only if wrong): `pocket/src/fpga/core/bosconian_pocket.sv`

**Interfaces:**
- Consumes: `sound_i2s` instantiation from Task 4
- Produces: nothing new

- [ ] **Step 1: Test on hardware**

| Check | Expected |
|---|---|
| Attract mode | Background music and effects audible |
| Coin insert | Coin sound |
| Firing | Shot sound |
| Explosions | Explosion sound |
| Voice samples | "Blast off!" / "Alert! Alert!" intelligible |

The Namco 52xx voice chip is the most fragile part of this core; the upstream Readme already notes that shot and explosion sounds are imperfect. Reproducing MiSTer's *existing* imperfections is a pass. Introducing new ones is not.

- [ ] **Step 2: Diagnose by symptom**

| Symptom | Cause |
|---|---|
| Loud buzz or heavy clipping | Sign conversion wrong — check `{~core_audio[15], core_audio[14:0]}` is present and `SIGNED_INPUT(1)` is set |
| Total silence | `sound_i2s` not driving `audio_mclk`/`audio_lrck`/`audio_dac`, or `audio_l`/`audio_r` unconnected in `core_top.v` |
| Correct but distorted pitch | Core clock wrong — confirm the PLL is producing 18.432 MHz, not a fallback rate |

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "Verify Pocket audio output on hardware

Unsigned-to-signed conversion confirmed correct; music, effects and
52xx voice samples all play."
```

---

### Task 8: DIP switches

Deliverable: every DIP adjustable from the Pocket menu, with MiSTer's defaults preserved.

**Files:**
- Modify: `pocket/src/fpga/core/core_top.v`
- Modify: `pocket/dist/Cores/nlhomme.Bosconian/interact.json`

**Interfaces:**
- Consumes: `dip_a` / `dip_b` / `self_test` / `service` inputs on `bosconian_pocket` from Task 4
- Produces: bridge address map below

Each DIP field gets its own bridge address. That is more addresses than strictly necessary, but it avoids APF's read-modify-write mask semantics entirely, and it means each field can be tested in isolation on hardware — which matters because bit ordering was derived by reading the `.mra`, not from a running system.

| Address | Field | Target bits | Default |
|---|---|---|---|
| `0x10000000` | Reset (action) | — | — |
| `0x10020000` | Difficulty | `dip_a[1:0]` | 0 |
| `0x10020004` | Allow Continue | `dip_a[2]` | 0 |
| `0x10020008` | Demo Sounds | `dip_a[3]` | 1 |
| `0x1002000C` | Freeze | `dip_a[4]` | 0 |
| `0x10020010` | Cabinet | `dip_a[7]` | 0 |
| `0x10020014` | Coinage | `dip_b[2:0]` | 0 |
| `0x10020018` | Bonus | `dip_b[5:3]` | 5 |
| `0x1002001C` | Lives | `dip_b[7:6]` | 1 |
| `0x10020020` | Self-test | `self_test` | 0 |
| `0x10020024` | Service | `service` | 0 |

`dip_a[6:5]` are unused on this hardware and read as 0. These defaults reconstitute `dip_a = 0x08` and `dip_b = 0x68` exactly.

- [ ] **Step 1: Add the DIP registers to `core_top.v`**

Replace the `dip_a` / `dip_b` / `self_test` / `service` placeholder wires from Task 4 Step 6 with:

```verilog
  // DIP switches, written by interact.json variables.
  //
  // One address per field: no read-modify-write masks to get wrong, and
  // each field can be tested independently on hardware. Values are held
  // in the MiSTer .mra polarity; bosconian_pocket inverts at the core
  // boundary, matching the MiSTer top level.
  //
  // Defaults reconstitute the .mra's default="08,68".
  reg [1:0] dsw_difficulty = 2'd0;
  reg       dsw_continue   = 1'b0;
  reg       dsw_demosound  = 1'b1;
  reg       dsw_freeze     = 1'b0;
  reg       dsw_cabinet    = 1'b0;
  reg [2:0] dsw_coinage    = 3'd0;
  reg [2:0] dsw_bonus      = 3'd5;
  reg [1:0] dsw_lives      = 2'd1;
  reg       dsw_selftest   = 1'b0;
  reg       dsw_service    = 1'b0;

  reg reset_action = 0;

  always @(posedge clk_74a) begin
    reset_action <= 0;

    if (bridge_wr) begin
      case (bridge_addr)
        32'h10000000: reset_action  <= bridge_wr_data[0];
        32'h10020000: dsw_difficulty <= bridge_wr_data[1:0];
        32'h10020004: dsw_continue   <= bridge_wr_data[0];
        32'h10020008: dsw_demosound  <= bridge_wr_data[0];
        32'h1002000C: dsw_freeze     <= bridge_wr_data[0];
        32'h10020010: dsw_cabinet    <= bridge_wr_data[0];
        32'h10020014: dsw_coinage    <= bridge_wr_data[2:0];
        32'h10020018: dsw_bonus      <= bridge_wr_data[2:0];
        32'h1002001C: dsw_lives      <= bridge_wr_data[1:0];
        32'h10020020: dsw_selftest   <= bridge_wr_data[0];
        32'h10020024: dsw_service    <= bridge_wr_data[0];
        default: ;
      endcase
    end
  end

  wire [7:0] dip_a = {dsw_cabinet, 2'b00, dsw_freeze,
                      dsw_demosound, dsw_continue, dsw_difficulty};
  wire [7:0] dip_b = {dsw_lives, dsw_bonus, dsw_coinage};
  wire       self_test = dsw_selftest;
  wire       service = dsw_service;
```

- [ ] **Step 2: Feed the reset action into the core**

`bosconian_pocket` currently derives reset from `reset_n`, the PLL lock, and `dn_active`. Add the menu reset by ORing `reset_action` into the `reset_n` passed down. In the `bosconian_pocket bc (...)` instantiation, change:

```verilog
      .reset_n(reset_n),
```

to:

```verilog
      .reset_n(reset_n & ~reset_action),
```

- [ ] **Step 3: Write `interact.json`**

Replace `pocket/dist/Cores/nlhomme.Bosconian/interact.json`. The Difficulty values are **not** sequential — the `.mra` maps them `Easy→0, Medium→2, Hardest→1, Auto→3`, and that ordering must be preserved. The Bonus labels carry two readings separated by `|` because the meaning depends on the Lives setting; they are copied verbatim from the `.mra` rather than reworded, since the Pocket menu cannot express a conditional option:

```json
{
  "interact": {
    "magic": "APF_VER_1",
    "variables": [
      { "name": "Reset Core", "id": 1, "type": "action", "enabled": true,
        "address": "0x10000000", "value": 1 },

      { "name": "Easy (Rank A)", "id": 10, "type": "radio", "group": 100,
        "enabled": true, "persist": true, "address": "0x10020000",
        "defaultval": 1, "value": 0 },
      { "name": "Medium (Rank B)", "id": 11, "type": "radio", "group": 100,
        "enabled": true, "persist": true, "address": "0x10020000", "value": 2 },
      { "name": "Hardest (Rank C)", "id": 12, "type": "radio", "group": 100,
        "enabled": true, "persist": true, "address": "0x10020000", "value": 1 },
      { "name": "Auto", "id": 13, "type": "radio", "group": 100,
        "enabled": true, "persist": true, "address": "0x10020000", "value": 3 },

      { "name": "5 Lives", "id": 20, "type": "radio", "group": 101,
        "enabled": true, "persist": true, "address": "0x1002001C", "value": 0 },
      { "name": "3 Lives", "id": 21, "type": "radio", "group": 101,
        "enabled": true, "persist": true, "address": "0x1002001C",
        "defaultval": 1, "value": 1 },
      { "name": "2 Lives", "id": 22, "type": "radio", "group": 101,
        "enabled": true, "persist": true, "address": "0x1002001C", "value": 2 },
      { "name": "1 Life", "id": 23, "type": "radio", "group": 101,
        "enabled": true, "persist": true, "address": "0x1002001C", "value": 3 },

      { "name": "1 Coin 1 Credit", "id": 30, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014",
        "defaultval": 1, "value": 0 },
      { "name": "1 Coin 2 Credits", "id": 31, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 1 },
      { "name": "1 Coin 3 Credits", "id": 32, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 2 },
      { "name": "2 Coins 3 Credits", "id": 33, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 3 },
      { "name": "2 Coins 1 Credit", "id": 34, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 4 },
      { "name": "3 Coins 1 Credit", "id": 35, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 5 },
      { "name": "4 Coins 1 Credit", "id": 36, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 6 },
      { "name": "Free Play", "id": 37, "type": "radio", "group": 102,
        "enabled": true, "persist": true, "address": "0x10020014", "value": 7 },

      { "name": "Bonus 20/70 | 30/120/120", "id": 40, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 0 },
      { "name": "Bonus 15/50 | 30/100/100", "id": 41, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 1 },
      { "name": "Bonus 30/100/100 | 30/80/80", "id": 42, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 2 },
      { "name": "Bonus 20/70/70 | 30/120", "id": 43, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 3 },
      { "name": "Bonus 15/70/70 | 20/100", "id": 44, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 4 },
      { "name": "Bonus 15/50/50 | 20/70", "id": 45, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "defaultval": 1, "value": 5 },
      { "name": "Bonus 10/50/50 | 15/70", "id": 46, "type": "radio",
        "group": 103, "enabled": true, "persist": true,
        "address": "0x10020018", "value": 6 },
      { "name": "Bonus Nothing", "id": 47, "type": "radio", "group": 103,
        "enabled": true, "persist": true, "address": "0x10020018", "value": 7 },

      { "name": "Allow Continue", "id": 50, "type": "check", "enabled": true,
        "persist": true, "address": "0x10020004", "defaultval": 0, "value": 1 },
      { "name": "Demo Sounds", "id": 51, "type": "check", "enabled": true,
        "persist": true, "address": "0x10020008", "defaultval": 1, "value": 1 },
      { "name": "Freeze", "id": 52, "type": "check", "enabled": true,
        "persist": true, "address": "0x1002000C", "defaultval": 0, "value": 1 },
      { "name": "Cocktail Cabinet", "id": 53, "type": "check", "enabled": true,
        "persist": true, "address": "0x10020010", "defaultval": 0, "value": 1 },
      { "name": "Self-Test Mode", "id": 54, "type": "check", "enabled": true,
        "address": "0x10020020", "defaultval": 0, "value": 1 },
      { "name": "Service Trigger", "id": 55, "type": "check", "enabled": true,
        "address": "0x10020024", "defaultval": 0, "value": 1 }
    ],
    "messages": []
  }
}
```

- [ ] **Step 4: Validate the JSON**

```bash
python3 -c "
import json
d = json.load(open('pocket/dist/Cores/nlhomme.Bosconian/interact.json'))
v = d['interact']['variables']
ids = [x['id'] for x in v]
assert len(ids) == len(set(ids)), f'duplicate ids: {ids}'
for g in (100, 101, 102, 103):
    members = [x for x in v if x.get('group') == g]
    defaults = [x for x in members if x.get('defaultval')]
    assert len(defaults) == 1, f'group {g} has {len(defaults)} defaults, want 1'
print(f'ok  {len(v)} variables, ids unique, one default per radio group')
"
```

Expected: `ok  31 variables, ids unique, one default per radio group`

- [ ] **Step 5: Commit, push, confirm CI is green**

```bash
git add pocket/src/fpga/core/core_top.v pocket/dist/Cores/nlhomme.Bosconian/interact.json
git commit -m "Add DIP switches to the Pocket menu

One bridge address per field rather than masked read-modify-write, so
each can be verified independently on hardware. Defaults reconstitute
the .mra's 08,68."
git push fork analogue
gh run watch
```

- [ ] **Step 6: Test on hardware**

This is the step that validates bit ordering derived from reading the `.mra`. Test each group by observing an actual behaviour change, not just that the menu accepts the setting:

| Setting | How to confirm |
|---|---|
| Lives | Start a game, count ships in the status area |
| Coinage | Set 2 Coins 1 Credit, insert coins, watch the credit counter |
| Free Play | Start with no coins inserted |
| Difficulty | Enter self-test; rank is displayed |
| Demo Sounds | Toggle off, confirm attract mode is silent |
| Allow Continue | Die out, check whether a continue is offered |
| Cocktail Cabinet | Player 2's view flips in a 2-player game |
| Self-Test Mode | Test screen appears instead of the game |

If a group produces the wrong effect, its bits are misplaced. Fix the `dip_a` / `dip_b` concatenation in `core_top.v` — not `interact.json`, and never `rtl/`.

---

### Task 9: Release packaging and documentation

Deliverable: a tagged release someone else can install, and instructions they can follow.

**Files:**
- Create: `pocket/README.md`
- Modify: `.github/workflows/pocket-build.yml`
- Modify: `Readme.md`

**Interfaces:**
- Consumes: the CI packaging step from Task 3
- Produces: a GitHub release attaching `nlhomme.Bosconian.zip`

- [ ] **Step 1: Add a release job to CI**

Append to `.github/workflows/pocket-build.yml`:

```yaml
  release:
    needs: synthesis
    if: startsWith(github.ref, 'refs/tags/')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Download core package
        uses: actions/download-artifact@v4
        with:
          name: pocket-core

      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          files: nlhomme.Bosconian.zip
          body: |
            Analogue Pocket core for Bosconian - Star Destroyer.

            Extract the zip to the root of your SD card, then build a
            ROM image and place it at
            `Assets/bosconian/common/bosco.rom`.
            See `pocket/README.md` for ROM build instructions.
```

Also add tags to the workflow trigger:

```yaml
on:
  push:
    branches: [analogue]
    tags: ['v*']
    paths-ignore: ['**.md']
```

- [ ] **Step 2: Write `pocket/README.md`**

```markdown
# Bosconian for Analogue Pocket

An openFPGA port of the Bosconian core. The game logic is the same VHDL
used by the MiSTer core in this repository; only the framework around it
differs.

## Install

1. Download `nlhomme.Bosconian.zip` from the releases page.
2. Extract it to the root of your Pocket's SD card. It adds
   `Cores/nlhomme.Bosconian/`, `Platforms/bosconian.json`, and an empty
   `Assets/bosconian/common/`.
3. Build a ROM image (below) and place it at
   `Assets/bosconian/common/bosco.rom`.

## Building the ROM

ROMs are not distributed. You need these MAME sets: `bosco.zip`,
`namco50.zip`, `namco51.zip`, `namco52.zip`, `namco54.zip`.

Put them in one directory and run:

    python3 pocket/tools/build_rom.py \
      --mra "releases/Bosconian - Star Destroyer (new version).mra" \
      --roms /path/to/your/roms \
      --out bosco.rom \
      --expect-size 0xE600

Every part is CRC-checked against the `.mra`, so a wrong or corrupt ROM
set fails here with the offending filename rather than producing a black
screen on the device.

## Controls

| Pocket | Function |
|---|---|
| D-pad | Move (8 directions) |
| A / B / X / Y | Fire |
| Select | Insert coin |
| Start | Start 1 player |
| L trigger | Start 2 players |

## Options

All DIP switches are in the Pocket's core options menu: difficulty,
coinage, bonus, lives, cabinet type, demo sounds, allow continue, plus
self-test and service.

Bonus values show two readings separated by `|` because the meaning
depends on the Lives setting — this is how the original hardware
behaves, not a labelling mistake.

## Not implemented

- **Pause.** The MiSTer core's pause can crash the game at certain
  moments, so it was not carried over.
- **High score saving.** Broken upstream and left out rather than
  shipped broken.
- **Alternate ROM versions.** Only the Namco "new version" set is
  supported so far.

## Building the gateware

Compilation happens in GitHub Actions using Quartus 17.1 — see
`.github/workflows/pocket-build.yml`. Push to `analogue` and download
the `pocket-core` artifact. Tag with `v*` to cut a release.

## Licence

GPLv2, inherited from the MiSTer core. The vendored openFPGA framework
files under `pocket/src/fpga/apf/` and the utility modules retain their
original permissive licences.
```

- [ ] **Step 3: Link it from the main Readme**

Add to `Readme.md`, immediately after the intro paragraph:

```markdown
An Analogue Pocket port of this core is available — see
[`pocket/README.md`](pocket/README.md).
```

- [ ] **Step 4: Verify the docs are accurate**

Re-read `pocket/README.md` against what was actually built. Specifically confirm the `build_rom.py` command line matches the real argument names, the control table matches `input.json`, and the "not implemented" list matches reality. Documentation that drifts from the build is worse than none, because it sends people looking for bugs that are actually missing features.

- [ ] **Step 5: Commit and tag**

```bash
git add pocket/README.md Readme.md .github/workflows/pocket-build.yml
git commit -m "Add Pocket readme and release workflow"
git push fork analogue
git tag v0.1.0-pocket && git push fork v0.1.0-pocket
gh run watch
```

Expected: the release job runs and `nlhomme.Bosconian.zip` is attached to the release.

- [ ] **Step 6: Final end-to-end check**

Note: no `icon.bin` or `Platforms/_images/bosconian.bin` is produced. Both are optional in APF — the Pocket falls back to a default icon and a plain platform banner. Adding them is a pure art task with no code dependency and can happen any time after this.


Install from the published release onto a clean SD card exactly as the readme instructs, then run the full checklist: boots to attract mode, starfield scrolls, sprites and radar render, voice samples play, coin/start/fire respond, DIP changes take effect, self-test passes.

---

## Risks and open questions

**Device capacity.** The Pocket's `5CEBA4F23C8` (~18,480 ALMs) is considerably smaller than MiSTer's Cyclone V SE. Galaga — the same hardware lineage — already fits on the Pocket, so this should be fine, but Task 4's fit report is the first real evidence. If it does not fit, the fallback is dropping `rtl/sound_samples.vhd` speech ROM storage into a smaller representation, which would be a design change requiring a new brainstorming pass.

**PLL fallback.** If 18.432 MHz cannot close, fall back to 18.0 / 6.0 MHz. This reproduces MiSTer's existing behaviour (about 2.3% slow) and is known-good.

**SDC instance paths.** The vendored `core_constraints.sdc` names the PLL as `ic|mp1|...`. Task 4 relocates the PLL into `bosconian_pocket`, so those paths change. The first CI compile after Task 4 will show the real names in `output_files/ap_core.sta.rpt`.

**`data_loader` clock choice.** Task 5 clocks it from the 6.144 MHz video clock. If ROM loading is unreliable, route the 18.432 MHz clock out of `bosconian_pocket` and use that instead.

**`sp_palette.vhd`.** Present in `rtl/` but absent from the MiSTer `files.qip`. Included in `bosconian_rtl.qip` on the assumption it is needed; remove the line if Quartus reports it as unused or duplicate.

**Pixel phase alignment.** The video retiming register free-runs at 6.144 MHz rather than being qualified by the core's `video_ce` output. This is correct only if the two clocks land on the intended phase. Task 4 Step 8 catches a gross failure (no stable picture); sheared or doubled pixels are the subtler symptom, and the fix is documented inline in `bosconian_pocket.sv`.

**DIP bit ordering.** Derived by reading the `.mra`, never observed running. Task 8 Step 6 is the only thing that validates it.

**Debug cycle cost.** Every gateware change is a CI build plus a manual SD card round trip. Task ordering front-loads the toolchain (Tasks 2–3) so that when Bosconian code finally lands, a failure is unambiguously in that code.
