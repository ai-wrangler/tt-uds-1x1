# SPDX-FileCopyrightText: © 2026 Juris Vitols
# SPDX-License-Identifier: Apache-2.0
"""UDS-1x1 tests: every frame of audio is compared with the Python model.

The testbench counts the 1s on the audio pin in each frame; the test steps
model/uds_model.py one frame at a time and checks that the counts are equal.
On the RTL it also checks that the DAC integrators (v1, v2) at the end of
every frame equal the model's.
Stimuli (SPI messages, pin triggers) start right after a frame boundary, so
the frame in which the chip sees them is known exactly (see Bench.spi).
"""
import os
import random
import re
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "model"))
import uds_model as M  # noqa: E402

with open(os.path.join(HERE, "..", "src", "project.v")) as _f:     # the chip's build options
    _top = _f.read()
VOICES = int(re.search(r"localparam \[3:0\] VOICES\s*= 4'd(\d+);", _top).group(1))
TRIGGERS = int(re.search(r"localparam\s+TRIGGERS\s*= (\d);", _top).group(1))
STATUS = int(re.search(r"localparam\s+STATUS\s*= (\d);", _top).group(1))
DIGITS = (0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07)       # 7-segment 0..7
GL = os.environ.get("GATES") == "yes"   # gate-level runs are much slower: shorter waits
F = M.frame_clks(VOICES)        # clocks per frame
HALF = 4                        # SPI: clocks per SCK half period

CS, MOSI, MISO, SCK = 0, 1, 2, 3


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.model = M.Engine(VOICES, check=True, triggers=bool(TRIGGERS), status=bool(STATUS))
        self.before = {}        # frame -> actions on the model before it steps that frame
        self.checked = 0        # frames compared so far
        self.errors = 0
        self.statuses = []      # STATUS register during each frame, from the model
        self.uio = 1 << CS
        self.ui = 0
        self.ready = 0          # first frame in which the next SPI message may start
        self.v1_peak = 0        # largest |v1|, |v2| of the chip's DAC at frame ends (RTL only)
        self.v2_peak = 0

    def at(self, frame, action):
        self.before.setdefault(frame, []).append(action)

    async def start(self):
        dut = self.dut
        cocotb.start_soon(Clock(dut.clk, 84, unit="ns").start())   # about 12 MHz
        dut.ena.value = 1
        dut.ui_in.value = 0
        dut.uio_in.value = self.uio
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 3)
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
        cocotb.start_soon(self.monitor())

    async def monitor(self):
        dut = self.dut
        while True:
            await dut.frame_tick.value_change
            await ReadOnly()
            got = int(dut.frame_ones.value)
            for action in self.before.pop(self.checked, []):
                action()
            want = self.model.step()
            self.statuses.append(self.model.status_reg)
            if got != want:
                self.errors += 1
                if self.errors <= 10:
                    dut._log.error("frame %d: chip %d ones, model %d" % (self.checked, got, want))
            if not GL and self.checked > 0:
                # the DAC integrators at the end of the frame must equal the model's
                v1 = signed(dut.frame_v1.value, M.SD_V1_BITS)
                v2 = signed(dut.frame_v2.value, M.SD_V2_BITS)
                self.v1_peak = max(self.v1_peak, abs(v1))
                self.v2_peak = max(self.v2_peak, abs(v2))
                if (v1, v2) != (self.model.v1, self.model.v2):
                    self.errors += 1
                    if self.errors <= 10:
                        dut._log.error("frame %d: chip v1 %d v2 %d, model v1 %d v2 %d" % (
                            self.checked, v1, v2, self.model.v1, self.model.v2))
            self.checked += 1

    async def next_frame(self):
        """Wait for a frame boundary; returns k, the frame that just started.
        On return it is the middle of frame k's clock 1."""
        await self.dut.frame_tick.value_change
        await ReadOnly()
        k = int(self.dut.frame_count.value)
        await FallingEdge(self.dut.clk)
        return k

    async def frames(self, n):
        if GL:
            n = (n + 7) // 8
        for _ in range(n):
            await self.next_frame()

    def _drive(self):
        self.dut.uio_in.value = self.uio

    def _set(self, bit, value):
        self.uio = (self.uio & ~(1 << bit)) | (int(value) << bit)

    async def spi(self, data):
        """Send bytes; returns (bytes read on MISO, frame the chip acts in).

        Starts on frame k's clock 1. SCK of bit i rises at clock 8i + 9 and
        the chip sees the edge 2 clocks later, so the last bit of a message of
        n bytes is taken on clock 8(8n - 1) + 11, together with its pulse
        (hit_done or stop). A pulse on clock c is acted on at the end of frame
        (c + 1) // F, so the model gets it before the next frame."""
        k = await self.next_frame()
        while k < self.ready:
            k = await self.next_frame()
        assert str(self.dut.uio_out.value[5]) == "0", "BUSY is high"
        start = k * F
        self._set(CS, 0)
        self._drive()
        await ClockCycles(self.dut.clk, HALF, rising=False)
        rx = []
        for byte in data:
            r = 0
            for i in range(8):
                self._set(SCK, 0)
                self._set(MOSI, (byte >> (7 - i)) & 1)
                self._drive()
                await ClockCycles(self.dut.clk, HALF, rising=False)
                r = (r << 1) | (str(self.dut.uio_out.value[MISO]) == "1")
                self._set(SCK, 1)
                self._drive()
                await ClockCycles(self.dut.clk, HALF, rising=False)
            rx.append(r)
        self._set(SCK, 0)
        self._drive()
        await ClockCycles(self.dut.clk, HALF, rising=False)
        self._set(CS, 1)
        self._drive()
        pulse = start + 8 * (8 * len(data) - 1) + 11
        assert 2 < (pulse + 1) % F < F - 2, "message ends too close to a frame boundary"
        return rx, k, (pulse + 1) // F

    async def hit(self, ch, params):
        """Send a HIT. The chip picks a slot at the end of frame m and writes it
        during frame m + 1; like the bridge, wait until BUSY is low again."""
        payload = M.hit_bytes(*params)
        _, _, m = await self.spi((M.CMD_HIT | ch,) + payload)
        self.at(m + 1, lambda: self.model.hit(ch, payload))
        self.ready = m + 2
        return m

    async def stop(self):
        _, _, m = await self.spi((M.CMD_STOP,))
        self.at(m + 1, self.model.stop)

    async def read(self, reg):
        """Returns (value, frame k): the answer is taken during frame k."""
        rx, k, _ = await self.spi((M.CMD_READ | reg, 0x00))
        assert (k * F + 67) // F == k
        return rx[1], k

    async def pins(self, mask):
        """Set the pin triggers at the start of a frame; the chip sees them at its end."""
        k = await self.next_frame()
        self.ui = mask
        self.dut.ui_in.value = mask
        self.at(k + 1, lambda: self.model.set_pins(mask))

    async def finish(self, frames=4):
        await self.frames(frames)
        assert self.checked > 0
        assert self.errors == 0, "%d of %d frames differ from the model" % (self.errors, self.checked)
        self.dut._log.info("%d frames match the model; slot choices %s" % (self.checked, self.model.choices))


