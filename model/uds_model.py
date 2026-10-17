"""UDS-1x1 golden model v0.2: the specification of the chip's sound engine.

The RTL must match this model exactly: for the same HITs, STOPs and pin
triggers it must put the same number of 1s on the audio pin in every frame.
The engine is built around what is cheap in a 1x1 Sky130 tile:

  * Voice state lives in one long shift register (the "ring"), WORD = 48 bits
    per voice, that moves one bit per clock. A voice is processed while its
    48 bits pass the end of the ring, so one frame is 48 clocks per voice.
  * There is no multiplier. Loudness is made in time: during its 48-clock
    window a voice adds 8x its signal to the sigma-delta DAC on env >> 3
    clocks and 1x on env & 7 clocks, so over the window the DAC adds
    signal x env.
  * The tone/noise balance is made the same way: on each of those clocks the
    voice adds either its triangle or its noise, chosen by a fixed pattern.

Python's >> on negative numbers is floor division, the same as Verilog's >>>.

Timing
    One frame = WORD x slots clocks. The design target is fs = 62 500 Hz:
    clk = 6 MHz for the 1x1 chip's 2 voices (9 MHz for 3, 12 MHz for 4).
    Pitch and decay are counted in frames, so they scale with the clock.

SPI messages (mode 0, MSB first, CS low for the whole message)
    HIT   0x18 | channel, then 3 bytes:
          byte 1  pitch        increment = (32 + p[4:0]) << p[7:5] per frame,
                               on a 16-bit phase: 30.5 Hz (p=0) to 7.69 kHz (p=255)
          byte 2  decay[7:4]   the envelope steps every 2^decay frames (13-15 = 13)
                  sweep[3:0]   bits 2:0 amount s (0 = off), bit 3 reserved (0):
                               the pitch starts (env - 128) >> (7 - s) steps
                               higher and falls back while env >= 128
          byte 3  balance[7:4] tone/noise: 0 = all triangle, 15 = 15/16 noise
                  level[3:0]   the envelope starts at 17 x level (0 = silent)
    READ  0x30 | register, then one byte: the chip answers on MISO
          register 0 ID (0xD5), 1 VERSION (0x20 | voices), 2 STATUS
    STOP  0x40: every voice goes silent
    One HIT is taken per frame; wait for the BUSY pin to go low before the
    next message (HITs about 2 frames apart).
    Build options (src/project.v): with STATUS, register 2 is a bitmap of the
    channels sounding; with TRIGGERS, a rising edge on ui_in[n] plays
    channel n with its preset. The 1x1 chip has neither.

Noise: channels 0-4 (snare, toms, bass drum) use low-passed LFSR noise,
channels 5-7 (cymbal, hi-hats) use the metal source: four square waves XORed.

Voice word, in the order the bits leave the ring (bit 0 first)
    0-7 pitch, 8-11 decay, 12-15 sweep  (MSB first, as sent)
    16-23 env                           (LSB first)
    24-27 balance                       (MSB first, as sent)
    28-30 channel, 31 unused, 32-47 phase  (LSB first)

Per frame (each step() call)
    1. At the frame boundary: a pending HIT picks its voice slot from the
       state at the end of the last frame (same drum -> its own slot, else a
       free slot, else the quietest by env[7:5]); STATUS is latched; a waiting
       pin trigger is loaded if no HIT is pending.
    2. Each slot, in order, plays from its current state:
           tri   = triangle(phase)              9 bits signed
           noise = this frame's noise source    9 bits signed
           adds  wt x tri + wn x noise to the DAC (WEIGHTS[env][balance])
       then updates: phase += increment(clamp(pitch + sweep offset)),
       and if (frame mod 2^decay) == 0: env -= max(env >> 3, 1).
       The chosen slot is then replaced by the new HIT (env = 17 x level,
       phase = 0x4000); after a STOP every env is 0.
    3. The DAC, clock by clock (see "Sigma-delta DAC" below): each slot's
       48-clock window feeds x = 8 x src on env >> 3 clocks, 1 x src on
       env & 7 clocks and 0 on the rest, where src is the triangle or the
       noise by the balance pattern; the loop turns x into one output bit per
       clock. step() returns the frame's count of 1s.

Sigma-delta DAC (v0.2, VERSION register 0x22)
    A 1-bit second-order loop with two delaying integrators (feedback 1 and
    2), noise transfer function exactly (1 - z^-1)^2, input at half scale
    (feedback +-4096 for an x of at most +-2048):
        y   = 1 if v2 >= 0 else 0               the pin, one clock later
        fb  = +4096 if y else -4096
        v1 <- clamp(v1 + x - fb, -16384, 16383)   15 bits, saturating
        v2 <- v2 + v1 - 2 fb   (the old v1)       17 bits, never overflows
    Both integrators update from registered values, so the two adders work
    side by side (no adder chain in the clock period).
    Reset: v1 = 0, v2 = -1 (the pin is low in reset and idles as 0110 0110 ...).
    Silence: when no voice sounds at the end of a frame (the next frame's x
    is all 0), the frame's last clock (whose x is always 0) loads the reset
    values instead of updating, so every silence is the same clean pattern
    with exactly 48 ones per frame, whatever the loop held after a decay.
    Boundedness, for ANY input with |x| <= 2048 (proof in sd2_bounds()):
    while v2 >= 0 every clock lowers v1 by at least 2048, and v2 only rises
    while v1 > 8192, so once v2 turns non-negative it rises for at most 4
    more clocks; hence -45056 <= v2 <= 45050, inside 17 bits. The v1 clamp
    is a safety net: the chip's own signals keep |v1| below about 3.3 x 4096
    (model/dac_analysis.py), and the tests check that it never acts.
    The first-order DAC of v0.1 (Engine(dac_order=1)) is kept for comparisons:
        acc <- acc + 2048 + x (12 bits), the bit is the carry.
"""

