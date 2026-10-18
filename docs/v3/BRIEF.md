# UDS v3: shared brief

Started 2026-10-18 at about 12:00 Riga time by Juris's main session (the coordinator). Every v3 session reads
this file first. Tracker: [issue #2](https://github.com/ai-wrangler/tt-uds-1x1/issues/2).

## 1. What Juris asked for

> Ok create 3rd version of UDS - more modern with sounds that I can change for each chanell - for inspiration
> take sounds from Gus Gus, Simian Mobile Disco, Trentemoller and Royksopp. It has to be real and has to fit on
> 1x1 tile. Deploy agents for faster work

How we read it (Juris can overrule any of this on the tracker or through the coordinator):

- **3rd version.**
  - v1 = `main` (ba09c49, first-order DAC). It is what tapes out if nothing changes.
  - v2 = branch `sd2` / PR #1 (second-order DAC).
  - v3 = a new voice engine on this branch `v3`. `v3` was forked from `sd2`, so it already has the
    second-order DAC.
  - Juris decides later which version goes on the TTSKY26d tile. The shuttle closes on 2026-11-30.
- **More modern.** The drums of current electronic music: deep house, techno, electro and electronica.
  - Kicks: punchy, with a fast pitch drop.
  - Snares that snap, and real claps.
  - Crisp hats, metallic percussion, toms and zaps.
- **Sounds that I can change for each channel.**
  - All 8 channels get a fully editable sound (a *patch*).
  - The controller (the browser twin, the RP2350 on the demoboard) keeps one patch per channel and sends it
    with every HIT, and knobs edit it live.
  - The chip stores a patch only while a voice plays it. There is no on-chip patch memory: one FF costs about
    20 to 25 µm².
- **Inspiration.** GusGus, Simian Mobile Disco, Trentemøller and Röyksopp.
  - Original sounds and original patterns only. Everything is synthesized: no samples, no transcribed parts of
    their tracks.
  - Kit names by city or mood (for example "Reykjavík"), with "inspired by ..." only in the descriptions.
- **Real.** The sound comes out of the chip's own audio pin.
  - The Verilog passes the Tiny Tapeout flow on 1x1 in GitHub Actions on branch `v3`: the gds, precheck and
    gl_test jobs all pass. The viewer job always fails on branches; that is expected.
  - A bit-exact Python model specifies the engine, and the tests check the RTL and the gate-level netlist
    against it.
- **Fit on 1x1 tile.** This is a hard requirement. If a feature does not fit, it goes, in the priority order
  that V3-SOUND posts.

## 2. Facts to start from

- **Chip repo:** https://github.com/ai-wrangler/tt-uds-1x1.
  - `main` = v1, `sd2` = v2.
  - Branches `area-3v`, `area-4v` and `lean-3v` are old experiments. The v1 engine with 3 or 4 voices failed
    GDS on 1x1 (lean-3v: 82 % utilization at global placement, routing congestion 1.03, failed in "Build
    GDS"). Their Actions logs have the numbers.
- **Browser twin:** https://github.com/ai-wrangler/uds-virtual, live at https://ai-wrangler.github.io/uds-virtual/.
  - It deploys from `main` with GitHub Pages.
  - `app/engine/builds.json` lists the engine builds "1st" (v1) and "2nd" (v2).
  - The Verilog runs clock by clock in WebAssembly: Yosys → `engine/gen.py` → straight-line C++ → zig wasm32.
    v1 runs at 100 to 170 MHz on a cloud CPU, which is 17 to 28 times real time.
- **Area** (TT flow, sky130_fd_sc_hd, 1x1):

  | Design | Std-cell area | Utilization | FFs | Setup slack (20 ns constraint) | Hold slack |
  | --- | --- | --- | --- | --- | --- |
  | v1, 2 voices | 12 842 µm² | 77.9 % | 235 | +8.95 ns | +0.022 ns |
  | sd2 | 14 805 µm² | 89.8 % | 254 | +5.87 ns | +0.029 ns |

  - The core holds about 16 500 µm². Aim for at most 88 %; above about 90 %, routing and hold fixing failed
    before.
  - So v3 must **save** area somewhere before it can add features. The expensive part is per-voice state:
    every bit of a voice word is about 20 µm² times the number of voices.
- **v1 engine** (`src/uds_core.v` on `main`; header comment and `docs/info.md`):
  - All voice state is in one shift-register ring: 48 bits per voice, moving one bit per clock.
  - The envelope and the phase are updated bit-serially.
  - Loudness is made in time: 8× slots and 1× slots.
  - Oscillator: a triangle with exponential pitch, 32 steps per octave. The pitch sweep is tied to the
    envelope.
  - Noise: LFSR drum noise, and a fixed metal source that XORs squares at fs/6, fs/10 and fs/14.
  - 96 clocks per frame at 6 MHz, so 62.5 kHz.
  - The voice choice prefers the same channel, then a free voice, then the quieter one. Channels 6 and 7 share
    a voice (hi-hat choke).
- **SPI protocol (v1):**
  - Mode 0, SCK at most clk / 6, CS low for a whole message.
  - HIT = `0x18|ch` + 3 bytes. READ = `0x30|reg` + a dummy byte (reg 0 is ID `0xD5`, reg 1 is VERSION).
    STOP = `0x40`.
  - BUSY is on uio[5]: wait for it to go low after a HIT. FRAME is on uio[4].
- **Pins.** Keep them for v3, so the demoboard, the Audio Pmod and the DIY guide still apply:

  | Pin | Signal |
  | --- | --- |
  | uio[0] | CS_N |
  | uio[1] | MOSI |
  | uio[2] | MISO |
  | uio[3] | SCK |
  | uio[4] | FRAME |
  | uio[5] | BUSY |
  | uio[6] | AUDIO_L |
  | uio[7] | AUDIO_R |
  | uo[6:0] | 7-segment digit (last channel hit) |
  | uo[7] | AUDIO |
  | ui_in | free: v3 may use it (for example for pin triggers), but only if area allows |

  The top module stays `tt_um_ai_wrangler_uds1x1`, so v3 could replace v1 with a plain merge.
- **Controller:** the RP2350 on the TT demoboard. It sets the chip clock (6, 12, 24 MHz and so on) and drives
  SPI. The browser twin must simulate v3 at least 3 times faster than real time on a cloud CPU.
- **GM drum map** in uds-virtual (`app/audio/midi.js`), note → channel:

  | Notes | Channel |
  | --- | --- |
  | 35, 36 | 4 |
  | 37 to 40 | 0 |
  | 41, 43 | 3 |
  | 45, 47 | 2 |
  | 48, 50 | 1 |
  | 42, 44 | 6 |
  | 46 | 7 |
  | 49, 51, 52, 55, 57, 59 | 5 |

  A v3 kit may bring its own map (see section 4).

## 3. Roles: one session each

| Session | Owns | Where |
| --- | --- | --- |
| **V3-CHIP** | Architecture; `docs/v3/CONTRACT.md` + `docs/v3/params.json`; `model/uds3_*.py`; `src/`; `test/`; `info.yaml`; `docs/info.md`; GDS; `docs/v3/REPORT.md` | tt-uds-1x1, branch `v3` |
| **V3-SOUND** | Research on the four artists; prototype synth; feature ranking; `kits/*.json`; `kits/patterns/*.mid`; `docs/v3/audio/*.mp3`; `docs/v3/SOUND.md` | tt-uds-1x1, branch `v3-sound` → PRs into `v3` (V3-CHIP merges) |
| **V3-WEB** | Browser twin: v3 engine build, per-channel sound editor, kit loader, chip-version switch, tests, deploy | uds-virtual, branch `v3` → PR into `main` |
| **Coordinator** | Talks to Juris, watches the tracker, checks results | Juris's main session |

## 4. Coordination

- **Tracker** = [issue #2](https://github.com/ai-wrangler/tt-uds-1x1/issues/2).
  - Comment at every milestone, for every question and for every contract change. Start each comment with your
    session name in bold.
  - Read the tracker at the start, at each milestone, and at least every 30 minutes while you work.
- **`docs/v3/CONTRACT.md`** on `v3` is the single source of truth for:
  - the clock and the frame;
  - the SPI protocol;
  - the HIT patch fields: name, bits, meaning, units, defaults;
  - the VERSION value.

  V3-CHIP owns it.
  - It starts as DRAFT 0. V3-CHIP freezes CONTRACT 1 within about 60 minutes, after a quick area estimate,
    and announces it on the tracker.
  - Each later change bumps the version, lists the change at the top of the file and is announced on the
    tracker.
  - Everyone else reads it and never edits it: ask on the tracker instead.
- **`docs/v3/params.json`** is the machine-readable twin of the contract, written by V3-CHIP:

  ```json
  {"contract": 1, "clockHz": 12000000, "frameClocks": 192,
   "hit": {"opcode": "0x18|ch", "bytes": [["pitch"], ["decay", "level"], ...]},
   "params": [{"id": "pitch", "label": "Pitch", "bits": 8, "min": 0, "max": 255, "default": 64,
               "unit": "32 steps/oct", "group": "tone", "help": "..."}]}
  ```

  - In `hit.bytes`, the fields of each byte are listed MSB first, and their widths come from `params`.
  - V3-WEB generates the editor from this file, and V3-SOUND writes kits against it.
- **Kits** = `kits/<id>.json`:

  ```json
  {"id": "reykjavik", "name": "Reykjavík", "inspiredBy": "GusGus", "description": "...", "contract": 1,
   "tempo": 122,
   "channels": [{"ch": 0, "name": "Clap", "notes": [39, 38], "patch": {"pitch": 80, "decay": 7, ...}}]}
  ```

  - `channels` has 8 entries.
  - `notes` are the GM notes that play that channel; use the default map above when omitted.

## 5. DRAFT 0 of the contract

This is a strawman so everyone can start; V3-CHIP will change it. See `CONTRACT.md` and `params.json`.

- **Clock and frame:** 12 MHz, 192 clocks per frame (2 voices × 96-clock windows) = 62.5 kHz.
- **HIT** = `0x18|ch` + 4 bytes (a 32-bit patch). The playing voice keeps the patch until the sound ends.

| Byte | Bits | Field | Meaning |
| --- | --- | --- | --- |
| P0 | 7:0 | pitch | base pitch, exponential, 32 steps per octave (as v1) |
| P1 | 7:4 | decay | amplitude decay time, exponential (as v1) |
| P1 | 3:0 | level | start level |
| P2 | 7:5 | bend | pitch-envelope depth: 0 = none, 7 = about +3 octaves at the start |
| P2 | 4:3 | bendtime | pitch-envelope time: about 5, 15, 40 or 120 ms |
| P2 | 2:0 | mix | tone/noise mix: 0 = tone only, 7 = noise only |
| P3 | 7:6 | wave | 0 triangle, 1 driven (clipped) triangle, 2 square, 3 metal (the tone square XOR fixed inharmonic squares) |
| P3 | 5:4 | color | noise color: 0 dark, 1 white, 2 bright (high-passed), 3 metallic |
| P3 | 3 | clap | the noise comes in 3 to 4 bursts about 10 ms apart, then the tail |
| P3 | 2:0 | snap | a short click or noise transient at the start: 0 = off, 7 = strongest |

- **Other messages:** READ ID, READ VERSION and STOP as in v1. VERSION = `0x3V` (3 = v3, V = voices).
- **Unchanged from v1:** the 7-segment digit, FRAME and BUSY.

## 6. Rules

- **tt-uds-1x1 branches:**
  - Never push to `main` or `sd2` of tt-uds-1x1, and never touch PR #1.
  - No force-push on `v3`. V3-SOUND works on `v3-sound` and opens PRs into `v3`.
- **uds-virtual `main`** deploys the live site:
  - Only V3-WEB merges there, and only by PR.
  - Merge only when all existing tests (Node, Playwright e2e/ui/audio) and the new ones pass, and v1 and v2
    still work.
  - Check the live site after each deploy.
- **Tools:**
  - Use REST `gh api`; GraphQL is not available.
  - Never run `playwright install`: Chromium is already in `/opt/pw-browsers`. For global packages, use
    `NODE_PATH=$(npm root -g)`.
  - pip needs `--break-system-packages`.
- **Commits and PRs:** end commit messages and PR descriptions with the attribution lines your own session
  instructions give you.
- **Juris's earlier UI decisions stand:**
  - English only.
  - Autorhythm = 16 empty slots that load `.mid` files.
  - The MIDI section stays as it is.
- **Reporting:** plain words, measured numbers, and say what is not done. Never call something verified that
  was not run.

## 7. Timeline (Riga time)

| By | Milestone |
| --- | --- |
| ~12:45 | V3-SOUND posts the feature ranking with parameter ranges |
| ~13:00 | V3-CHIP freezes CONTRACT 1 + params.json |
| ~15:00 | V3-CHIP: model + first RTL, RTL tests against the model green |
| ~17:00 | V3-CHIP: GDS green on `v3`, fits 1x1. V3-SOUND: kits, demo patterns, renders |
| ~18:30 | V3-WEB: v3 playable on the live site |
| ~19:30 | Final reports on the tracker |

If something slips, ship what works and say what is missing.
