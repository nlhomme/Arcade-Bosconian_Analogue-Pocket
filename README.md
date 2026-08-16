# Bosconian for Analogue Pocket

An openFPGA implementation of the arcade game Bosconian - Star Destroyer,
developed in 1981 by Namco and released to Western audiences by Midway.

The game logic in `rtl/` is the VHDL core originally written for MiSTer,
carried over unchanged; everything under `src/` is the openFPGA framework
around it.

The port itself — the framework glue, the ROM tooling, the CI pipeline
and this documentation — was written with
[Claude Code](https://claude.com/claude-code).

**Status: working on real hardware.** Confirmed booting and playing on an
actual Analogue Pocket, with the game's own self-test reporting
**RAM OK / ROM OK** and the options menu holding state correctly.

Some checks in [`HARDWARE-CHECKLIST.md`](HARDWARE-CHECKLIST.md) remain
outstanding: confirming each DIP switch maps to the right setting,
repeated power cycles to see whether sprite-to-background alignment is
stable, and menu reset reliability. None is known to be wrong; they are
simply unverified.

## About the game

Bosconian is a top-down 8-directional shooter. The goal is to destroy all
enemy bases in each level while fighting off enemy ships.

It is the first top-down shooter that allowed diagonal movement, and one
of the earliest arcade games with recorded voice samples — Pole Position
came later in 1982, and Sinistar in 1983.

## Install

1. Download `nlhomme.Bosconian.zip` from the
   [releases page](https://github.com/nlhomme/Arcade-Bosconian_Analogue-Pocket/releases).
2. Extract it to the root of your Pocket's SD card. It adds
   `Cores/nlhomme.Bosconian/`, `Platforms/bosconian.json`, and an empty
   `Assets/bosconian/common/`.
3. Build a ROM image (below) and put it at
   `Assets/bosconian/common/bosco.rom`. The core loads that filename
   automatically, so there is nothing to pick once it is in place.

### A note on updater tools

Tools like [pupdate](https://github.com/mattpannella/pupdate) install many
cores' ROMs for you, by downloading them from the `openFPGA-Files`
archive. **They cannot do that for this core** — it is not published in
that archive, so there is nothing for them to fetch. Build the ROM
yourself as described below; it is one command.

This only affects the ROM. Nothing prevents an updater from installing or
updating the core itself.

## Building the ROM

The core needs a single file, `bosco.rom` (58,880 bytes). It is not
distributed here — you assemble it from MAME ROM sets you already own,
using a script in this repository.

### What you need

**1. Python 3.** Already installed on macOS and Linux. On Windows, get it
from [python.org](https://www.python.org/downloads/) and tick *"Add
Python to PATH"* during install.

**2. This repository.** The script and the ROM layout file both live
here, and neither is inside the core zip.

- On the [repository page](https://github.com/nlhomme/Arcade-Bosconian_Analogue-Pocket),
  click **Code → Download ZIP**, then unzip it.
- Or, if you use git: `git clone https://github.com/nlhomme/Arcade-Bosconian_Analogue-Pocket.git`

**3. Five MAME ROM sets**, all in one folder:

| File | Contains |
|---|---|
| `bosco.zip` | the main game |
| `namco50.zip` | Namco 50xx custom chip |
| `namco51.zip` | Namco 51xx custom chip |
| `namco52.zip` | Namco 52xx voice chip |
| `namco54.zip` | Namco 54xx sound chip |

All five are required. The four `namco*.zip` sets are separate downloads
from `bosco.zip` — missing them is the most common failure.

Keep them zipped. Do not extract them.

### Build it

Open a terminal, move into the folder you unzipped or cloned, and run the
command below — replacing `~/Downloads` with the folder holding your five
zips:

```
cd Arcade-Bosconian_Analogue-Pocket

python3 tools/build_rom.py \
  --mra "releases/Bosconian - Star Destroyer (new version).mra" \
  --roms ~/Downloads \
  --out bosco.rom
```

On Windows, use `py` instead of `python3`, and put it on one line:

```
py tools\build_rom.py --mra "releases\Bosconian - Star Destroyer (new version).mra" --roms C:\Users\you\Downloads --out bosco.rom
```

Success looks like exactly this:

```
wrote bosco.rom (58880 bytes, 0xE600)
```

Any other output is a failure — the file is only written when every piece
checks out.

### Install it

Copy the `bosco.rom` you just built to your Pocket's SD card at:

```
Assets/bosconian/common/bosco.rom
```

Create the folders if they are not there. The core loads that exact
filename from that exact folder, so the game starts as soon as it is in
place — there is nothing to select.

### If it fails

Every piece of the ROM is checked against a CRC recorded in the `.mra`
file, so a wrong or corrupt set fails here, naming the file at fault,
instead of producing a black screen on the device.

| Message | Cause |
|---|---|
| `part '50xx.bin' not found` | Missing `namco50.zip` (likewise 51/52/54) |
| `part 'bos3_1.3n' not found` | Missing `bosco.zip`, or you extracted it |
| `CRC mismatch for ...` | That file is corrupt, or from a different ROM set |
| `.mra file not found` | You are not in the repository folder — `cd` into it first |
| `not a directory` | `--roms` needs the *folder*, not a `.zip` file |
| `python3: command not found` | Try `python` or `py` |

`python3 tools/build_rom.py -h` prints a worked example with these same
paths.

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
allow continue, demo sounds, freeze, cabinet type, coinage, bonus,
lives, self-test, and service.

Bonus values show two readings separated by `|` (e.g. "Bonus 20/70 |
30/120/120") because the meaning depends on the Lives setting — this is
how the original hardware behaves, not a labelling mistake.

## Not implemented

- **Pause.** The MiSTer core's pause handling can crash the game at
  certain moments, so it was not carried over to this port.
- **High score saving.** It is broken in the upstream MiSTer core
  (commented out and marked broken by its author), so it was left out
  here rather than shipped broken.
- **Alternate ROM versions.** Only the Namco "new version" set is
  supported so far.

## Timing

This core runs the game logic at 18.432 MHz, the clock rate the
original Namco hardware used. The MiSTer core this port derives
from runs at a flat 18.000 MHz, about 2.3% slow, for PLL simplicity — this port
is more accurate to the original hardware in that respect.

## Building the gateware

Compilation happens in GitHub Actions using the raetro `pocket` Quartus
image (`ghcr.io/raetro/quartus:pocket`) — see
`.github/workflows/pocket-build.yml`. The vendored `ap_core.qsf` was
generated by Quartus 18.1.1, not the older Quartus 17.1 toolchain used
elsewhere in openFPGA documentation. Push to `main` and download
the `pocket-core` artifact. Tag with `v*` to cut a release.

## Artwork

The core currently ships with no artwork, so it shows as a plain entry
both on the Pocket and in the cores inventory. Three images are involved,
in two different places.

### On the cores inventory website

The [inventory](https://openfpga-library.github.io/analogue-pocket/)
serves these from its own repository, not from here. They are added by
opening a pull request against
[openfpga-library/analogue-pocket](https://github.com/openfpga-library/analogue-pocket):

| Path in that repo | Size | Shown as |
|---|---|---|
| `assets/images/platforms/bosconian.png` | 521 × 165 | the card image |
| `assets/images/authors/nlhomme.Bosconian.png` | 36 × 36 | the small core icon |

Plain PNGs. Until they exist the site falls back to nothing, which is why
the entry looks bare.

### On the Pocket itself

These ship inside the core zip and are a Pocket-specific binary format,
**not** PNG:

| Path in `dist/` | Size | Shown as |
|---|---|---|
| `Platforms/_images/bosconian.bin` | 521 × 165, 171,930 bytes | platform banner |
| `Cores/nlhomme.Bosconian/icon.bin` | 36 × 36, 2,592 bytes | core icon |

Both are 2 bytes per pixel. The encoding is not plain RGB565 — a sample
of shipping images decodes to a mostly-transparent mask with very few
distinct values — so convert artwork with
[agg23/Analogue-Pocket-Image-Process](https://github.com/agg23/Analogue-Pocket-Image-Process)
rather than rolling your own.

Drop the converted files at those paths under `dist/` and they are
packaged into the release automatically; the build copies all of `dist/`.

## Credits

The game core is the work of the MiSTer Bosconian project; this
repository adds the Analogue Pocket framework around it.

* **Nolan Nicholson** — FPGA implementation of the overall Bosconian
  system from the Midway service schematics, particularly the video board
* **Dar** — FPGA implementation of Galaga, from which much of this core
  was adapted, particularly the logic board
* **Wolfgang Scherr** — several LUTs and Namco customs, including the
  05xx starfield generator, plus a hint to the operation of the 52xx
  voice chip
* **Mike Johnson** — several Namco customs including the 07xx sync
  generator, plus a lot of legwork originally done for FPGAArcade
* **Daniel Wallner** — T80/T80se, a Z80-compatible CPU
* **MAME** — memory mapping, Namco customs, and general information
* **Adam Gastineau (agg23)** — the openFPGA template and utility modules
  this port is built on
* **Analogue** — the Pocket Framework (APF)

The openFPGA port was developed with [Claude Code](https://claude.com/claude-code):
the glue in `src/fpga/core/`, the `tools/` scripts and their tests, the
GitHub Actions build, and the documentation. The game core in `rtl/` is
untouched upstream work by the people listed above.

## Licence

GPLv2, inherited from the MiSTer core, covers this port's own sources
(`src/fpga/core/bosconian_pocket.sv`, `src/fpga/core/core_top.v`) and the
game core in `rtl/`.

Vendored third-party files keep their original headers and are
governed by them:

- Analogue's Pocket Framework licence agreement — `src/fpga/apf/apf_top.v`,
  `src/fpga/apf/common.v`, `src/fpga/apf/io_bridge_peripheral.v`, `src/fpga/apf/io_pad_controller.v`
- Intel / Altera IP licences (Quartus megafunction output) —
  `src/fpga/apf/mf_datatable.v`, `src/fpga/apf/mf_ddio_bidir_12.v`, `src/fpga/apf/build_id_gen.tcl`,
  `src/fpga/core/mf_pllbase.v`, `src/fpga/core/mf_pllbase.bsf`, `src/fpga/core/pin_ddio_clk.v`
- MIT — `src/fpga/core/data_loader.sv`, `src/fpga/core/data_unloader.sv`,
  `src/fpga/core/sound_i2s.sv`, `src/fpga/core/sync_fifo.sv`

`src/fpga/core/core_bridge_cmd.v` carries only a bare "2022 Analogue" year/name
comment with no licence grant; its terms are unclear and it is not
claimed under any licence above.

Consult each file's own header for the governing terms.