WORD = 48
DEFAULT_SLOTS = 2                   # the 1x1 chip
FS_TARGET = 62_500

SNARE, SMALL_TOM, MID_TOM, BIG_TOM, BASS, CYMBAL, HH_CLOSED, HH_OPEN = range(8)
CHANNEL_NAMES = ("snare", "small tom", "middle tom", "big tom", "bass drum",
                 "cymbal", "closed hi-hat", "open hi-hat")
METAL_CHANNELS = (CYMBAL, HH_CLOSED, HH_OPEN)

CMD_HIT, CMD_READ, CMD_STOP = 0x18, 0x30, 0x40
REG_ID, REG_VERSION, REG_STATUS = 0, 1, 2
CHIP_ID = 0xD5
VERSION = 2                         # 1: first-order DAC, 2: second-order DAC

LFSR_BITS = 17                      # x^17 + x^14 + 1, period 131 071 frames
LFSR_RESET = 1
METAL_HALF_PERIODS = (3, 4, 5, 7)   # frames; the 4 is bit 2 of the frame counter
PHASE_START = 0x4000                # the triangle starts at its zero crossing
FRAME_BITS = 13                     # decay values 13-15 behave as 13

# Sigma-delta DAC (second order, see the docstring)
SD_FB = 4096                        # feedback: x of +-2048 is half scale
SD_V1_BITS, SD_V2_BITS = 15, 17
SD_V1_MIN, SD_V1_MAX = -(1 << (SD_V1_BITS - 1)), (1 << (SD_V1_BITS - 1)) - 1
SD_V2_MIN, SD_V2_MAX = -(1 << (SD_V2_BITS - 1)), (1 << (SD_V2_BITS - 1)) - 1
SD_V2_RESET = -1

