# Analogue Pocket port — design

Date: 2026-08-15
Branch: `analogue`
Status: approved, ready for implementation planning

## Goal

Run the existing Bosconian core on the Analogue Pocket, using the openFPGA
framework (APF), without changing `rtl/` or breaking the MiSTer build.

The game logic is already done and works. This port is glue: replace the MiSTer
`sys/` framework with APF, and replace `.mra` ROM assembly with a build script.

## Scope

In scope for v1:

- Boots and plays from a ROM loaded off the Pocket SD card.
- DIP switches adjustable from the Pocket's own menu.
- A build path that produces a Pocket core zip without a local FPGA toolchain.

Out of scope for v1, deliberately:

- **Pause.** Upstream `rtl/pause.v` works, but the Readme records that pausing at
  certain moments crashes the game. Porting it ports the bug.
- **Hiscore save.** Upstream has it commented out and marked broken ("scores are
  not written to RAM after a reset, reason as yet unknown"). Shipping it means
  debugging it first.
- **Multiple ROM variants.** The repo has one `.mra`. Others can be added later
  without design changes — the build script takes an `.mra` as input.
- **MiSTer-only video options.** Scandoubler FX, aspect-ratio select, and H/V
  sync adjust have no meaning on the Pocket's digital display.
- **`Flip Screen`.** Declared in the MiSTer `CONF_STR` but never wired to
  anything upstream. It is dead config, not a feature.

## Repo layout

`rtl/`, `sys/`, and the MiSTer project files are untouched. The Pocket port is a
sibling subtree with its own Quartus project reading the same `rtl/`.

```
Arcade-Bosconian_MiSTer/            (branch: analogue)
├── rtl/                            unchanged, shared source of truth
├── sys/  Arcade-Bosconian.sv/.qsf  unchanged, MiSTer build still works
├── docs/superpowers/specs/         this document
└── pocket/
    ├── src/fpga/                   vendored from agg23/openfpga-template
    │   ├── ap_core.qpf/.qsf
    │   ├── apf/                    APF framework, unmodified (incl. synch_3)
    │   └── core/
    │       ├── core_top.v          APF top level; owns the bridge
    │       ├── bosconian_pocket.sv our glue — the `emu` equivalent
    │       ├── bosconian_rtl.qip   points Quartus at ../../../../rtl/*
    │       ├── mf_pllbase*         fractional-N PLL from clk_74a
    │       ├── data_loader.sv      dataslot → dn_* stream
    │       ├── sound_i2s.sv        16-bit → I2S
    │       └── sync_fifo.sv        used by sound_i2s
    ├── dist/                       mirrors the SD card tree
    │   ├── Cores/nlhomme.Bosconian/*.json
    │   ├── Platforms/bosconian.json
    │   └── Assets/bosconian/common/
    └── tools/
        ├── build_rom.py            .mra + MAME zips → .rom
        └── reverse_rbf.py          .rbf → .rbf_r
```

The template's own `src/fpga/` layout is kept rather than reorganised: it
matches every other openFPGA core, and reorganising it would break the qsf's
relative paths for no benefit.

## Architecture

Two modules, one boundary.

`core_top.v` is a thin, diffable edit of Analogue's template. It owns everything
APF-specific: the bridge, dataslot handshaking, interact-variable writes, and the
Pocket's video/audio/controller pins. It exposes a narrow interface to the glue
module and nothing else.

`bosconian_pocket.sv` is the MiSTer `emu` equivalent: PLL, reset, video
retiming, audio conversion, input mapping, and the `bosconian` instantiation. It
knows nothing about APF.

The point of the split is that `core_top.v` stays close enough to the upstream
template to re-sync against it, and the glue stays readable without APF context.

### Interface between them

```
core_top → bosconian_pocket:
    clk_74a
    dn_addr[15:0], dn_data[7:0], dn_wr    ROM stream
    dn_active                             held true for whole download
    dip_a[7:0], dip_b[7:0]                DIP registers
    self_test, service
    reset_req                             menu Reset action
    cont1_key[15:0], cont2_key[15:0]

bosconian_pocket → core_top:
    video_rgb[23:0], video_de, video_hs, video_vs
    video_rgb_clock, video_rgb_clock_90
    audio_l[15:0], audio_r[15:0]          signed
```

### Clocks

One PLL from `clk_74a` (74.25 MHz). All outputs integer-related off a common
6.144 MHz base:

| Output | Rate | Use |
|---|---|---|
| c0 | 18.432 MHz | `clock_18` → `bosconian` |
| c1 | 6.144 MHz | `video_rgb_clock` |
| c2 | 6.144 MHz @ 90° | `video_rgb_clock_90` |

No audio clock is needed: `sound_i2s` derives its 12.288 MHz master clock from
`clk_74a` with an internal fractional accumulator.

This corrects an upstream inaccuracy: MiSTer runs the core at a flat 18.000 MHz,
so the game runs about 2.3% slow. 18.432 MHz is the authentic Namco rate
(6.144 MHz pixel clock × 3).

Requires fractional-N PLL mode — 74.25 MHz to 6.144 MHz has no integer solution
(their gcd is 6 kHz, needing a divider of 12375). The template's PLL already has
`fractional_vco_multiplier("true")` and already achieves 12.287999 MHz from
74.25 MHz, so this is proven achievable. The solution is VCO = 737.28 MHz
(18.432 × 40; 737.28 / 6.144 = 120 exactly), well inside the Cyclone V range. If
it nonetheless fails to close, fall back to 18.0 / 6.0 MHz, which reproduces
MiSTer's current behaviour exactly and is a known-good state.

### Video

`bosconian.vhd` generates RGB and sync in the 18.432 MHz domain, gated by its
internal 6 MHz clock enable. One retiming register stage moves those signals into
the 6.144 MHz `video_rgb_clock` domain. The `.sdc` must declare the two PLL
outputs as related clocks so Quartus times the transfer rather than treating it
as an unconstrained crossing.

- `video_de = hblank_n & vblank_n`
- `video_hs`, `video_vs` are the core's active-low syncs inverted
- RGB is 3:3:2 from the core, expanded to 8:8:8 by bit replication, matching what
  MiSTer's `arcade_video` does today

`video.json`: 288 × 224, rotation 0, aspect 4:3. Bosconian is a **horizontal**
game — the `.mra` states `<rotation>horizontal</rotation>` and the MiSTer top
level hardcodes `no_rotate = 1'b1`. It is not rotated like its Galaga sibling.

### Audio

Core `audio[15:0]` → `sound_i2s` → `audio_mclk` / `audio_lrck` / `audio_dac`.
Mono, duplicated to both channels.

**The samples are unsigned.** MiSTer sets `AUDIO_S = 0`. I2S expects signed, so
the conversion is `{~audio[15], audio[14:0]}`, instantiated with
`CHANNEL_WIDTH(16)` and `SIGNED_INPUT(1)`. Omitting this produces a full-scale
DC offset and clipping rather than silence, which is easy to misdiagnose as a
broken sound core. `sound_i2s` refuses to elaborate with `CHANNEL_WIDTH(16)` and
`SIGNED_INPUT(0)` — it raises `$error` — so the conversion cannot be skipped
silently.

### ROM loading

Dataslot 1 → `data_loader` → the existing `dn_addr[15:0] / dn_data[7:0] / dn_wr`
port on `bosconian`. `data_loader` emits bytes in address order, which is
identical to MiSTer's `ioctl_*` semantics, so `rtl/` needs no changes at all.

Expected ROM size is 58,880 bytes (0xE600), derived from the `.mra` part list:

| Region | Size |
|---|---|
| Main CPU, 4 × 4K | 16K |
| CPU 2, 2 × 4K | 8K |
| CPU 3, 4K | 4K |
| gfx1, 4K | 4K |
| gfx2, 4K doubled | 8K |
| Speech, 3 × 4K | 12K |
| Namco 50xx/51xx/52xx/54xx | 2K + 1K + 1K + 1K |
| Colour LUT + radar PROM | 2 × 256B |

### DIP switches

Interact-variable writes at `0x1002_0000` land in a `dsw` register, split on the
same bit numbering the `.mra` already uses, so the existing `<switches>` table
maps across one-to-one:

| Bits | Signal |
|---|---|
| 0–7 | `dip_a` → `dip_switch_a` (DIP 6K) |
| 8–15 | `dip_b` → `dip_switch_b` (DIP 6J) |
| 16 | `self_test` |
| 17 | `service` |

The core inverts on the way in (`~dsw`), as MiSTer does. A Reset action is bound
to `0x1000_0000`.

`interact.json` gets radio groups for Difficulty, Coinage, Bonus, and Lives, and
checkboxes for Allow Continue, Demo Sounds, Freeze, Cabinet, Self-test, and
Service.

**Requirement:** the Pocket's power-on defaults must reproduce MiSTer's
`default="08,68"` byte for byte — `dip_a = 0x08`, `dip_b = 0x68`. Bit ordering
within each group must be verified in-game (see Verification), not assumed from
reading the `.mra`.

The Bonus labels are ambiguous by design: the Readme notes that Bonus means
different things depending on the Lives setting, and the `.mra` encodes both
readings in one string (`20/70 | 30/120/120`). Carry those labels over verbatim.
Pocket's menu cannot express conditional options, and inventing clearer labels
risks stating something false.

### Inputs

`cont1_key` mapped to mirror the Galaga Pocket core already on the user's SD
card, so muscle memory carries over:

| Pocket | Function |
|---|---|
| D-pad | Up / Down / Left / Right |
| A, B, X, Y | Fire |
| Start | Start 1P |
| Select | Coin |
| L trigger | Start 2P |

Dock `cont2_key` drives player 2.

### Unused core ports

`bosconian.vhd` exposes ports this port does not drive. Tie them off explicitly
rather than leaving them floating:

- `h_offset`, `v_offset` → 0 (MiSTer analog-output tweaks, meaningless here)
- `pause` → 0 (out of scope for v1)

### Reset

Asserted on any of: PLL not locked, a startup delay, ROM download in progress,
or the menu Reset action.

## ROM build script

`pocket/tools/build_rom.py`, stdlib only (`zipfile`, `xml`, `argparse`).

1. Parse the `.mra` for its `<rom>` part list and the `zip="a.zip|b.zip|…"`
   search list.
2. Resolve each `<part name=…>` against those zips in order.
3. Verify each part against its `crc=` attribute.
4. Concatenate in document order, write `bosco.rom`.

That is the entire job. This `.mra` has no interleaving, no fills, and no
patches, so the script does not need to implement them.

CRC verification is the important part: it turns a wrong or corrupt ROM set into
a build-time error instead of a black screen on hardware, which is otherwise
near-undiagnosable for someone not doing FPGA development.

Leaves behind one `assert`-based self-check covering the offset and CRC logic.

## Build and CI

**Quartus cannot run on the development machine.** It is x86 Linux/Windows only;
there is no macOS build, and the machine is arm64. This is a hard constraint, not
a preference.

Therefore CI is a required component, not an optional one:

- GitHub Actions workflow on a Linux x86 runner, Quartus 17.0.2 Lite in a
  container (no license needed for Cyclone V in Lite edition).
- Post-process the `.rbf` into `bitstream.rbf_r` via `tools/reverse.py` — the
  Pocket requires the bit-reversed format.
- Package `pocket/dist/` plus the bitstream into a release zip laid out for
  direct extraction onto the SD card.

Local Docker on the dev machine is a fallback only. Quartus is a ~10 GB x86
image running under emulation on Apple Silicon; it may work, it will be slow, and
it is not the supported path.

## Verification

There is no simulation harness in this repo and this design does not add one.

- **Script:** `assert`-based self-check on offset/CRC logic. CRC verification
  catches bad ROM sets at build time.
- **Gateware:** Quartus fit and timing closure in CI is the automated gate. A
  timing failure fails the build.
- **Behaviour:** hardware checklist, run on the Pocket:
  - boots to attract mode
  - starfield scrolls
  - sprites and the radar render correctly
  - voice samples play (the Namco 52xx is the most fragile part of this core)
  - coin, start, and fire respond
  - each DIP group visibly takes effect — this is what validates the bit ordering
  - self-test mode passes

## Risks

- **Fractional-N PLL may not close timing at 18.432 MHz.** Mitigation: documented
  fallback to MiSTer's 18.0 MHz, which is known-good.
- **DIP bit ordering.** Derived from reading the `.mra`, not from a running
  system. Only in-game testing confirms it; the checklist covers this.
- **`base="8"` in the `.mra` `<switches>` element.** Its exact semantics in
  mra-tools should be confirmed during implementation. It does not affect the
  Pocket build — we author `interact.json` directly — but it does affect whether
  our reading of the bit mapping is correct.
- **No hardware-in-the-loop for the implementer.** Every behavioural bug costs a
  full CI build plus a manual SD card round trip. This argues for getting the
  boring things (clocks, reset, ROM load) provably right before chasing polish.

## Licensing

This repo is GPLv2. `agg23/openfpga-template` — the APF framework and the
utility modules alike — is permissively licensed (MIT), so vendoring it is
fine, provided the original headers stay intact. The resulting core inherits
GPLv2 and should say so in `core.json` metadata and the Pocket readme.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Location | This repo, `analogue` branch | One RTL source of truth; upstream MiSTer fixes still merge |
| ROM delivery | Concatenated `.rom` + own build script | Self-contained and reproducible in CI |
| Framework | `agg23/openfpga-template` | Ships APF *and* `data_loader`/`sound_i2s`/`sync_fifo`/`synch_3` in one repo — one vendoring step, ~250 lines of glue we own |
| v1 scope | Boot + DIPs only | Pause and hiscore are both broken upstream |
| Author id | `nlhomme` | Matches the GitHub account |
| Build | GitHub Actions | Quartus cannot run on the dev machine |
