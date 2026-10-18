# UDS v3 contract: DRAFT 0

**Status: DRAFT 0. This is a strawman by the coordinator.** V3-CHIP owns this file. It replaces DRAFT 0 with
CONTRACT 1 after a first area estimate and announces that on the
[tracker](https://github.com/ai-wrangler/tt-uds-1x1/issues/2). Each later version lists its changes here at the
top. Other sessions read this file and never edit it.

`docs/v3/params.json` is the machine-readable twin of this file.

## Clock and frame

- 12 MHz. One frame is 192 clocks: 2 voices, each with a 96-clock window. That gives a 62.5 kHz frame.
- Pitches and times scale with the clock.

## Pins (same as v1)

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
| uo[6:0] | 7-segment digit of the last channel hit |
| uo[7] | AUDIO |

ui_in is unused.

## SPI

Mode 0, MSB first, SCK at most clk / 6, CS low for the whole message.

| Message | Bytes |
| --- | --- |
| HIT | `0x18` + ch, then P0 P1 P2 P3 |
| READ | `0x30` + reg, then a dummy byte. The answer comes on MISO. Reg 0 = ID `0xD5`; reg 1 = VERSION `0x3V` (3 = v3, V = voices). |
| STOP | `0x40`: all voices go silent |

- After a HIT, wait until BUSY is low before you send the next message.
- Voice choice works as in v1: the same channel first, then a free voice, then the quieter one. Channels 6 and
  7 share a voice (choke).

## HIT patch: 32 bits

| Byte | Bits | id | Meaning |
| --- | --- | --- | --- |
| P0 | 7:0 | pitch | Base pitch, exponential, 32 steps per octave (as v1) |
| P1 | 7:4 | decay | Amplitude decay time, exponential (as v1) |
| P1 | 3:0 | level | Start level, 0 to 15 |
| P2 | 7:5 | bend | Pitch-envelope depth: 0 = none, 7 = about +3 octaves at the start |
| P2 | 4:3 | bendtime | Pitch-envelope time: about 5, 15, 40 or 120 ms |
| P2 | 2:0 | mix | Tone/noise mix: 0 = tone only, 7 = noise only |
| P3 | 7:6 | wave | 0 triangle, 1 driven (clipped) triangle, 2 square, 3 metal |
| P3 | 5:4 | color | Noise color: 0 dark, 1 white, 2 bright (high-passed), 3 metallic |
| P3 | 3 | clap | The noise comes in 3 to 4 bursts about 10 ms apart, then the tail |
| P3 | 2:0 | snap | A short click or noise transient at the start: 0 = off, 7 = strongest |

## Audio

- Second-order 1-bit sigma-delta, as on `sd2`.
- Filter it with the Audio Pmod, or with an RC filter of 1 kΩ and 10 nF.