# Default sound per channel: pitch, sweep, decay, balance, level.
# The pin triggers use these; the bridge sends its own values.
PRESETS = {
    SNARE:     (80, 4, 7, 11, 13),
    SMALL_TOM: (84, 5, 8, 2, 12),
    MID_TOM:   (70, 5, 8, 2, 12),
    BIG_TOM:   (56, 5, 9, 2, 12),
    BASS:      (20, 6, 9, 1, 15),
    CYMBAL:    (255, 0, 11, 15, 11),
    HH_CLOSED: (255, 0, 6, 15, 10),
    HH_OPEN:   (255, 0, 9, 15, 10),
}
ACCENT_LEVEL_DROP = 4               # unaccented hits on an accented row are this much softer


def frame_clks(slots=DEFAULT_SLOTS):
    return WORD * slots


def clock_for(slots=DEFAULT_SLOTS):
    """Clock frequency that gives fs = 62.5 kHz with this many voices."""
    return FS_TARGET * frame_clks(slots)


def hit_bytes(pitch, sweep, decay, balance, level):
    """The three HIT payload bytes for these parameters."""
    return (pitch & 0xFF, ((decay & 15) << 4) | (sweep & 15), ((balance & 15) << 4) | (level & 15))


def hit_message(ch, *params):
    return (CMD_HIT | (ch & 7),) + hit_bytes(*params)


def decode(payload):
    p, b2, b3 = payload
    return {"pitch": p, "decay": b2 >> 4, "sweep": b2 & 15, "balance": b3 >> 4, "level": b3 & 15}


def increment(pitch_eff):
    return (32 + (pitch_eff & 31)) << (pitch_eff >> 5)


def frequency(pitch, fs=FS_TARGET):
    """Oscillator frequency in Hz for an 8-bit pitch value."""
    return increment(pitch) * fs / 65536.0


def sweep_offset(env, sweep):
    s = sweep & 7
    if s == 0 or env < 128:
        return 0
    return (env - 128) >> (7 - s)


def effective_pitch(pitch, env, sweep):
    return min(pitch + sweep_offset(env, sweep), 255)


def triangle(phase):
    """9-bit signed triangle: -256 at phase 0, 255 at phase 0x8000."""
    p = phase >> 6
    t = (p & 0x1FF) ^ (0x1FF if p & 0x200 else 0)
    return t - 256


BITREV4 = tuple(int("{:04b}".format(i)[::-1], 2) for i in range(16))


def window_weights(env, balance):
    """(triangle weight, noise weight) a voice adds over its 48-clock window."""
    q, r = env >> 3, env & 7
    wt = wn = 0
    for t in range(WORD):
        w = 8 if t < q else (1 if t < q + r else 0)
        if w:
            if BITREV4[t & 15] < balance:
                wn += w
            else:
                wt += w
    return wt, wn


WEIGHTS = tuple(tuple(window_weights(e, b) for b in range(16)) for e in range(256))


def window_x(env, balance, tri, noise):
    """The DAC input x on each clock t = 0..47 of a voice's window, exactly as
    the RTL builds it: 8 x src while t < q, 1 x src while t < q + r, else 0,
    with q, r = env >> 3, env & 7, and src = noise on the clocks where
    bitrev4(t) < balance, else the triangle."""
    q, qr = env >> 3, (env >> 3) + (env & 7)
    xs = [0] * WORD
    for t in range(qr):
        src = noise if BITREV4[t & 15] < balance else tri
        xs[t] = 8 * src if t < q else src
    return xs


def sd2_bounds(xmax=2048, fb=SD_FB, v1_min=SD_V1_MIN, v1_max=SD_V1_MAX):
    """Worst-case v2 of the second-order loop for ANY input |x| <= xmax.

    While v2 >= 0 (y = 1) each clock changes v2 by v1 - 2 fb (the v1 before
    the clock) and lowers v1 by at least d = fb - xmax (or v1 is at the
    clamp's low end). v2 turns non-negative from v2 <= -1 in one clock that
    adds at most v1_max + 2 fb; after that the v1 it adds are at most v1_max,
    v1_max - d, v1_max - 2d, ..., so it rises only while those exceed 2 fb.
    The negative side is the mirror image. Returns (lowest, highest) v2."""
    d = fb - xmax
    assert d > 0
    hi = -1 + v1_max + 2 * fb
    v1 = v1_max
    while v1 > 2 * fb:
        hi += v1 - 2 * fb
        v1 -= d
    lo = 0 + v1_min - 2 * fb
    v1 = v1_min
    while v1 < -2 * fb:
        lo += v1 + 2 * fb
        v1 += d
    return lo, hi


