# -*- coding: utf-8 -*-
"""UDS Autorhythm patterns, transcribed from the Rokton/Formanta UDS manual.

Source: "ЭУС «Роктон». Нотное приложение. Ритмические рисунки." (the manual's
notation appendix: 16 rhythm patterns, two staves each).

Runs on CPython 3 and MicroPython (RP2040 bridge, ESP32 panel).

Grid format
-----------
One line per instrument, in the score's staff order, one character per step:

    x  hit        .  no hit        o  open hi-hat (XX row only)

Spaces and "|" are ignored; they only mark beats and bars for readability.
Tied notes in the score are not retriggered. The score has no accent marks.

Banks
-----
PATTERNS (bank A) holds the 16 original Autorhythm patterns, unchanged.
BANK_B holds patterns beyond the original. Bank B grids may also use

    X  accented hit        O  accented open hi-hat

and may be any whole number of beats up to 32 steps. Each bank B entry has a
default tempo (bpm). midi_to_grid.py converts General MIDI drum files into
this format.

Step resolution
---------------
    4/4 patterns           32 steps = 2 bars of sixteenths       (4 steps per beat)
    Waltz (3/4)            24 steps = 4 bars of eighths          (2 steps per beat)
    Slow rock, Swing       24 steps = 2 bars of triplet eighths  (3 steps per beat)
    Lezginka (6/8)         24 steps = 4 bars of eighths          (3 steps per dotted-quarter beat)

The original PROM has 32 step addresses per pattern; how it shortened the
24-step patterns is not known yet (a PROM dump would show it).

Channel numbers match the UDS-1x1 chip protocol (bit n of a step byte = channel n).
"""

SNARE = 0       # МБ  малый барабан
SMALL_TOM = 1   # МТ  малый том
MID_TOM = 2     # СТ  средний том
BIG_TOM = 3     # БТ  большой том
BASS = 4        # ББ  большой барабан
CYMBAL = 5      # Т   тарелка
HH_CLOSED = 6   # ХХ  хай-хэт
HH_OPEN = 7     # ХХ  хай-хэт, marked "o" in the score

CHANNEL_NAMES = ("snare", "small tom", "middle tom", "big tom",
                 "bass drum", "cymbal", "hi-hat closed", "hi-hat open")

ROWS = ("T", "XX", "MB", "BB", "MT", "CT", "BT")   # score order, top to bottom
ROW_CHANNEL = {"T": CYMBAL, "XX": HH_CLOSED, "MB": SNARE, "BB": BASS,
               "MT": SMALL_TOM, "CT": MID_TOM, "BT": BIG_TOM}

MAX_STEPS = 32


def _p(name, name_ru, meter, steps_per_beat, grid, notes="", bpm=None):
    return {"name": name, "name_ru": name_ru, "meter": meter,
            "steps_per_beat": steps_per_beat, "grid": grid, "notes": notes, "bpm": bpm}


