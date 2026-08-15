# Hardware bring-up checklist

**The port boots and plays correctly on a real Analogue Pocket**, and the
game's own self-test reports **RAM OK / ROM OK**. Sections 1, 2, 4 and 5
(self-test, boot/attract, controls, audio) are confirmed.
The passing self-test is worth more than it looks: it checksums the ROMs
on real silicon, so it validates the whole load path — SD card, data
slot, bridge, FIFO, block RAM — and retires the risk that the loader's
FIFO (~14% margin, overflow checking off) was silently corrupting
bytes.

What remains unverified is everything a "does it boot and play?" test
cannot see. Those items are marked **[ ] not yet done** below. None is
known to be wrong; they are simply unchecked, and each has a failure mode
that looks fine until you look for it specifically.

Work through them in order; the early items are the ones most likely to
explain a failure in the later ones.

## Install

1. Unzip `nlhomme.Bosconian.zip` to the **root** of the SD card.
2. Build `bosco.rom` (see `README.md`) and copy it to
   `Assets/bosconian/common/bosco.rom`.
3. Launch the core, then **select `bosco.rom` from the file picker**.
   This core declares no default ROM filename, so copying the file into
   place is not by itself enough.

If the core does not appear in the Pocket's menu at all, the JSON tree is
wrong — not the gateware. If it appears but refuses to launch, suspect
the bitstream or the file layout rather than the game logic.

---

## 1. Self-test FIRST, before anything else — CONFIRMED (RAM OK / ROM OK)

Enable **Self-Test Mode** in the core's options menu and launch.

Bosconian's own self-test checksums its ROMs on real silicon. This is the
only test that can detect a silent ROM-load corruption: the loader's FIFO
has roughly 14% timing margin and overflow checking is disabled, so an
overrun would corrupt a handful of bytes and show up later as an
inexplicable graphics or sound glitch — never as a load error.

A clean self-test validates the whole path — SD card, data slot, bridge,
FIFO, and block RAM — in one shot.

- [ ] Self-test screen appears
- [ ] ROM checks pass
- [ ] Turn Self-Test Mode back off afterwards

## 2. Boot and attract mode — CONFIRMED

- [ ] Boots to attract mode
- [ ] Starfield scrolls smoothly
- [ ] Sprites and the radar render correctly
- [ ] Picture is stable — no rolling, flickering, or dropout

## 3. Sprite-to-background alignment, across several power cycles — NOT YET DONE

Power-cycle the Pocket **at least five times**, checking each boot.

The sprite layer and the tile/background layer latch on different clock
phases, and which phase gets sampled is re-decided at every reset. Worst
case is sprites sitting one pixel off from the background — and the
answer may differ between boots.

This behaviour is inherited unchanged from the MiSTer core, so a small
offset is not a regression introduced by this port.

- [ ] Note whether sprites are ever 1 pixel off from the starfield/tiles
- [ ] Note whether the answer **changes** between power cycles

If it is stable, leave it alone. If it flips between boots and bothers
you, the adjustment is `phase_shift1` in
`src/fpga/core/mf_pllbase/mf_pllbase_0002.v` (picoseconds; one
core slot is 54,257 ps). Do **not** reach for `video_ce` — that is the
misaligned phase.

## 4. Controls — CONFIRMED

- [ ] **Select** — adds a credit, coin sound plays
- [ ] **Start** — begins a 1-player game
- [ ] **L trigger** (with 2 credits) — begins a 2-player game
- [ ] **D-pad** — ship moves in all 8 directions, diagonals included
- [ ] **A / B / X / Y** — ship fires

With a dock and a second controller:

- [ ] Player 2's stick does not fight Player 1 during a 1-player game

Both controllers are ORed onto the same inputs — identical to MiSTer, but
MiSTer users rarely hit this and dock users will.

## 5. Audio — CONFIRMED

Listen for the absence of problems, not just the presence of sound.

- [ ] Music and effects audible in attract mode
- [ ] Coin, shot and explosion sounds present
- [ ] Voice samples intelligible ("Blast off!", "Alert! Alert!")
- [ ] **At silence: no hum, buzz or DC offset**

That last one matters. The samples are unsigned and must be converted to
signed; a wrong conversion produces full-scale offset and clipping, which
is easy to mistake for "the sound is just a bit rough".

Note the upstream MiSTer core already has imperfect shot and explosion
sounds (a pre-existing upstream issue). Reproducing those imperfections is a
pass; new ones are not.

## 6. Menu reset — NOT YET DONE

- [ ] Press **Reset Core** ten or more times in a row
- [ ] The game restarts every time and never sticks on a black screen

The reset pulse is stretched across a clock-domain boundary to guarantee
it is captured. Neither the original nor the stretched version has ever
run, and an unreliable reset is the expected symptom if the stretch is
insufficient.

## 7. Reload a ROM while running — NOT YET DONE

- [ ] With the game running, load the ROM again from the core's menu
- [ ] It reloads and restarts cleanly

A cold boot never exercises this path — reset assert, reload, release.

## 8. DIP switches — the ordering check — NOT YET DONE

Each group must produce the *right* effect, not merely some effect. The
bit ordering was derived by reading the `.mra`, never observed running.

- [ ] **Lives** — start a game, count the ships (default is 3)
- [ ] **Coinage** — set 2 Coins 1 Credit, insert coins, watch the counter
- [ ] **Free Play** — start with no coins inserted
- [ ] **Difficulty** — shown on the self-test screen
- [ ] **Demo Sounds** — off makes attract mode silent
- [ ] **Allow Continue** — die out, check a continue is offered
- [ ] **Cocktail Cabinet** — player 2's view flips in a 2-player game
- [ ] **Freeze** — gameplay halts

Free Play and Cocktail Cabinet deserve explicit attention: every other
setting has a plausible fallback reading, but those two can only be
confirmed by observing the behaviour.

## 9. Frame rate — NOT YET DONE

- [ ] Watch a full minute of gameplay for periodic judder

This core runs at 60.606 Hz — about 1% above 60 — because it uses the
authentic 18.432 MHz clock rather than MiSTer's 18.000 MHz. Nobody has
seen how the Pocket's scaler handles that cadence.

---

## If something is wrong

| Symptom | Look at |
|---|---|
| Core not listed in the menu | JSON tree, not the gateware |
| Core listed but won't launch | Bitstream or file layout |
| Black screen after selecting ROM | ROM never reached the core; check `dn_active` releases |
| Boots but graphics are garbled | ROM loaded at wrong offsets, or FIFO overrun — run the self-test |
| Loud buzz or clipping | Unsigned→signed audio conversion |
| Correct sounds, wrong pitch | Core clock is not 18.432 MHz |
| Sprites 1px off background | Pixel-phase lottery, see section 3 |
| A DIP does the wrong thing | Bit packing in `core_top.v` — never `rtl/` |

`rtl/` is the original MiSTer game core, carried over unchanged. Nothing
on this checklist should be fixed by editing it — every item above is a
property of the Pocket framework around it, not of the game logic.

## When the remaining items pass

Update the status note at the top of `README.md` to say the full
checklist has been worked through.