def group(ch):
    return HH_CLOSED if ch == HH_OPEN else ch      # open and closed hat share a voice


class Slot:
    __slots__ = ("ch", "pitch", "decay", "sweep", "balance", "env", "phase")

    def __init__(self):
        self.ch = self.pitch = self.decay = self.sweep = self.balance = 0
        self.env = self.phase = 0

    def load(self, ch, payload):
        d = decode(payload)
        self.ch = ch
        self.pitch, self.decay, self.sweep, self.balance = d["pitch"], d["decay"], d["sweep"], d["balance"]
        self.env = 17 * d["level"]
        self.phase = PHASE_START


class Engine:
    def __init__(self, slots=DEFAULT_SLOTS, check=False, triggers=True, status=True, dac_order=2):
        self.slots = [Slot() for _ in range(slots)]
        self.check = check
        self.triggers = triggers                   # build option: pin triggers
        self.has_status = status                   # build option: STATUS register
        self.dac_order = dac_order                 # 2: this chip; 1: the v0.1 DAC, for comparisons
        self.frame = 0
        self.lfsr = LFSR_RESET
        self.metal_count = [0, 0, 0]               # counters for half periods 3, 5, 7
        self.metal_sq = [0, 0, 0]
        self.acc = 0                               # first-order DAC: integrator
        self.v1, self.v2 = 0, SD_V2_RESET          # second-order DAC: integrators
        self.v1_peak = self.v2_peak = 0            # largest |v1|, |v2| so far
        self.v1_clamps = 0                         # clocks on which the v1 clamp acted
        self.bits = None                           # set to a list to record the pin, clock by clock
        self.pending = None                        # (channel, payload) waiting for a slot
        self.kill_pending = False
        self.pins = 0                              # pin trigger levels
        self.served = 0                            # pins already turned into a hit
        self.status_reg = 0
        self.last_target = None
        self.choices = {"retrigger": 0, "free": 0, "steal": 0}

    # -- control, between frames ------------------------------------------
    def hit(self, ch, payload):
        """A HIT whose last bit arrived during the frame just stepped."""
        if self.check:
            assert self.pending is None, "HITs closer than 2 frames"
        self.pending = (ch & 7, tuple(payload))

    def stop(self):
        self.kill_pending = True

    def set_pins(self, mask):
        """Pin trigger levels (ui_in) as seen at the next frame boundary."""
        self.pins = mask & 0xFF if self.triggers else 0

    def read(self, reg):
        if reg == REG_ID:
            return CHIP_ID
        if reg == REG_VERSION:
            return (VERSION << 4) | len(self.slots)
        if reg == REG_STATUS:
            return self.status_reg
        return 0

    def status(self):
        """Bitmap of channels sounding now."""
        bits = 0
        for s in self.slots:
            if s.env:
                bits |= 1 << s.ch
        return bits

    def busy(self):
        return self.pending is not None

    def choose(self, ch):
        g = group(ch)
        for i, s in enumerate(self.slots):          # same drum already sounding: retrigger it
            if s.env and group(s.ch) == g:
                self.choices["retrigger"] += 1
                return i
        for i, s in enumerate(self.slots):          # else the first free slot
            if s.env == 0:
                self.choices["free"] += 1
                return i
        self.choices["steal"] += 1
        return min(range(len(self.slots)), key=lambda i: (self.slots[i].env >> 5, i))

    # -- one audio frame ---------------------------------------------------
    def noise(self):
        """(drum noise, metal noise) for this frame, 9 bits signed each."""
        pc = bin(self.lfsr & 0xF).count("1")
        drum = min(pc * 128 - 256, 255)
        x = self.metal_sq[0] ^ self.metal_sq[1] ^ self.metal_sq[2] ^ ((self.frame >> 2) & 1)
        return drum, (255 if x else -256)

    def step(self):
        """Run one frame; returns the number of 1s on the audio pin."""
        f = self.frame
        # 1. frame boundary
        commit = None
        if self.pending is not None:
            ch, payload = self.pending
            commit = (self.choose(ch), ch, payload)
            self.pending = None
        elif self.pins & ~self.served:
            waiting = self.pins & ~self.served
            p = (waiting & -waiting).bit_length() - 1       # lowest waiting pin
            self.served |= 1 << p
            self.pending = (p, hit_bytes(*PRESETS[p]))
        self.served &= self.pins
        self.status_reg = self.status() if self.has_status else 0
        kill, self.kill_pending = self.kill_pending, False
        self.last_target = commit[0] if commit else None

        # 2. voices: each plays its 48-clock window into the DAC input
        drum, metal = self.noise()
        total = 0
        xs = []
        for i, s in enumerate(self.slots):
            env = s.env
            n = metal if s.ch in METAL_CHANNELS else drum
            wx = window_x(env, s.balance, triangle(s.phase), n)
            xs += wx
            if env:
                wt, wn = WEIGHTS[env][s.balance]
                total += wt * triangle(s.phase) + wn * n
            pe = effective_pitch(s.pitch, env, s.sweep)
            s.phase = (s.phase + increment(pe)) & 0xFFFF
            if env and (f & ((1 << min(s.decay, FRAME_BITS)) - 1)) == 0:
                d = env >> 3
                s.env = env - (d if d else 1)
            if kill:
                s.env = 0
            if commit and commit[0] == i:
                s.load(commit[1], commit[2])

        # 3. noise sources and counters step at the end of the frame
        lfsr = self.lfsr
        fb = ((lfsr >> 16) ^ (lfsr >> 13)) & 1
        self.lfsr = ((lfsr << 1) | fb) & 0x1FFFF
        for k, half in enumerate((3, 5, 7)):
            if self.metal_count[k] == half - 1:
                self.metal_count[k] = 0
                self.metal_sq[k] ^= 1
            else:
                self.metal_count[k] += 1
        self.frame = (f + 1) & ((1 << FRAME_BITS) - 1)

        # 4. the DAC, one clock per x
        if self.check:
            assert abs(total) <= len(self.slots) * 65_280
            assert sum(xs) == total
        self.last_total = total
        self.last_x = xs
        if self.dac_order == 1:
            return self.dac1(xs)
        return self.dac2(xs, quiet=not any(s.env for s in self.slots))

    def dac2(self, xs, quiet=False):
        """Second-order sigma-delta over one frame; returns the count of 1s.
        The pin in clock c + 1 is y computed from v2 after clock c's update,
        which is how test/tb.v counts a frame. quiet: no voice sounds in the
        next frame, so the last clock restarts the loop at (0, -1)."""
        v1, v2 = self.v1, self.v2
        ones = 0
        bits = self.bits
        last = len(xs) - 1
        for i, x in enumerate(xs):
            if quiet and i == last:             # x is always 0 on a frame's last clock
                v1, v2 = 0, SD_V2_RESET
                if bits is not None:
                    bits.append(0)
                break
            fb = SD_FB if v2 >= 0 else -SD_FB
            v2 += v1 - 2 * fb               # both from this clock's v1, v2
            v1 += x - fb
            if v1 > SD_V1_MAX:
                v1 = SD_V1_MAX
                self.v1_clamps += 1
            elif v1 < SD_V1_MIN:
                v1 = SD_V1_MIN
                self.v1_clamps += 1
            y = v2 >= 0
            ones += y
            if bits is not None:
                bits.append(int(y))
            if abs(v1) > self.v1_peak:
                self.v1_peak = abs(v1)
            if abs(v2) > self.v2_peak:
                self.v2_peak = abs(v2)
        if self.check:
            assert SD_V2_MIN <= v2 <= SD_V2_MAX
        self.v1, self.v2 = v1, v2
        return ones

    def dac1(self, xs):
        """The v0.1 first-order DAC: acc + 2048 + x, the bit is the carry."""
        acc = self.acc
        ones = 0
        bits = self.bits
        for x in xs:
            acc += 2048 + x
            c = acc >> 12
            acc &= 0xFFF
            ones += c
            if bits is not None:
                bits.append(c)
        self.acc = acc
        return ones