# Pattern order follows the manual's list (and the style-button codes 0-15).
PATTERNS = (
    _p("Rock 1", "Рок 1", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  x.x. x.x. x.x. x.x. | x.x. x.x. x.x. x.x.
        MB  .... x.x. .... x... | .... x.x. .... x...
        BB  x... .... x... .... | x... .... x... ....
        MT  x.xx .... .... .... | x... .... .... ....
        CT  .... x.x. .... x.x. | ..x. x... x... x.xx
        BT  .... .... xxxx .... | ...x ..x. ..x. ....
    """),
    _p("Rock 2", "Рок 2", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  x.xx x.xx x.xx x.xx | x.xx x.xx x.xx xxox
        MB  .... x... .... x... | .... x... .... x...
        BB  x... ..x. x..x ..x. | x... ..x. x..x ..x.
        MT  ..xx .x.x .xx. .... | ..xx .x.x .xx. ....
        CT  .... x... x..x ..x. | .... x... x..x ..xx
        BT  x... .... .... x... | x... .... .... x...
    """),
    _p("Rock 3", "Рок 3", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  x.x. x.x. x.x. x.x. | x.x. x.x. x.x. x.o.
        MB  .... x... .... x... | .... x... .... x...
        BB  x.x. ..x. x.x. ..x. | x.x. ..x. x.x. ..x.
        MT  xx.x x... .... .... | xx.x x... .... ....
        CT  .... ..xx .xx. .... | .... ..xx .xx. ....
        BT  .... .... .... xxx. | .... .... .... xxx.
    """),
    _p("Rock 4", "Рок 4", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  x.x. x.x. x.x. x.x. | x.x. x.x. x.x. x.x.
        MB  .... x... .... x... | .... x... .... x...
        BB  x..x .x.x x..x .x.x | x..x .x.x x..x .x.x
        MT  .x.. .x.. .... .... | .x.. .x.. .... ....
        CT  .... .... .xxx xx.. | .... .... .xxx xx..
        BT  x..x .... .... ..x. | x..x .... .... ..x.
    """, "Read from the full-page scan (lower resolution than the close-ups)."),
    _p("Rumba", "Румба", "4/4", 4, """
        T   x... .... .... .... | .... .... .... ....
        XX  ..xx x.x. x.x. x.x. | x.xx x.x. x.x. x.x.
        MB  .... x... ..x. ..x. | .... ..x. ..x. ....
        BB  x... ..x. .... x... | x... .... x... ..x.
        MT  x... .... .... .... | .... .... x... ....
        CT  .... .... x... .... | x... .... .... x...
        BT  .... .... .... x.x. | .... ..x. ..x. ..x.
    """),
    _p("Samba", "Самба", "4/4", 4, """
        T   x... x... x... ..x. | ..x. ..x. x... ....
        XX  ..x. ..x. ..x. x... | x... x... ..x. x.x.
        MB  .... ..x. .... x... | .... ..x. .... x...
        BB  x... .... x... .... | x... .... x... ....
        MT  x... x... .... ..x. | ..x. .... .... ....
        CT  .... .... x... .... | .... ..x. .... ....
        BT  .... .... .... .... | .... .... x... ....
    """),
    _p("Bossa nova", "Боссанова", "4/4", 4, """
        T   x.x. ..x. ..x. ..x. | x.x. ..x. ..x. ..x.
        XX  .... x... .... x... | .... x... .... x...
        MB  x... ..x. .... x... | .... x... ..x. ....
        BB  x... ..x. x... ..x. | x... ..x. x... ..x.
        MT  ..x. .... .... .... | .... ..x. ..x. ....
        CT  .... ..x. .... ..x. | .... .... x... ..x.
        BT  x... .... ..x. .... | x... .... .... x...
    """),
    _p("Beguine", "Бегин", "4/4", 4, """
        T   x... .... .... .... | .... .... .... ....
        XX  .... x... .... x... | .... x... .... x...
        MB  ..xx x.x. ..x. ..x. | ..xx x.x. ..x. ..x.
        BB  x... .... x... x... | x... .... x... x...
        MT  .... ..x. .... .... | .... .... x... ....
        CT  .... .... ..x. .... | x... ..x. .... x...
        BT  x... .... .... x... | .... .... .... .x.x
    """),
    _p("Waltz", "Вальс", "3/4", 2, """
        T   x..... ...... ...... ......
        XX  ..x.x. x.x.x. x.x.x. x.x.x.
        MB  ..x.x. ..x.x. ..x.x. ..x.x.
        BB  x..... x..... x..... x.....
        MT  .x...x ...x.. .x...x ...x..
        CT  x...x. x....x x...x. x....x
        BT  ...x.. ....x. ...x.. ....x.
    """),
    _p("Slow rock", "Слоу рок", "12/8", 3, """
        T   x.. ... ... ... | ... ... ... ...
        XX  .xx xxx xxx xxo | xxx xxx xxx xxx
        MB  ... x.. ... x.. | ... x.. ... x..
        BB  x.. ..x x.. ..x | x.. ..x x.. .xx
        MT  ... ... x.. ... | ... ... x.. x..
        CT  ... x.. ... ..x | ... x.. ... .x.
        BT  x.x ..x ..x xx. | x.x ..x ..x ..x
    """, "Steps 9-10 big tom are a guess: an ink blot and a paper fold cover them."),
    _p("Swing", "Свинг", "4/4 swing", 3, """
        T   x.. x.x x.. x.x | x.. x.x x.. x.x
        XX  ... ... ..x ... | ... ... ... ...
        MB  ... x.. ... ..x | ..x ... ..x ...
        BB  x.. ... ... ... | ... ... ... ..x
        MT  .x. x.. ... x.. | .x. x.. ... x..
        CT  ... ..x ... .x. | ... ..x ... .x.
        BT  x.x ... .xx ..x | x.x ... .xx ..x
    """, "Score writes swung eighths at two thirds of the beat; read as a triplet grid."),
    _p("Lezginka", "Лезгинка", "6/8", 3, """
        T   x.. ... ... ... | ... ... ... ...
        XX  ... x.. x.. x.. | x.. x.. x.. x..
        MB  xxx x.x xxx x.x | xxx x.x x.x x.x
        BB  x.. x.. x.. x.. | x.. x.. x.. x..
        MT  ... ... x.. ... | ... ... x.x .x.
        CT  ..x xxx ..x xxx | ..x xxx ... ...
        BT  x.. ... ... ... | x.. ... ... ...
    """, "Read from the full-page scan (lower resolution than the close-ups)."),
    _p("March", "Марш", "4/4", 4, """
        T   x... .... .... .... | .... .... .... ....
        XX  .... x... .... x... | .... x... .... x...
        MB  ..x. ..x. ..x. ..x. | ..x. ..x. ..xx x.x.
        BB  x... x... x... x... | x... x... x... x...
        MT  .x.x x.x. .... xx.x | .x.x x.x. .... xx.x
        CT  ..x. .x.. x... ..x. | ..x. .x.. x... ..x.
        BT  x... ...x .... .... | x... ...x .... ....
    """),
    _p("Disco", "Диско", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  x.o. x.o. x.o. x.o. | x.o. x.o. xxo. x.o.
        MB  .... x... .... x... | .... x... .... x...
        BB  x... x... x... x... | x... x... x... x...
        MT  .... .... .... ..xx | .... .... .... ..xx
        CT  xxx. x.xx .... .... | xxx. x.xx .... ....
        BT  .... .... ..xx x... | .... .... ..xx x...
    """),
    _p("Tango", "Танго", "4/4", 4, """
        T   x... .... .... .... | .... .... .... ....
        XX  .... x... x... x.o. | x... x... x... x.o.
        MB  x... x... x... ..x. | x... x... x... ..x.
        BB  x... x... x... ..x. | x... x... x... ..x.
        MT  .... ..x. .... .... | ..x. ..x. .... ....
        CT  x... .... x... .... | x... .... x... ....
        BT  .... .... .... x... | .... .... .... x...
    """),
    _p("16 beat", "16 бит", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  xxo. xxo. xxo. xxo. | xxo. xxo. xxo. xxo.
        MB  .... x... .... x... | .... x... ...x ....
        BB  xx.. .x.x .... ...x | .xx. ..x. x... ...x
        MT  x..x x..x .x.. x..x | .x.. x..x ..x. .x..
        CT  .xx. .xx. x.xx .xx. | x.xx .xx. xx.x ...x
        BT  .... .... .... .... | .... .... .... x...
    """),
)


