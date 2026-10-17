<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

UDS-1x1 is a digital homage to the Formanta UDS, a Soviet analog drum synthesizer from the 1980s. It plays
eight drums: snare, small, middle and big tom, bass drum, cymbal, closed and open hi-hat, with two voices
sounding at once. Every hit carries its own sound: pitch, pitch sweep, decay, tone/noise balance and level,
so a controller with knobs can shape each drum the way the UDS front panel does.

Each voice is a triangle oscillator with an exponential pitch (8 bits, 32 steps per octave), a pitch sweep
that falls back to the set pitch in the first part of the decay, a noise source, and an exponential decay
envelope. The drums use low-passed LFSR noise; the cymbal and hi-hats use a metallic source made of square
waves XORed together.

A new hit takes the voice of the same drum if it is still sounding (open and closed hi-hat count as one
drum), else a free voice, else the quieter voice.

To fit in one tile there is no multiplier and no voice register file:

- All voice state sits in one 96-bit shift register that moves one bit per clock. Each voice passes the end
  of it once per frame (48 clocks per voice), and its envelope and phase are updated bit by bit on the way.
- Loudness is made in time. During its 48 clocks a voice adds 8 x its signal to the sigma-delta DAC on
  env/8 clocks and 1 x on env mod 8 clocks, so the DAC adds signal x env. The tone/noise balance picks the
  triangle or the noise on each of those clocks.

At 6 MHz the sample rate is 62.5 kHz (one frame is 96 clocks). Pitches and decay times scale with the clock.

### Audio DAC: second-order sigma-delta

The audio pin carries a 1-bit second-order sigma-delta bitstream at the full clock rate (6 Mbit/s). The DAC
takes the voices' signal clock by clock (8 x or 1 x the triangle or noise, as above) and feeds it into two
integrators: v1 += x - fb and v2 += v1 - 2 fb, where the output bit is 1 when v2 >= 0 and fb is +4096 or
-4096 to match. The quantization noise is shaped by (1 - z^-1)^2: it is pushed far above the audio band, so
quiet sounds and the tails of the decays stay clean instead of breaking up into single clicks, as they did
with the first-order DAC of version 1. In the audio band (30 Hz to 16 kHz, behind a 15.9 kHz RC filter) the
error relative to the sound is 18 to 27 dB lower than before over a whole bass drum, middle tom, snare or
cymbal, and about 40 dB lower in the second half of each decay, where the old DAC crackled
(`model/dac_analysis.py`; listen to `docs/audio/before.mp3` and `after.mp3`).

- The integrators are 15 and 17 bits wide. v2 can be shown to stay within +-45 056 for any input the
  voices can produce; v1 has a saturating limit as a safety net that the chip's own sounds never reach.
- Silence is a clean mid-scale pattern, 0110 0110 ... (1.5 MHz), 48 ones in each 96-clock frame. The DAC
  restarts at the end of every frame in which no voice sounds, so this holds after every decay or STOP.
- Output level: to keep the loop stable the DAC input is at half scale, so the sound is 6 dB quieter than
  with the first-order DAC. A full-level voice swings the filtered output by about 1/12 of the supply. Add
  about 6 dB of gain after the filter (for example a gain of 2 in the amplifier) for the old loudness.
- Filter: an RC low-pass at about 16 kHz (1 kOhm and 10 nF) is enough for listening. What is left above the
  audio band is mostly the 62.5 kHz frame rate, about -43 dB of the supply (a little less than before, but
  the sound is 6 dB quieter). If the output drives an amplifier with a wide input bandwidth or an ADC, a
  second RC stage (for example 10 kOhm and 1 nF after the first) lowers it by another 17 dB.

The engine is specified by a Python model (`model/uds_model.py`); the tests check the chip against it frame
by frame, on the RTL and on the gate-level netlist.

## How to test

### SPI (mode 0, MSB first, SCK at most clk / 6)

Keep CS low for a whole message.

| Message | Bytes |
| --- | --- |
| HIT | `0x18` + channel, pitch, decay << 4 + sweep, balance << 4 + level |
| READ | `0x30` + register, then one more byte: the answer comes on MISO |
| STOP | `0x40`: all voices go silent |

Channels: 0 snare, 1 small tom, 2 middle tom, 3 big tom, 4 bass drum, 5 cymbal, 6 closed hi-hat, 7 open hi-hat.

- pitch p: oscillator frequency = (32 + p mod 32) x 2^(p div 32) x fs / 65 536, 30.5 Hz to 7.7 kHz at fs 62.5 kHz
- decay: the envelope steps every 2^decay frames (13 to 15 act as 13); about 35 steps from full level to silence
- sweep: bits 2..0 set the depth (0 = none, 7 = up to 127 pitch steps); bit 3 is reserved, send 0
- balance: 0 = all tone ... 15 = almost all noise
- level: 0 (silent) to 15

Registers: 0 ID (`0xD5`), 1 VERSION (`0x22`: version 2, 2 voices). Version 2 has the second-order DAC; a
version 1 design (`0x12`, first-order DAC, never taped out) is 6 dB louder, so firmware can read VERSION to set
its output gain.

The chip takes one HIT per frame (16 us). After a HIT, wait until BUSY (uio[5]) goes low before sending the
next message.

Good starting sounds (pitch, decay, sweep, balance, level): snare 80, 7, 4, 11, 13; small tom 84, 8, 5, 2, 12;
middle tom 70, 8, 5, 2, 12; big tom 56, 9, 5, 2, 12; bass drum 20, 9, 6, 1, 15; cymbal 255, 11, 0, 15, 11;
closed hi-hat 255, 6, 0, 15, 10; open hi-hat 255, 9, 0, 15, 10.

The 7-segment display shows the number of the channel last hit, so you can see that a HIT arrived.

## External hardware

- Tiny Tapeout Audio Pmod on the bidirectional Pmod header (audio on uio[7] and uio[6]), or an RC filter and
  an amplifier on uo_out[7].
- Any SPI controller: the RP2040 on the demo board, a laptop GUI behind a USB bridge, or an ESP32 panel with
  knobs.
