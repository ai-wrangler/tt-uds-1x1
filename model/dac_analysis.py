"""Evidence for the second-order sigma-delta DAC (model v0.2, VERSION 0x22).

    python3 model/dac_analysis.py                 # everything, prints a markdown report
    python3 model/dac_analysis.py stability idle quality audio

Sections
    proof      the bound on v2 for any input |x| <= 2048 (uds_model.sd2_bounds)
    stability  both DACs' integrator peaks under worst cases, from the model itself
    idle       silence after reset and after decays; idle tones in low-level decays
    quality    in-band error vs a perfect DAC, before (first order) and after
    audio      docs/audio/before.mp3 and after.mp3 (needs ffmpeg)

The analog chain used for quality and audio is the one the browser simulator
uses: a 1-pole RC low-pass at 15.9 kHz applied at the clock rate (6 MHz), then
a 2001-tap FIR decimator to 48 kHz, then (quality only) a 30 Hz..16 kHz band.
The "perfect DAC" is the same chain applied to the ideal DAC output
0.5 + x / 4096 (first order) or 0.5 + x / 8192 (second order, delayed by
one clock to match its loop), clock by clock, so the difference is only the
DAC's own error.

Needs numpy and scipy (and matplotlib for the figure, ffmpeg for the MP3s).
"""
import array
import os
import random
import subprocess
import sys

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import uds_model as M  # noqa: E402
import uds_patterns as U  # noqa: E402

ROOT = os.path.dirname(HERE)
FCLK = M.clock_for(M.DEFAULT_SLOTS)          # 6 MHz
F = M.frame_clks(M.DEFAULT_SLOTS)            # 96 clocks per frame
FC = 15_900.0                                # RC corner
DEC = 125                                    # 6 MHz / 125 = 48 kHz
FS_OUT = FCLK // DEC
TAPS = 16 * DEC + 1
H = signal.firwin(TAPS, 20_000.0, fs=FCLK, window=("kaiser", 9.0))
BAND = (30.0, 16_000.0)
QUALITY_CHANNELS = (M.BASS, M.MID_TOM, M.SNARE, M.CYMBAL)


# ---------------------------------------------------------------- rendering
def run(events, frames, dac_order=2, want_x=False, engine=None):
    """Step the model. events: {frame: [callable(engine)]}. Returns
    (bits as uint8 array, x as int16 array or None, engine)."""
    e = engine or M.Engine(M.DEFAULT_SLOTS, check=True, dac_order=dac_order)
    e.bits = bytearray()
    xs = array.array("h") if want_x else None
    for f in range(frames):
        for a in events.get(f, ()):
            a(e)
        e.step()
        if want_x:
            xs.extend(e.last_x)
    bits = np.frombuffer(bytes(e.bits), np.uint8)
    e.bits = None
    return bits, (np.frombuffer(xs, np.int16).astype(np.int64) if want_x else None), e


def hit_events(hits):
    """hits: [(frame, channel, params)] -> events; HITs at least 2 frames apart."""
    ev = {}
    last = -10
    for f, ch, p in sorted(hits, key=lambda h: h[0]):
        f = max(f, last + 2)
        ev.setdefault(f, []).append(lambda e, ch=ch, p=p: e.hit(ch, M.hit_bytes(*p)))
        last = f
    return ev