def render(events, frames, slots=DEFAULT_SLOTS, check=False):
    """events: (frame, channel, payload). A HIT given for frame f arrives
    during frame f - 1, picks its slot at the start of frame f and plays from
    frame f + 1. HITs are kept 2 frames apart, as the bridge sends them.
    Returns the per-frame sum of the voices (the signal before the DAC)."""
    eng = Engine(slots, check)
    events = sorted(events, key=lambda e: (e[0], e[1]))
    out, k, last = [], 0, -2
    for f in range(frames):
        if k < len(events) and events[k][0] <= f and f - last >= 2:
            eng.hit(events[k][1], events[k][2])
            last = f
            k += 1
        eng.step()
        out.append(eng.last_total)
    return out


def pattern_events(bank, index, bpm, loops=2, presets=PRESETS, fs=FS_TARGET):
    """HIT events for an Autorhythm pattern from uds_patterns (bank A or B)."""
    import uds_patterns as U
    pat = bank[index]
    seq = U.steps(index, bank)
    acc = U.accents(index, bank)
    acc_rows = 0
    for a in acc:
        acc_rows |= a
    step_frames = fs * 60.0 / (bpm * pat["steps_per_beat"])
    events = []
    for loop in range(loops):
        for s, bits in enumerate(seq):
            frame = int(round((loop * len(seq) + s) * step_frames))
            for ch in range(8):
                if bits >> ch & 1:
                    p = list(presets[ch])
                    if acc_rows >> ch & 1 and not acc[s] >> ch & 1:
                        p[4] = max(0, p[4] - ACCENT_LEVEL_DROP)
                    events.append((frame, ch, hit_bytes(*p)))
    total = int(round(loops * len(seq) * step_frames)) + fs
    return events, total


