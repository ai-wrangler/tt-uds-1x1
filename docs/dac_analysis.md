# Second-order DAC: evidence

Output of `python3 model/dac_analysis.py` (model v0.2, VERSION 0x22). Every number below comes from the
bit-exact model, which the cocotb tests check against the RTL frame by frame (and, on the RTL, the DAC
integrators at every frame end).

## Proof of boundedness

For any input sequence with |x| <= 2048 (the RTL's x is 8 x a 9-bit value at most):
v1 is clamped to 15 bits [-16384, 16383]; v2 stays in [-45056, 45050] (11.00 x 4096), inside 17 bits [-65536, 65535].
Adversarial +-2048 inputs (random and v1-following, 4 M clocks): max |v2| = 40711 (9.94 x 4096), inside the bound.

## Stability: integrator peaks on the chip's own signals (model, clock by clock)

| scenario | frames | clocks | max abs v1 | max abs v2 | v1 clamp acted |
| --- | ---: | ---: | ---: | ---: | ---: |
| both voices full level, sustained; all 16 balances x pitches 0/31/32/128/224/255; drum + metal noise | 1728000 | 165.9 M | 13311 (3.25 x 4096) | 22973 (5.61 x 4096) | 0 |
| two in-phase triangles, pitch 0, full level | 20000 | 1.9 M | 12000 (2.93 x 4096) | 19391 (4.73 x 4096) | 0 |
| two in-phase triangles, pitch 255, full level | 20000 | 1.9 M | 11926 (2.91 x 4096) | 19227 (4.69 x 4096) | 0 |
| pitch sweeps, depth 7, retriggered every 400 frames | 20000 | 1.9 M | 11959 (2.92 x 4096) | 19201 (4.69 x 4096) | 0 |
| rapid retriggers: a HIT every 2 frames, random sounds, levels 13-15 | 100000 | 9.6 M | 12839 (3.13 x 4096) | 22634 (5.53 x 4096) | 0 |
| STOP every 37 frames between loud HITs every 6 frames | 30000 | 2.9 M | 12616 (3.08 x 4096) | 21710 (5.30 x 4096) | 0 |
| random sweeps: all 5 parameters uniform, random gaps and STOPs, 4 seeds | 480000 | 46.1 M | 12902 (3.15 x 4096) | 22767 (5.56 x 4096) | 0 |

Worst case over all scenarios: |v1| 13311 = 3.25 x 4096 (clamp at 16383: margin 1.8 dB), |v2| 22973 = 5.61 x 4096 (17-bit range 65535, proven bound 45050: margin 9.1 dB). The clamp never acted.

Per balance (sustained case), max |v1| / |v2| in units of 4096: 0: 2.97/4.88, 1: 3.14/5.53, 2: 3.14/5.50, 3: 2.99/4.75, 4: 2.98/4.86, 5: 3.08/4.73, 6: 3.19/4.88, 7: 2.92/4.65, 8: 2.90/4.63, 9: 2.98/4.77, 10: 3.25/4.98, 11: 2.99/4.88, 12: 2.98/4.73, 13: 3.06/5.07, 14: 3.15/5.61, 15: 3.15/5.60

## Silence and idle tones

- After reset, x = 0: the pin repeats `11001100` (period 4 clocks, 1.50 MHz), 48 ones in every frame.
- Silence after 68 sounds had decayed (8 presets + random sounds): the loop always settles in a short cycle, periods {4: 68} (clocks: count); in-band residue after the RC + decimation at most 2.1e-09 of the pin swing (-174 dB); frame counts [(48,)]: every silent frame has exactly 48 ones.

Idle tones: largest bin of the in-band error spectrum above the median of its 80 neighbours (noise-like error: about 10 to 15 dB; a tone: much more), and the in-band error level.

| signal | before: peak / median | at | error | after: peak / median | at | error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bass drum, quiet tail (env < 16) | 11.6 dB | 5558 Hz | -62.6 dB | 12.3 dB | 11001 Hz | -109.4 dB |
| middle tom, quiet tail (env < 16) | 9.7 dB | 1139 Hz | -62.5 dB | 9.9 dB | 9958 Hz | -108.8 dB |
| snare, quiet tail (env < 16) | 9.0 dB | 9463 Hz | -62.1 dB | 11.2 dB | 8423 Hz | -109.9 dB |
| cymbal, quiet tail (env < 16) | 16.4 dB | 124 Hz | -65.4 dB | 12.1 dB | 353 Hz | -110.6 dB |
| soft sustained triangle, pitch 0 (31 Hz), level 1 | 15.6 dB | 657 Hz | -62.7 dB | 12.2 dB | 15567 Hz | -109.3 dB |
| soft sustained triangle, pitch 64 (122 Hz), level 1 | 14.3 dB | 4407 Hz | -62.6 dB | 13.8 dB | 2812 Hz | -109.4 dB |
| soft sustained triangle, pitch 128 (488 Hz), level 1 | 24.8 dB | 4166 Hz | -63.1 dB | 20.6 dB | 3061 Hz | -109.3 dB |
| soft sustained metal noise, level 1 | 22.6 dB | 1675 Hz | -63.8 dB | 21.3 dB | 617 Hz | -111.7 dB |

## Quality: in-band error vs a perfect DAC (RC 15.9 kHz, FIR to 48 kHz, 30 Hz..16 kHz)

Signal and error in dB relative to a pin that is always 1. SNR = signal / error.

| preset | sound (ms) | whole sound: before | after | gain | second half (ms): before | after | gain | quiet tail, env < 16 (ms): before | after | gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **snare** | 76 | 27.4 dB | 45.3 dB | +17.9 dB | (38) 13.1 dB | 53.9 dB | +40.8 dB | (31) 10.8 dB | 51.5 dB | +40.7 dB |
| small tom | 147 | 29.9 dB | 50.2 dB | +20.2 dB | (74) 11.5 dB | 50.4 dB | +38.9 dB | (61) 9.8 dB | 48.5 dB | +38.7 dB |
| **middle tom** | 147 | 29.9 dB | 50.2 dB | +20.3 dB | (74) 11.7 dB | 51.9 dB | +40.2 dB | (61) 9.9 dB | 50.1 dB | +40.1 dB |
| big tom | 295 | 30.3 dB | 53.5 dB | +23.2 dB | (147) 12.1 dB | 52.1 dB | +40.0 dB | (123) 9.9 dB | 49.7 dB | +39.8 dB |
| **bass drum** | 311 | 32.7 dB | 56.0 dB | +23.3 dB | (156) 12.2 dB | 52.4 dB | +40.2 dB | (123) 9.9 dB | 49.9 dB | +40.0 dB |
| **cymbal** | 1147 | 34.0 dB | 60.7 dB | +26.6 dB | (573) 19.3 dB | 57.5 dB | +38.2 dB | (459) 16.6 dB | 54.9 dB | +38.3 dB |
| closed hi-hat | 36 | 32.2 dB | 45.1 dB | +12.9 dB | (18) 18.2 dB | 50.7 dB | +32.5 dB | (15) 16.6 dB | 48.6 dB | +32.0 dB |
| open hi-hat | 287 | 32.7 dB | 54.1 dB | +21.3 dB | (143) 18.7 dB | 57.0 dB | +38.3 dB | (123) 17.1 dB | 55.4 dB | +38.3 dB |

Output level: the signal at the pin is 6.0 dB lower with the second-order DAC (bass drum: -36.5 vs -30.5 dB), because its input is at half scale. The noise floor drops much more.

Smallest improvement over the four target presets (whole sound): +17.9 dB (target: +12 dB).

Absolute in-band error, dB re a pin that is always 1 (before / after; add 6 dB to 'after' for the same loudness):

- bass drum: whole -63.2 / -92.5, second half -62.6 / -108.8, quiet tail -62.6 / -108.6
- middle tom: whole -63.0 / -89.3, second half -62.6 / -108.8, quiet tail -62.5 / -108.7
- snare: whole -62.5 / -86.4, second half -62.2 / -109.0, quiet tail -62.1 / -108.7
- cymbal: whole -65.3 / -98.0, second half -65.7 / -109.9, quiet tail -65.4 / -109.8

Figure: docs/dac_spectra.png

- before: docs/audio/before.mp3, 31.0 s
- after: docs/audio/after.mp3, 31.0 s

Both files: RC 15.9 kHz + decimation to 48 kHz, the same demo (8 presets loud, then soft, then Rock 1 and House). after.mp3 is played 6 dB louder so that the drums are at the same level: that is the analog gain the new DAC needs.