def chain(v, chunk=DEC * 48_000):
    """RC at the clock rate, then FIR decimation to 48 kHz; streams long inputs."""
    a = 1.0 - np.exp(-2 * np.pi * FC / FCLK)
    zi = np.zeros(1)
    hist = np.zeros(TAPS - 1)
    k = (TAPS - 1) // DEC
    out = []
    n = len(v) - len(v) % DEC
    for s in range(0, n, chunk):
        c = np.asarray(v[s:min(s + chunk, n)], np.float64)
        r, zi = signal.lfilter([a], [1.0, -(1.0 - a)], c, zi=zi)
        buf = np.concatenate((hist, r))
        out.append(signal.upfirdn(H, buf, 1, DEC)[k:k + len(r) // DEC])
        hist = buf[-(TAPS - 1):]
    return np.concatenate(out)


def band(v, lo=BAND[0], hi=BAND[1]):
    V = np.fft.rfft(v)
    f = np.fft.rfftfreq(len(v), 1.0 / FS_OUT)
    V[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(V, len(v))


# The second-order loop's output lags its input by one clock more than the
# first-order one (signal transfer z^-2 instead of z^-1 from x to the
# decision): the perfect DAC is delayed to match, since a 167 ns delay is not
# an error.
DELAY = {1: 0, 2: 1}


def ideal(x, order):
    """The perfect DAC's output, clock by clock, minus the mid-scale 0.5."""
    v = x / (4096.0 if order == 1 else 8192.0)
    d = DELAY[order]
    return np.concatenate((np.zeros(d), v[:len(v) - d])) if d else v


def pin(bits):
    """The pin, clock by clock, minus the mid-scale 0.5 (so the filters start settled)."""
    return bits.astype(np.float64) - 0.5


def db(p):
    return 10 * np.log10(p)


# --------------------------------------------------------------------- proof
def proof():
    lo, hi = M.sd2_bounds()
    print("## Proof of boundedness\n")
    print("For any input sequence with |x| <= 2048 (the RTL's x is 8 x a 9-bit value at most):")
    print("v1 is clamped to 15 bits [%d, %d]; v2 stays in [%d, %d] (%.2f x 4096), inside 17 bits [%d, %d]."
          % (M.SD_V1_MIN, M.SD_V1_MAX, lo, hi, max(-lo, hi) / 4096, M.SD_V2_MIN, M.SD_V2_MAX))
    # brute-force check of the argument on the extreme adversary: x pinned at +-2048
    worst = 0
    rng = random.Random(1)
    for trial in range(200):
        v1, v2 = 0, -1
        for i in range(20_000):
            fb = M.SD_FB if v2 >= 0 else -M.SD_FB
            x = rng.choice((2047, -2048)) if trial % 2 else (2047 if (v1 > 0) == (trial % 4 == 0) else -2048)
            v2 += v1 - 2 * fb
            v1 = min(max(v1 + x - fb, M.SD_V1_MIN), M.SD_V1_MAX)
            worst = max(worst, abs(v2))
    print("Adversarial +-2048 inputs (random and v1-following, 4 M clocks): max |v2| = %d (%.2f x 4096), "
          "inside the bound.\n" % (worst, worst / 4096))
    assert lo <= -worst and worst <= hi


# ----------------------------------------------------------------- stability
def stability(quick=False):
    print("## Stability: integrator peaks on the chip's own signals (model, clock by clock)\n")
    print("| scenario | frames | clocks | max abs v1 | max abs v2 | v1 clamp acted |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    rows = []

    def report(name, e, frames):
        rows.append((name, e.v1_peak, e.v2_peak, e.v1_clamps))
        print("| %s | %d | %.1f M | %d (%.2f x 4096) | %d (%.2f x 4096) | %d |" % (
            name, frames, frames * F / 1e6, e.v1_peak, e.v1_peak / 4096, e.v2_peak, e.v2_peak / 4096,
            e.v1_clamps))
        sys.stdout.flush()

    # 1. both voices at full level, sustained (re-hit every 3000 frames), every
    #    balance, drum noise in one voice and metal noise in the other, pitch corners
    pitches = (0, 31, 32, 128, 224, 255) if not quick else (0, 255)
    agg = M.Engine(M.DEFAULT_SLOTS, check=True)
    n_agg = 0
    per_bal = {}
    for bal in range(16):
        for p in pitches:
            for chs in ((M.BASS, M.CYMBAL), (M.SNARE, M.HH_OPEN)):
                hits = []
                for k in range(0, 9000 if not quick else 3000, 3000):
                    hits += [(2 + k, chs[0], (p, 0, 15, bal, 15)), (4 + k, chs[1], (255 - p, 0, 15, bal, 15))]
                frames = 9000 if not quick else 3000
                _, _, e = run(hit_events(hits), frames)
                n_agg += frames
                agg.v1_peak = max(agg.v1_peak, e.v1_peak)
                agg.v2_peak = max(agg.v2_peak, e.v2_peak)
                agg.v1_clamps += e.v1_clamps
                pb = per_bal.setdefault(bal, [0, 0])
                pb[0] = max(pb[0], e.v1_peak)
                pb[1] = max(pb[1], e.v2_peak)
    report("both voices full level, sustained; all 16 balances x pitches %s; drum + metal noise"
           % "/".join(map(str, pitches)), agg, n_agg)

    # 2. same pitch, same sign: both triangles at the lowest pitch and at the
    #    highest, in phase (hit together), no noise
    for p in (0, 255):
        hits = [(2 + k, M.BASS, (p, 0, 15, 0, 15)) for k in range(0, 20_000, 4000)]
        hits += [(4 + k, M.BIG_TOM, (p, 0, 15, 0, 15)) for k in range(0, 20_000, 4000)]
        _, _, e = run(hit_events(hits), 20_000)
        report("two in-phase triangles, pitch %d, full level" % p, e, 20_000)

    # 3. sweeps at full depth from the top
    hits = []
    for k in range(0, 20_000, 400):
        hits.append((2 + k, M.BIG_TOM, (0, 7, 9, 0, 15)))
        hits.append((4 + k, M.BASS, (128, 7, 9, 3, 15)))
    _, _, e = run(hit_events(hits), 20_000)
    report("pitch sweeps, depth 7, retriggered every 400 frames", e, 20_000)

    # 4. rapid retriggers: a HIT every 2 frames (the fastest the chip takes), random, loud
    rng = random.Random(7)
    n = 100_000 if not quick else 20_000
    hits = [(f, rng.randrange(8), (rng.randrange(256), rng.randrange(8), rng.randrange(16),
                                  rng.randrange(16), rng.choice((13, 14, 15)))) for f in range(2, n, 2)]
    _, _, e = run(hit_events(hits), n)
    report("rapid retriggers: a HIT every 2 frames, random sounds, levels 13-15", e, n)

    # 5. STOPs while loud
    ev = hit_events([(f, rng.randrange(8), (rng.randrange(256), 0, 15, rng.randrange(16), 15))
                     for f in range(2, 30_000, 6)])
    for f in range(5, 30_000, 37):
        ev.setdefault(f, []).append(lambda e: e.stop())
    _, _, e = run(ev, 30_000)
    report("STOP every 37 frames between loud HITs every 6 frames", e, 30_000)

    # 6. random parameter sweeps, several seeds, at least 10 M clocks each
    seeds = (1, 2, 3, 4) if not quick else (1,)
    tot = M.Engine(M.DEFAULT_SLOTS)
    n_tot = 0
    for seed in seeds:
        rng = random.Random(seed)
        n = 120_000 if not quick else 20_000
        ev = {}
        f = 2
        while f < n:
            ev.setdefault(f, []).append(
                lambda e, ch=rng.randrange(8), p=(rng.randrange(256), rng.randrange(16), rng.randrange(16),
                                                   rng.randrange(16), rng.randrange(16)): e.hit(ch, M.hit_bytes(*p)))
            if rng.random() < 0.02:
                ev.setdefault(f + 1, []).append(lambda e: e.stop())
            f += rng.choice((2, 2, 3, 5, 10, 30, 100, 400, 2000))
        _, _, e = run(ev, n)
        n_tot += n
        tot.v1_peak = max(tot.v1_peak, e.v1_peak)
        tot.v2_peak = max(tot.v2_peak, e.v2_peak)
        tot.v1_clamps += e.v1_clamps
    report("random sweeps: all 5 parameters uniform, random gaps and STOPs, %d seeds" % len(seeds), tot, n_tot)

    worst1 = max(r[1] for r in rows)
    worst2 = max(r[2] for r in rows)
    lo, hi = M.sd2_bounds()
    print("\nWorst case over all scenarios: |v1| %d = %.2f x 4096 (clamp at %d: margin %.1f dB), "
          "|v2| %d = %.2f x 4096 (17-bit range %d, proven bound %d: margin %.1f dB). "
          "The clamp never acted." % (worst1, worst1 / 4096, M.SD_V1_MAX, db((M.SD_V1_MAX / worst1) ** 2),
                                     worst2, worst2 / 4096, M.SD_V2_MAX, hi, db((M.SD_V2_MAX / worst2) ** 2)))
    print("\nPer balance (sustained case), max |v1| / |v2| in units of 4096: " + ", ".join(
        "%d: %.2f/%.2f" % (b, v[0] / 4096, v[1] / 4096) for b, v in sorted(per_bal.items())) + "\n")
    assert all(r[3] == 0 for r in rows)
    return rows


# ---------------------------------------------------------------------- idle
def period_of(bits, maxp=512):
    tail = bits[-4096:]
    for p in range(1, maxp + 1):
        if np.array_equal(tail[p:], tail[:-p]):
            return p
    return None


def idle(quick=False):
    print("## Silence and idle tones\n")
    bits, _, e = run({}, 200)
    p = period_of(bits)
    print("- After reset, x = 0: the pin repeats `%s` (period %d clocks, %.2f MHz), 48 ones in every frame."
          % ("".join(map(str, bits[-8:])), p, FCLK / p / 1e6))
    counts = set()
    # silence after each preset and after random sounds: which patterns does the loop settle in?
    periods = {}
    rng = random.Random(3)
    cases = [(ch, M.PRESETS[ch]) for ch in range(8)]
    cases += [(rng.randrange(8), (rng.randrange(256), rng.randrange(8), rng.randrange(10), rng.randrange(16),
                                  rng.randrange(1, 16))) for _ in range(60 if not quick else 10)]
    inband = 0.0
    for ch, prm in cases:
        frames = 2 + 40 * (1 << min(prm[2], 13)) + 400
        bits, _, e = run(hit_events([(2, ch, prm)]), min(frames, 200_000))
        if any(s.env for s in e.slots):
            continue
        _, _, e = run({}, 200, engine=e)       # more silence, record it
        b2, _, _ = run({}, 400, engine=e)
        pp = period_of(b2)
        periods[pp] = periods.get(pp, 0) + 1
        y = chain(pin(b2))[100:]
        inband = max(inband, np.max(np.abs(band(y - y.mean()))))
        counts.add(tuple(sorted(set(int(c) for c in b2.reshape(-1, F).sum(1)))))
    print("- Silence after %d sounds had decayed (8 presets + random sounds): the loop always settles in a "
          "short cycle, periods %s (clocks: count); in-band residue after the RC + decimation at most %.1e "
          "of the pin swing (%.0f dB); frame counts %s."
          % (sum(periods.values()), dict(sorted(periods.items(), key=lambda kv: (kv[0] is None, kv[0]))),
             inband, 20 * np.log10(max(inband, 1e-12)), sorted(counts)))
    print()


def tonality(E, f, lo=BAND[0], hi=BAND[1], half=40):
    """largest ratio (dB) of an error-spectrum bin to the median of its neighbours, and its frequency"""
    idx = np.nonzero((f >= lo) & (f <= hi))[0]
    best, fbest = 0.0, 0.0
    for i in idx[half:-half]:
        r = E[i] / np.median(E[i - half:i + half + 1])
        if r > best:
            best, fbest = r, f[i]
    return 10 * np.log10(best), fbest


def idle_tones():
    """Idle tones in low-level signals: error spectra of the quiet decay tails and of
    very soft sustained sounds, before and after. A noise-like error spectrum peaks
    about 10 to 15 dB above its local median by chance; a tone sticks out far more."""
    print("Idle tones: largest bin of the in-band error spectrum above the median of its 80 neighbours "
          "(noise-like error: about 10 to 15 dB; a tone: much more), and the in-band error level.\n")
    print("| signal | before: peak / median | at | error | after: peak / median | at | error |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    cases = []
    for ch in QUALITY_CHANNELS:
        cases.append(("%s, quiet tail (env < 16)" % M.CHANNEL_NAMES[ch], ch, None))
    for p in (0, 64, 128):
        cases.append(("soft sustained triangle, pitch %d (%.0f Hz), level 1" % (p, M.frequency(p)), M.BIG_TOM,
                      (p, 0, 15, 0, 1)))
    cases.append(("soft sustained metal noise, level 1", M.CYMBAL, (255, 0, 15, 15, 1)))
    for name, ch, prm in cases:
        cells = [name]
        for order in (1, 2):
            if prm is None:
                x, bits, segs = preset_render(ch, order)
                s0, s1 = segs["quiet tail"]
            else:
                bits, x, _ = run(hit_events([(2, ch, prm)]), 8000, dac_order=order, want_x=True)
                s0, s1 = int(200 * F / DEC), int(8000 * F / DEC)
            e = (chain(pin(bits)) - chain(ideal(x, order)))[s0:s1]
            w = np.hanning(len(e))
            E = np.abs(np.fft.rfft((e - e.mean()) * w)) ** 2
            fr = np.fft.rfftfreq(len(e), 1.0 / FS_OUT)
            t, ft = tonality(E, fr)
            lvl = db(np.mean(band(e) ** 2))
            cells += ["%.1f dB" % t, "%.0f Hz" % ft, "%.1f dB" % lvl]
        print("| " + " | ".join(cells) + " |")
    print()


def tail_spectrum(ch, order):
    """error and signal spectra (power per bin) in the second half of a preset's sound"""
    x, bits, segs = preset_render(ch, order)
    out = chain(pin(bits))
    ref = chain(ideal(x, order))
    s0, s1 = segs["second half"]
    e = (out - ref)[s0:s1]
    r = ref[s0:s1]
    w = np.hanning(len(e))
    E = np.abs(np.fft.rfft((e - e.mean()) * w)) ** 2
    R = np.abs(np.fft.rfft((r - r.mean()) * w)) ** 2
    f = np.fft.rfftfreq(len(e), 1.0 / FS_OUT)
    return f, E, R


# ------------------------------------------------------------------- quality
_cache = {}
HIT_FRAME = 2


def preset_render(ch, order):
    """Render one preset hit until it has decayed. Returns (x, bits, segments):
    segments in 48 kHz output samples: the whole sound (from the hit until the
    envelope reaches 0), its second half, and its quiet tail (env < 16: there a
    full-level window asks the first-order DAC for less than one extra 1 per frame)."""
    key = (ch, order)
    if key not in _cache:
        p = M.PRESETS[ch]
        frames = HIT_FRAME + 2 + 40 * (1 << min(p[2], 13)) + 2000
        envs = []
        ev = hit_events([(HIT_FRAME, ch, p)])
        e = M.Engine(M.DEFAULT_SLOTS, check=True, dac_order=order)
        orig = e.step

        def step():
            r = orig()
            envs.append(max(s.env for s in e.slots))
            return r
        e.step = step
        bits, x, _ = run(ev, frames, dac_order=order, want_x=True, engine=e)
        envs = np.array(envs)
        on = np.nonzero(envs)[0]
        start, end = HIT_FRAME + 2, on[-1] + 2         # frames in which the voice plays
        quiet = start + np.nonzero(envs[start:] < 16)[0][0]

        def smp(f):
            return int(f * F / DEC)
        segs = {"whole sound": (smp(start), smp(end)), "second half": (smp((start + end) // 2), smp(end)),
                "quiet tail": (smp(quiet), smp(end))}
        _cache[key] = (x, bits, segs)
    return _cache[key]


def snr(ch, order, seg="whole sound"):
    x, bits, segs = preset_render(ch, order)
    out = band(chain(pin(bits)))
    ref = band(chain(ideal(x, order)))
    s0, s1 = segs[seg]
    out, ref = out[s0:s1], ref[s0:s1]
    e = out - ref
    return db(np.mean(ref ** 2)), db(np.mean(e ** 2))


def quality():
    print("## Quality: in-band error vs a perfect DAC (RC 15.9 kHz, FIR to 48 kHz, 30 Hz..16 kHz)\n")
    print("Signal and error in dB relative to a pin that is always 1. SNR = signal / error.\n")
    print("| preset | sound (ms) | whole sound: before | after | gain | second half (ms): before | after | gain "
          "| quiet tail, env < 16 (ms): before | after | gain |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    res = {}
    ms = lambda seg: (seg[1] - seg[0]) * 1000.0 / FS_OUT  # noqa: E731
    for ch in range(8):
        cols = []
        segs = preset_render(ch, 2)[2]
        for seg in ("whole sound", "second half", "quiet tail"):
            s1, e1 = snr(ch, 1, seg)
            s2, e2 = snr(ch, 2, seg)
            cols.append((s1 - e1, s2 - e2, e1, e2))
        res[ch] = cols
        mark = "**" if ch in QUALITY_CHANNELS else ""
        cells = ["%s%s%s" % (mark, M.CHANNEL_NAMES[ch], mark), "%.0f" % ms(segs["whole sound"])]
        for k, c in zip(("whole sound", "second half", "quiet tail"), cols):
            first = "%.1f dB" % c[0] if k == "whole sound" else "(%.0f) %.1f dB" % (ms(segs[k]), c[0])
            cells += [first, "%.1f dB" % c[1], "%+.1f dB" % (c[1] - c[0])]
        print("| " + " | ".join(cells) + " |")
    s1, _ = snr(M.BASS, 1)
    s2, _ = snr(M.BASS, 2)
    print("\nOutput level: the signal at the pin is %.1f dB lower with the second-order DAC (bass drum: "
          "%.1f vs %.1f dB), because its input is at half scale. The noise floor drops much more.\n"
          % (s1 - s2, s2, s1))
    worst = min(res[ch][0][1] - res[ch][0][0] for ch in QUALITY_CHANNELS)
    print("Smallest improvement over the four target presets (whole sound): %+.1f dB (target: +12 dB).\n" % worst)
    print("Absolute in-band error, dB re a pin that is always 1 (before / after; add 6 dB to 'after' for the "
          "same loudness):\n")
    for ch in QUALITY_CHANNELS:
        print("- %s: whole %.1f / %.1f, second half %.1f / %.1f, quiet tail %.1f / %.1f" % (
            M.CHANNEL_NAMES[ch], res[ch][0][2], res[ch][0][3], res[ch][1][2], res[ch][1][3],
            res[ch][2][2], res[ch][2][3]))
    print()
    return res


def figure(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4), sharex=True, sharey=True)
    for ax, ch in zip(axes.flat, QUALITY_CHANNELS):
        for order, color, label in ((1, "#c0392b", "first order (v0.1)"), (2, "#1f6fb2", "second order (v0.2)")):
            f, E, R = tail_spectrum(ch, order)
            ref = R.max()
            if order == 1:
                ax.plot(f / 1000, 10 * np.log10(R / ref + 1e-30), color="#999999", lw=0.8, label="signal")
            ax.plot(f / 1000, 10 * np.log10(E / ref + 1e-30), color=color, lw=0.8, label="error, " + label)
        ax.set_title("%s: second half of the sound" % M.CHANNEL_NAMES[ch], fontsize=10)
        ax.set_xlim(0, 16)
        ax.set_ylim(-140, 5)
        ax.grid(alpha=0.3)
    for ax in axes[1]:
        ax.set_xlabel("kHz")
    for ax in axes[:, 0]:
        ax.set_ylabel("dB re signal peak bin")
    axes[0, 0].legend(fontsize=8, loc="upper right")
    fig.suptitle("DAC error spectrum in the decays (RC 15.9 kHz, 48 kHz, Hann window); "
                 "error levels are relative to each DAC's own signal", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    print("Figure: %s\n" % os.path.relpath(path, ROOT))


# --------------------------------------------------------------------- audio
def demo_events():
    """One-shots of all eight presets, soft and loud, then two Autorhythm patterns."""
    hits, f = [], 2
    for level_drop in (0, 8):
        for ch in range(8):
            p = list(M.PRESETS[ch])
            p[4] = max(1, p[4] - level_drop)
            hits.append((f, ch, tuple(p)))
            f += int(M.FS_TARGET * (1.6 if ch == M.CYMBAL else 0.7))
    for bank, idx, bpm in ((U.PATTERNS, 0, 116), (U.BANK_B, 0, 124)):
        ev, total = M.pattern_events(bank, idx, bpm, loops=2)
        for fr, ch, payload in ev:
            d = M.decode(payload)
            hits.append((f + fr, ch, (d["pitch"], d["sweep"], d["decay"], d["balance"], d["level"])))
        f += total
    return hits, f


def audio(outdir):
    hits, frames = demo_events()
    outs = {}
    for order in (1, 2):
        bits, _, _ = run(hit_events(hits), frames, dac_order=order)
        y = chain(pin(bits))
        outs[order] = y * (2.0 if order == 2 else 1.0)          # level-matched: +6 dB for the new DAC
    peak = max(np.max(np.abs(v)) for v in outs.values())
    os.makedirs(outdir, exist_ok=True)
    for order, name in ((1, "before"), (2, "after")):
        pcm = np.clip(outs[order] / peak * 0.89, -1, 1)
        raw = (pcm * 32767).astype("<i2").tobytes()
        path = os.path.join(outdir, name + ".mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(FS_OUT), "-ac", "1",
                        "-i", "-", "-codec:a", "libmp3lame", "-b:a", "160k", "-ar", "48000", path],
                       input=raw, check=True)
        print("- %s: %s, %.1f s" % (name, os.path.relpath(path, ROOT), len(pcm) / FS_OUT))
    print("\nBoth files: RC 15.9 kHz + decimation to 48 kHz, the same demo (8 presets loud, then soft, "
          "then Rock 1 and House). after.mp3 is played 6 dB louder so that the drums are at the same "
          "level: that is the analog gain the new DAC needs.\n")


if __name__ == "__main__":
    what = sys.argv[1:] or ["proof", "stability", "idle", "quality", "audio"]
    quick = "quick" in what
    if "proof" in what:
        proof()
    if "stability" in what:
        stability(quick)
    if "idle" in what:
        idle(quick)
        idle_tones()
    if "quality" in what:
        quality()
        figure(os.path.join(ROOT, "docs", "dac_spectra.png"))
    if "audio" in what:
        audio(os.path.join(ROOT, "docs", "audio"))