def write_wav(path, samples, rate=FS_TARGET, gain=3.0, slots=DEFAULT_SLOTS):
    """16-bit mono WAV of render() output (the voices' sum, before the DAC).
    gain 1.0 = the level of the v0.1 first-order DAC, where a full-level voice
    reaches about 1/6 of the pin's swing; the v0.2 DAC is 6 dB lower (1/12)."""
    import struct
    import wave
    scale = 32767.0 * gain / (frame_clks(slots) * 2048)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", max(-32768, min(32767, int(s * scale))))
                               for s in samples))


if __name__ == "__main__":
    import sys
    import uds_patterns as U
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    ev, f = [], 0
    for ch in range(8):
        ev.append((f, ch, hit_bytes(*PRESETS[ch])))
        f += int(FS_TARGET * (1.8 if ch == CYMBAL else 0.6))
    sections = [("one-shots: snare, small tom, mid tom, big tom, bass drum, cymbal, "
                 "closed hat, open hat", render(ev, f))]
    for bank, idx, bpm, voices, label in ((U.PATTERNS, 0, 116, 2, "Rock 1"),
                                          (U.BANK_B, 0, 124, 2, "House"),
                                          (U.PATTERNS, 6, 128, 2, "Bossa nova"),
                                          (U.PATTERNS, 13, 120, 2, "Disco")):
        ev, total = pattern_events(bank, idx, bpm, loops=2)
        sections.append((label, render(ev, total, slots=voices)))
    samples, t = [], 0.0
    gap = [0] * int(FS_TARGET * 0.8)
    for label, s in sections:
        print("%4.1f s  %s" % (t, label))
        samples += s + gap
        t += (len(s) + len(gap)) / FS_TARGET
    peak = max(abs(v) for v in samples)
    write_wav(out + "/model_demo.wav", samples, gain=0.9 * frame_clks() * 2048 / peak)