def signed(value, bits):
    v = int(value)
    return v - (1 << bits) if v >> (bits - 1) else v


def random_params(rng):
    return (rng.randrange(256), rng.randrange(16), rng.randrange(16), rng.randrange(16), rng.randrange(16))


@cocotb.test()
async def test_registers(dut):
    """ID and VERSION registers; STATUS is 0 before any hit."""
    b = Bench(dut)
    await b.start()
    assert (await b.read(M.REG_ID))[0] == M.CHIP_ID
    version = (await b.read(M.REG_VERSION))[0]
    assert version == (M.VERSION << 4) | VOICES, hex(version)
    assert VOICES != 2 or version == 0x22, hex(version)     # second-order DAC, 2 voices
    assert (await b.read(M.REG_STATUS))[0] == 0
    await b.finish()


@cocotb.test()
async def test_presets(dut):
    """Each drum with its preset, one after the other, as on the chip's pin triggers."""
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    for ch in range(8):
        await b.hit(ch, M.PRESETS[ch])
        await b.frames(150)
    await b.finish()


@cocotb.test(skip=not STATUS)
async def test_status(dut):
    """STATUS shows the drums that sound; the 7-segment display follows it."""
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    await b.hit(M.BASS, M.PRESETS[M.BASS])
    await b.hit(M.HH_OPEN, M.PRESETS[M.HH_OPEN])
    await b.frames(2)
    value, k = await b.read(M.REG_STATUS)
    await b.frames(2)
    want = b.statuses[k]
    assert value == want == (1 << M.BASS) | (1 << M.HH_OPEN), (value, want)
    assert int(dut.uo_out.value) & 0x7F == (1 << M.BASS) | (1 << 6)
    await b.finish()


@cocotb.test()
async def test_random_hits(dut):
    """Random channels and parameters, voices stolen and retriggered, a STOP."""
    rng = random.Random(1)
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    for n in range(60):
        await b.hit(rng.randrange(8), random_params(rng))
        await b.frames(rng.choice((0, 0, 1, 3, 10, 40)))
        if n == 40:
            await b.stop()
    await b.frames(100)
    await b.finish()


