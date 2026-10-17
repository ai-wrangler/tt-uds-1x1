<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

UDS-1x1 is a digital homage to the Formanta UDS, a Soviet analog drum synthesizer from the 1980s. It plays
eight drums: snare, small, middle and big tom, bass drum, cymbal, closed and open hi-hat. Four voices sound at
once. Every hit carries its own sound: pitch, pitch sweep, decay, tone/noise balance and level, so an outside
controller with knobs can shape each drum the way the UDS front panel does.

Each voice is a triangle oscillator with an exponential pitch (8 bits, 32 steps per octave), a pitch sweep
that falls back to the set pitch in the first part of the decay, a noise source, and an exponential decay
envelope. The drums use low-passed LFSR noise; the cymbal and hi-hats use a metallic source made of square
waves XORed together.

To fit four voices in one tile there is no multiplier and no voice register file:

- All voice state sits in one 192-bit shift register that moves one bit per clock. Each voice passes the end
  of it once per frame (48 clocks per voice), and its envelope and phase are updated bit by bit on the way.
- Loudness is made in time. During its 48 clocks a voice adds 8 x its signal to the sigma-delta DAC on
  env/8 clocks and 1 x on env mod 8 clocks, so the DAC adds signal x env. The tone/noise balance picks the
  triangle or the noise on each of those clocks.

At 12 MHz the sample rate is 62.5 kHz. The audio output is a first-order sigma-delta bitstream: filter it
with an RC low-pass (for example 1 kOhm and 10 nF) or use the Tiny Tapeout Audio Pmod.

The engine is specified by a Python model (`model/uds_model.py`) and the tests check the chip against it
frame by frame.

## How to test

### SPI (mode 0, MSB first, SCK at most clk / 6)

Keep CS low for a whole message.

| Message | Bytes |
| --- | --- |
| HIT | `0x18` + channel, pitch, decay << 4 + sweep, balance << 4 + level |
| READ | `0x30` + register, then one more byte: the answer comes on MISO |
| STOP | `0x40`: all voices go silent |

Channels: 0 snare, 1 small tom, 2 middle tom, 3 big tom, 4 bass drum, 5 cymbal, 6 closed hi-hat, 7 open hi-hat.
A hit on the open or closed hi-hat cuts the other one off.

- pitch p: oscillator frequency = (32 + p mod 32) x 2^(p div 32) x 62 500 / 65 536 Hz, 30.5 Hz to 7.7 kHz
- decay: the envelope steps every 2^decay frames; about 35 steps from full level to silence
- sweep: bits 2..0 set the depth (0 = none, 7 = up to 127 pitch steps); bit 3 is reserved, send 0
- balance: 0 = all tone ... 15 = almost all noise
- level: 0 (silent) to 15

Registers: 0 ID (`0xD5`), 1 VERSION (`0x14`: version 1, 4 voices), 2 STATUS (bit n = channel n is sounding).

The chip takes one HIT per frame (16 us). After a HIT, wait until BUSY (uio[5]) goes low before sending the
next message.

### Without a computer

Set the clock to 12 MHz and give a rising edge on one of ui_in[7:0]: that drum plays with its built-in sound.
The segments of the 7-segment display light while their drums sound (the hi-hats share segment G).

## External hardware

- Tiny Tapeout Audio Pmod on the bidirectional Pmod header (audio on uio[7] and uio[6]), or an RC filter and
  an amplifier on uo_out[7].
- Any SPI controller, for example the RP2040 on the demo board, a laptop GUI behind a USB bridge, or an ESP32
  panel with knobs.