# Bank B: patterns beyond the original UDS (up to 16, picked with a bank switch).
BANK_B = (
    _p("House", "Хаус", "4/4", 4, """
        T   .... .... .... .... | .... .... .... ....
        XX  X.x. X.x. X.x. X.O. | X.x. X.x. X.x. X.x.
        MB  .... x... .... x... | .... x... .... x...
        BB  x... x... x... x... | x... x... x... x...
        MT  .... .... .... .... | .... .... .... ....
        CT  .... .... .... .... | .... .... .... ....
        BT  .... .... .... .... | .... .... .... ....
    """, "Generic house groove shared by six example MIDI files named after GusGus songs "
         "(Over, Crossfade, Arabian Horse, Deep Inside, Higher, Within You; 123-130 BPM); "
         "not a transcription of those songs. Snare and clap merged onto the snare.", bpm=124),
    _p("Downtempo", "Даунтемпо", "4/4", 4, """
        T   .... .... .... ....
        XX  X.x. X.x. X.x. X.x.
        MB  .... x... .... x...
        BB  X... .... x... ....
        MT  .... .... .... ....
        CT  .... .... .... ....
        BT  .... .... .... ....
    """, "Generic downtempo groove shared by three example MIDI files named after GusGus songs "
         "(Polyesterday, Believe, Teenage Sensation; 100-105 BPM); not a transcription "
         "of those songs.", bpm=102),
)