@cocotb.test()
async def test_long_sounds(dut):
    """Slow decays and sweeps over a few thousand frames."""
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    await b.hit(M.BASS, (20, 7, 4, 1, 15))
    await b.hit(M.SNARE, (80, 9, 6, 11, 13))
    await b.hit(M.CYMBAL, M.PRESETS[M.CYMBAL])
    await b.hit(M.BIG_TOM, (40, 7 | 8, 5, 3, 15))
    await b.frames(3000)
    await b.finish()


@cocotb.test(skip=not TRIGGERS)
async def test_pin_triggers(dut):
    """Rising edges on ui_in play the presets; several at once are taken in turn."""
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    await b.pins(1 << M.BASS)
    await b.frames(5)
    await b.pins(0)
    await b.frames(30)
    await b.pins((1 << M.SNARE) | (1 << M.HH_CLOSED) | (1 << M.BASS))
    await b.frames(10)
    await b.pins(1 << M.SNARE)
    await b.frames(10)
    await b.pins(0xFF)
    await b.frames(40)
    await b.pins(0)
    await b.frames(200)
    await b.finish()


@cocotb.test(skip=bool(STATUS))
async def test_display_digit(dut):
    """Without STATUS the display shows the digit of the channel last hit."""
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    for ch in (4, 0, 7, 2):
        await b.hit(ch, M.PRESETS[ch])
        assert int(dut.uo_out.value) & 0x7F == DIGITS[ch]
    await b.finish()


@cocotb.test()
async def test_silence(dut):
    """Silence is the clean mid-scale pattern: 48 ones in every frame after
    reset, and again after a decay or a STOP (the loop restarts at (0, -1))."""
    b = Bench(dut)
    await b.start()
    await b.frames(4)
    await b.hit(M.CYMBAL, (255, 0, 4, 15, 15))     # short and loud
    await b.hit(M.BASS, (20, 6, 15, 1, 15))        # long
    await b.frames(300)
    await b.stop()
    await b.frames(6)
    n = b.checked
    await b.frames(20)
    await b.finish()
    assert (b.model.v1, b.model.v2) == (0, M.SD_V2_RESET)
    assert b.checked > n


def dac_params(rng):
    """Random sounds, biased towards what stresses the DAC: full level, slow
    decays, pitch corners, all balances, metal and drum noise."""
    pitch = rng.choice((0, 1, 31, 32, 128, 224, 254, 255, rng.randrange(256)))
    sweep = rng.choice((0, 0, 7, rng.randrange(8)))
    decay = rng.choice((15, 13, 11, 9, rng.randrange(16)))
    balance = rng.randrange(16)
    level = rng.choice((15, 15, 15, 14, rng.randrange(16)))
    return (pitch, sweep, decay, balance, level)


@cocotb.test()
async def test_dac(dut):
    """Second-order DAC under long random traffic: both voices at full level
    for long stretches, every balance, pitch corners, rapid retriggers, STOPs
    and decays to silence. Every frame must match the model (count of 1s and,
    on the RTL, both integrators); the integrators must stay inside the
    proven bound and the v1 clamp must never act."""
    total = 3_000 if GL else int(os.environ.get("DAC_FRAMES", "100000"))
    rng = random.Random(2026)
    b = Bench(dut)
    await b.start()
    await b.frames(2)
    while b.checked < total:
        r = rng.random()
        if r < 0.55:                                    # rapid retriggers and steals
            await b.hit(rng.randrange(8), dac_params(rng))
        elif r < 0.75:                                  # both voices loud and sustained
            await b.hit(rng.choice((0, 1, 2, 3, 4)), dac_params(rng))
            await b.hit(rng.choice((5, 6)), dac_params(rng))
            await b.frames(rng.choice((500, 2000, 6000)))
        elif r < 0.80:
            await b.stop()
        elif r < 0.85:                                  # let everything decay to silence
            await b.frames(rng.choice((3000, 12000)))
        else:
            await b.frames(rng.choice((0, 1, 2, 5, 20, 100, 400)))
    await b.finish()
    lo, hi = M.sd2_bounds()
    m = b.model
    chip = ("gate level: integrators not visible" if GL else
            "chip at frame ends |v1| %d |v2| %d (equal to the model's)" % (b.v1_peak, b.v2_peak))
    dut._log.info("DAC over %d frames: model peaks |v1| %d (%.2f x 4096), |v2| %d (%.2f x 4096), "
                  "clamps %d; %s; proven |v2| bound %d"
                  % (b.checked, m.v1_peak, m.v1_peak / 4096, m.v2_peak, m.v2_peak / 4096,
                     m.v1_clamps, chip, max(-lo, hi)))
    assert m.v1_clamps == 0, "the v1 clamp acted"
    assert m.v1_peak < -M.SD_V1_MIN
    assert -m.v2_peak >= lo and m.v2_peak <= hi
    assert GL or (b.v1_peak <= m.v1_peak and b.v2_peak <= m.v2_peak)