BANKS = (PATTERNS, BANK_B)


def parse(grid):
    """Return {row label: string of step characters} for one grid."""
    rows = {}
    for line in grid.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        label, cells = line.split(None, 1)
        rows[label] = "".join(c for c in cells if c not in " |")
    return rows


def length(index, bank=PATTERNS):
    rows = parse(bank[index]["grid"])
    return len(rows["XX"])


def _bits(index, bank, hit_chars, open_chars):
    rows = parse(bank[index]["grid"])
    out = [0] * len(rows["XX"])
    for label in ROWS:
        cells = rows[label]
        for s in range(len(cells)):
            c = cells[s]
            if c in hit_chars:
                out[s] |= 1 << ROW_CHANNEL[label]
            elif c in open_chars:
                out[s] |= 1 << HH_OPEN
    return out


def steps(index, bank=PATTERNS):
    """Step bytes for one pattern; bit n set = trigger channel n on that step."""
    return _bits(index, bank, "xX", "oO")


def accents(index, bank=PATTERNS):
    """Accent bytes for one pattern; bit n set = channel n is accented on that step."""
    return _bits(index, bank, "X", "O")


def prom():
    """512-byte table in the original PROM layout: address = pattern * 32 + step.

    Steps past a pattern's length are 0. The bit order is ours (bit n = channel n);
    the original PROM's bit order is not known yet.
    """
    table = bytearray(len(PATTERNS) * MAX_STEPS)
    for p in range(len(PATTERNS)):
        for s, value in enumerate(steps(p)):
            table[p * MAX_STEPS + s] = value
    return table


def _check_bank(bank, bank_a):
    for pat in bank:
        rows = parse(pat["grid"])
        if tuple(sorted(rows)) != tuple(sorted(ROWS)):
            raise ValueError("%s: rows %s" % (pat["name"], sorted(rows)))
        n = len(rows["XX"])
        if bank_a and n not in (24, 32):
            raise ValueError("%s: %d steps" % (pat["name"], n))
        if n < 1 or n > MAX_STEPS:
            raise ValueError("%s: %d steps, allowed 1-%d" % (pat["name"], n, MAX_STEPS))
        if n % pat["steps_per_beat"]:
            raise ValueError("%s: length not a whole number of beats" % pat["name"])
        if not bank_a and not pat["bpm"]:
            raise ValueError("%s: bank B pattern needs a bpm" % pat["name"])
        for label in ROWS:
            cells = rows[label]
            if len(cells) != n:
                raise ValueError("%s %s: %d steps, expected %d" % (pat["name"], label, len(cells), n))
            allowed = "x.o" if label == "XX" else "x."
            if not bank_a:
                allowed += "XO" if label == "XX" else "X"
            for c in cells:
                if c not in allowed:
                    raise ValueError("%s %s: bad character %r" % (pat["name"], label, c))
    if len(bank) > 16:
        raise ValueError("a bank holds at most 16 patterns")


def check():
    """Raise ValueError if any grid is malformed. Returns the number of patterns."""
    _check_bank(PATTERNS, True)
    _check_bank(BANK_B, False)
    return len(PATTERNS) + len(BANK_B)


if __name__ == "__main__":
    print("%d patterns OK" % check())
    for letter, bank in (("A", PATTERNS), ("B", BANK_B)):
        print("Bank %s" % letter)
        for p, pat in enumerate(bank):
            hits = sum(bin(v).count("1") for v in steps(p, bank))
            acc = sum(bin(v).count("1") for v in accents(p, bank))
            print("%2d  %-11s %-10s %2d steps  %d per beat  %3d hits  %2d accents  %s" % (
                p, pat["name"], pat["meter"], length(p, bank), pat["steps_per_beat"], hits, acc,
                pat["notes"]))
