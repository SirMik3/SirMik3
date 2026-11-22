#!/usr/bin/env python3
"""
Animated terminal profile card, built on a strict character grid.

Writes two variants of the same card:
    assets/terminal.svg          95 columns, for desktop
    assets/terminal-compact.svg  48 columns, for phones (README swaps it in
                                 with <picture> + a max-width media query)

Grid metrics reverse-engineered from a console2svg capture:
    font-size      14px
    cell advance    8.4px   (exactly 0.6em)
    line height    18px
    baseline       cell_top + 14
    chrome         27px title bar, 8px body padding, 10px corner radius

The critical technique is textLength on every run (lengthAdjust defaults to
"spacing"): it pins a run to an exact pixel width, so the character grid
survives even when the viewer falls back to a font other than the intended
one. Everything is laid out in (col, row) cell coordinates and converted at
render time.

No <style> block and no <script>: colours and metrics are presentation
attributes, so nothing breaks if GitHub's SVG sanitiser strips CSS. Motion is
SMIL, which does run inside an <img>-embedded SVG.

Rendering cost: the drop shadow is a blur filter, which is expensive. It sits
on a static rect *behind* the window, never on a group that contains animated
content — otherwise every animation frame (and every cursor blink, forever)
re-blurs the whole card.

Verify changes in a real browser. cairosvg and most SVG rasterisers ignore
textLength and SMIL, so they will show a broken layout that is actually fine.
"""

import math
import os
import random

# ---------------------------------------------------------------- metrics ---
FS, CW, CH = 14, 8.4, 18      # font size, cell advance, line height
BASE = 14                     # baseline offset within a cell
PAD, TITLEBAR = 8, 27

FONT = ('ui-monospace,"JetBrains Mono","Cascadia Mono","Segoe UI Mono",'
        '"Noto Sans Mono","SFMono-Regular",Menlo,Consolas,monospace')

# Multiplies every animation start time and duration. 1.0 is the original
# pacing (~8.4s until the cursor appears); 0.6 finishes in ~5s.
PACE = 0.6

# Candles are drawn as rects by default: pixel-identical to the block glyphs
# but immune to a viewer's font lacking U+2588/U+2502. Flip to True to emit
# real characters instead (wide layout only; compact candles are sub-cell).
GLYPH_CANDLES = False

# ----------------------------------------------------------------- palette --
FRAME, BORDER, BAR_BG, BODY = "#1f1f1f", "#3a3a3a", "#2c2c2c", "#1e1e1e"
FG, DIM, RULE, TRACK = "#d4d4d4", "#7c7c7c", "#333333", "#2a2a2a"
RED, YELLOW, GREEN = "#ff5f57", "#febc2e", "#28c840"
BLUE, CYAN, MAGENTA = "#4ea1ff", "#29b8db", "#c678dd"
UP, DOWN = "#26a65b", "#e0483d"       # candle bodies, slightly muted

TABLE = [
    ("QNT", "market modelling, backtesting",     30, GREEN),
    ("GFX", "real-time rendering, glsl, opengl", 25, MAGENTA),
    ("SYS", "linux internals, networking",       20, BLUE),
    ("SEC", "hardening, network security",       15, YELLOW),
    ("W3",  "vyper (learning)",                  10, CYAN),
]
STACK = "c / c++ / python / glsl / react"

# ============================================================ price series ==
# Geometric Brownian motion, seeded so the committed SVG is reproducible.
# Each candle is one half-year; OHLC comes from monthly sub-steps within it,
# which is what gives the wicks a believable length relative to the bodies.
SEED, MU, SIGMA, S0 = 3719, 0.13, 0.26, 100.0
START_YEAR, PERIODS, SUBSTEPS = 2009, 35, 6      # 35 half-years: 2009H1..2026H1


def simulate():
    rnd = random.Random(SEED)
    dt = 0.5 / SUBSTEPS
    drift = (MU - 0.5 * SIGMA ** 2) * dt
    shock = SIGMA * math.sqrt(dt)
    s, bars = S0, []
    for _ in range(PERIODS):
        o = s
        path = []
        for _ in range(SUBSTEPS):
            s *= math.exp(drift + shock * rnd.gauss(0, 1))
            path.append(s)
        bars.append((o, max(max(path), o), min(min(path), o), path[-1]))
    return bars


BARS = simulate()
FIRST, LAST = BARS[0][0], BARS[-1][3]
TOTAL = (LAST / FIRST - 1) * 100
CAGR = ((LAST / FIRST) ** (1 / 17.0) - 1) * 100

LO = min(b[2] for b in BARS) * 0.94
HI = max(b[1] for b in BARS) * 1.06
LOG_LO, LOG_HI = math.log(LO), math.log(HI)
CHART_ROWS = 11
PLOT_H = CHART_ROWS * CH
YEAR_TICKS = [(0, "2009"), (8, "2013"), (16, "2017"), (24, "2021"), (34, "2026")]


def num(v):
    """Shortest faithful number: 70.0 -> '70', 37.4 -> '37.4'."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(sec):
    """Seconds on the original timeline -> SMIL clock value, scaled by PACE."""
    return f"{round(sec * PACE, 3):g}s"


# ================================================================== layouts ==
WIDE = dict(
    name="terminal.svg", cols=95, rows=33, margin=20,  # 95 * 8.4 = 798.0
    cwd="~/portfolio",
    # allocation table: one row per entry
    alloc_two_line=False, sym_c=0, focus_c=8, bar_c=50, pct_c=72, bar_cells=20,
    header=[(0, "SYMBOL"), (8, "FOCUS"), (50, "ATTENTION")],
    # returns caption, chart
    caption=[[(0, "SIM", CYAN, True), (6, "synthetic gbm", DIM),
              (22, f"seed {SEED}  mu {MU:.0%}  sigma {SIGMA:.0%}", DIM),
              (52, "2009-2026", DIM), (64, "TOTAL", None), (72, "CAGR", DIM)]],
    axis_c=6, plot_c=8, step=2, body_inset=0,
)

COMPACT = dict(
    name="terminal-compact.svg", cols=48, rows=39, margin=14,
    cwd="~",
    # allocation table: symbol + focus on one row, the bar underneath
    alloc_two_line=True, sym_c=0, focus_c=5, bar_c=5, pct_c=43, bar_cells=36,
    header=[(0, "SYM"), (5, "FOCUS / ATTENTION")],
    caption=[[(0, "SIM", CYAN, True), (5, "synthetic gbm", DIM),
              (20, f"seed {SEED}", DIM), (31, f"mu {MU:.0%}", DIM),
              (39, f"sigma {SIGMA:.0%}", DIM)],
             [(5, "2009-2026", DIM), (16, "TOTAL", None), (24, "CAGR", DIM)]],
    axis_c=6, plot_c=8, step=1, body_inset=1,
)


# ===================================================================== card ==
class Card:
    def __init__(self, L):
        self.L = L
        self.cols, self.rows, m = L["cols"], L["rows"], L["margin"]
        self.win_w = self.cols * CW + 2 * PAD
        self.win_h = self.rows * CH + 2 * PAD + TITLEBAR
        self.w = round(self.win_w + 2 * m + 1)
        self.h = round(self.win_h + 2 * m + 1)
        self.x0 = m + 1 + PAD                 # x of column 0
        self.y0 = m + 1 + TITLEBAR + PAD      # y of row 0's top edge
        self.out = []
        self.n_typed = 0
        self.prompt_parts = [("[", DIM, False), ("michael@arch", GREEN, True),
                             (" ", DIM, False), (L["cwd"], BLUE, False),
                             ("]$ ", DIM, False)]
        self.prompt_len = sum(len(p[0]) for p in self.prompt_parts)

    def add(self, s):
        self.out.append(s)

    # ---------------------------------------------------------- primitives --
    def px(self, col, row):
        """Cell coordinate -> (x, baseline y)."""
        return self.x0 + col * CW, self.y0 + row * CH + BASE

    def run(self, col, row, text, fill=FG, bold=False):
        """One text run locked to an exact width, so columns can never drift."""
        if len(text) > 0 and col + len(text) > self.cols:
            raise ValueError(f"{text!r} at col {col} overflows {self.cols} cols")
        x, y = self.px(col, row)
        weight = ' font-weight="bold"' if bold else ""
        # Browsers don't inherit xml:space, so it goes on each run whose
        # spaces matter (leading, trailing or doubled) and nowhere else.
        keep = text != text.strip() or "  " in text
        space = ' xml:space="preserve"' if keep else ""
        return (f'<text x="{num(x)}" y="{num(y)}" fill="{fill}"{weight}{space} '
                f'textLength="{num(len(text) * CW)}">{esc(text)}</text>')

    def block(self, col, row, n_cells, fill, inner="", inset=0):
        """A run of coloured cells — how a terminal paints a background."""
        x, _ = self.px(col, row)
        return (f'<rect x="{num(x)}" y="{num(self.y0 + row * CH + inset)}" '
                f'width="{num(n_cells * CW)}" height="{CH - inset * 2}" '
                f'fill="{fill}">{inner}</rect>')

    def rule(self, row):
        x, _ = self.px(0, row)
        return (f'<rect x="{num(x)}" y="{num(self.y0 + row * CH + 9)}" '
                f'width="{num(self.cols * CW)}" height="1" fill="{RULE}"/>')

    @staticmethod
    def fade(el, begin, dur=0.16):
        return (f'<g opacity="0">{el}<animate attributeName="opacity" '
                f'to="1" begin="{t(begin)}" dur="{t(dur)}" fill="freeze"/></g>')

    def prompt(self, row):
        col, parts = 0, []
        for text, color, bold in self.prompt_parts:
            parts.append(self.run(col, row, text, color, bold))
            col += len(text)
        return "".join(parts)

    def typed(self, row, text, begin):
        """Reveal a command left-to-right behind an expanding clip, like typing."""
        self.n_typed += 1
        uid = f"k{self.n_typed}"
        col = self.prompt_len
        x, _ = self.px(col, row)
        dur = max(0.4, len(text) * 0.05)
        return (f'<clipPath id="{uid}"><rect x="{num(x)}" '
                f'y="{num(self.y0 + row * CH)}" width="0" height="{CH}">'
                f'<animate attributeName="width" to="{num(len(text) * CW)}" '
                f'begin="{t(begin)}" dur="{t(dur)}" fill="freeze"/></rect>'
                f'</clipPath><g clip-path="url(#{uid})">'
                f'{self.run(col, row, text)}</g>')

    # --------------------------------------------------------------- chart --
    def y_of(self, v):
        """Price -> pixel y, on a log scale (17 years of compounding needs one)."""
        frac = (math.log(v) - LOG_LO) / (LOG_HI - LOG_LO)
        return self.plot_top + (1 - frac) * PLOT_H

    def snap(self, y, mode="round"):
        """Clamp to a cell edge so candles read as block characters. Wick ends
        round outward (floor/ceil), otherwise a wick collapses into its body
        and the high/low information disappears."""
        raw = (y - self.plot_top) / CH
        r = {"round": round, "up": math.floor, "down": math.ceil}[mode](raw)
        return self.plot_top + max(0, min(CHART_ROWS, r)) * CH

    def candle(self, i, o, h, l, c):
        """One OHLC bar: a 1-cell body with a centred wick behind it."""
        L = self.L
        col = L["plot_c"] + i * L["step"]
        x, _ = self.px(col, 0)
        color = UP if c >= o else DOWN
        top = self.snap(self.y_of(max(o, c)))
        bot = self.snap(self.y_of(min(o, c)))
        if bot - top < CH:                       # doji: never collapse
            bot = top + CH
        wick_t = self.snap(self.y_of(h), "up")
        wick_b = self.snap(self.y_of(l), "down")

        if GLYPH_CANDLES and L["step"] > 1:
            parts = []
            for yy in range(int(wick_t), int(wick_b), CH):
                r = self.chart_row + (yy - self.plot_top) // CH
                inside = top <= yy < bot
                parts.append(self.run(col, int(r), "█" if inside else "│",
                                      color))
            return "".join(parts)

        inset = L["body_inset"]
        return (f'<rect x="{num(x + CW / 2 - 1)}" y="{num(wick_t)}" width="2" '
                f'height="{num(max(1, wick_b - wick_t))}" fill="{color}"/>'
                f'<rect x="{num(x + inset)}" y="{num(top)}" '
                f'width="{num(CW - 2 * inset)}" height="{num(bot - top)}" '
                f'fill="{color}"/>')

    # -------------------------------------------------------------- render --
    def render(self):
        L, add = self.L, self.add
        W, H, m = self.w, self.h, L["margin"]

        # backdrop + window chrome. The shadow is the only filtered element
        # and nothing animated lives inside it, so it is rasterised once.
        add('<defs><linearGradient id="desk" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0%" stop-color="#20243a"/>'
            '<stop offset="55%" stop-color="#171a2b"/>'
            '<stop offset="100%" stop-color="#0d0f19"/></linearGradient>'
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="8" stdDeviation="12" '
            'flood-color="#000000" flood-opacity="0.55"/></filter></defs>')
        add(f'<rect width="{W}" height="{H}" fill="url(#desk)"/>')
        add(f'<rect x="{m + 0.5}" y="{m + 0.5}" rx="10" width="{num(self.win_w)}" '
            f'height="{num(self.win_h)}" fill="{FRAME}" stroke="{BORDER}" '
            f'filter="url(#shadow)"/>')
        add(f'<rect x="{m + 1}" y="{m + 1}" rx="9" width="{num(self.win_w - 1)}" '
            f'height="{TITLEBAR}" fill="{BAR_BG}"/>')
        for i, c in enumerate([RED, YELLOW, GREEN]):
            add(f'<circle cx="{m + 14 + i * 16}" cy="{m + 14}" r="5" fill="{c}"/>')
        add(f'<text x="{W / 2:.0f}" y="{m + 18}" fill="{DIM}" font-size="12" '
            f'text-anchor="middle">michael@arch: {L["cwd"]}</text>')
        add(f'<rect x="{m + 1}" y="{m + 1 + TITLEBAR}" rx="9" '
            f'width="{num(self.win_w - 1)}" height="{num(self.win_h - TITLEBAR)}" '
            f'fill="{BODY}"/>')

        # grid content: crisp edges inherited by every rect in this group
        add('<g shape-rendering="crispEdges">')
        fade, run, row = self.fade, self.run, 0

        # ---------------------------------------------------------- whoami --
        add(fade(self.prompt(row), 0.15))
        add(self.typed(row, "whoami", 0.4))
        add(fade(run(0, row + 1, "michael", FG, True)
                 + run(8, row + 1, "developer, nicosia cyprus", DIM), 1.1))

        # ------------------------------------------------------ allocation --
        row = 3
        add(fade(self.prompt(row), 1.5))
        add(self.typed(row, "./portfolio --show-allocation", 1.7))

        T = 3.2
        for col, label in L["header"]:
            add(fade(run(col, row + 2, label, DIM, True), T))
        add(fade(self.rule(row + 3), T))

        row += 4
        two = L["alloc_two_line"]
        for i, (sym, focus, pct, color) in enumerate(TABLE):
            r, tt = row + i * (2 if two else 1), T + 0.25 + i * 0.15
            br = r + 1 if two else r
            filled = round(L["bar_cells"] * pct / 100)
            add(fade(run(L["sym_c"], r, sym, color, True), tt))
            add(fade(run(L["focus_c"], r, focus, FG), tt))
            add(fade(self.block(L["bar_c"], br, L["bar_cells"], TRACK, inset=3), tt))
            grow = (f'<animate attributeName="width" to="{num(filled * CW)}" '
                    f'begin="{t(tt + 0.1)}" dur="{t(0.6)}" fill="freeze"/>')
            add(fade(self.block(L["bar_c"], br, 0, color, grow, inset=3), tt))
            add(fade(run(L["pct_c"], br, f"{pct:>3}%", DIM), tt + 0.3))

        # --------------------------------------------------------- returns --
        row += len(TABLE) * (2 if two else 1) + 1
        R = 4.7
        add(fade(self.prompt(row), R - 0.2))
        add(self.typed(row, "./portfolio --returns", R))

        C = R + 1.3
        # caption: says plainly what the series is, so nobody reads it as a
        # track record
        row += 2
        for line in L["caption"]:
            parts = []
            for col, text, color, *bold in line:
                if text == "TOTAL":
                    text, color = f"{TOTAL:+.0f}%", UP if TOTAL >= 0 else DOWN
                elif text == "CAGR":
                    text = f"cagr {CAGR:.1f}%"
                parts.append(run(col, row, text, color, bool(bold and bold[0])))
            add(fade("".join(parts), C - 0.15))
            row += 1

        self.chart_row = row
        self.plot_top = self.y0 + row * CH
        step, axis_x = L["step"], self.px(L["axis_c"], 0)[0]

        add(fade(f'<rect x="{num(axis_x)}" y="{num(self.plot_top)}" width="1" '
                 f'height="{PLOT_H + 1}" fill="{RULE}"/>'
                 f'<rect x="{num(axis_x)}" y="{num(self.plot_top + PLOT_H)}" '
                 f'width="{num((L["plot_c"] + PERIODS * step - L["axis_c"]) * CW)}" '
                 f'height="1" fill="{RULE}"/>', C - 0.15))

        for r in range(0, CHART_ROWS, 3):                   # y-axis price ticks
            frac = 1 - (r * CH) / PLOT_H
            v = math.exp(LOG_LO + frac * (LOG_HI - LOG_LO))
            add(fade(run(0, row + r, f"{v:>5.0f}", DIM), C - 0.15))

        for i, yr in YEAR_TICKS:
            col = L["plot_c"] + i * step - (2 if i else 0)
            add(fade(run(col, row + CHART_ROWS, yr, DIM), C + 1.5))

        # candles, revealed left to right as if the series were streaming in
        candles = "".join(self.candle(i, *b) for i, b in enumerate(BARS))
        x_start, _ = self.px(L["plot_c"], 0)
        sweep = (PERIODS * step + 1) * CW
        add(f'<clipPath id="sweep"><rect x="{num(x_start - 2)}" '
            f'y="{num(self.plot_top - 4)}" width="0" height="{PLOT_H + 8}">'
            f'<animate attributeName="width" to="{num(sweep)}" begin="{t(C)}" '
            f'dur="{t(1.7)}" fill="freeze"/></rect></clipPath>'
            f'<g clip-path="url(#sweep)">{candles}</g>')

        # ---------------------------------------------------------- footer --
        row += CHART_ROWS + 2
        F = C + 1.9
        add(fade(run(0, row, "stack", DIM, True) + run(8, row, STACK, FG), F))
        row += 2
        add(fade(self.prompt(row), F + 0.25))
        # hard on/off blink like a real terminal: two repaints per cycle,
        # instead of a continuous fade that repaints every frame
        blink = (f'<animate attributeName="opacity" values="1;0" '
                 f'calcMode="discrete" dur="1.06s" begin="{t(F + 0.45)}" '
                 f'repeatCount="indefinite"/>')
        add(fade(self.block(self.prompt_len, row, 1, FG, blink), F + 0.25))
        add('</g>')

        if row != self.rows - 2:           # keep one blank row below the prompt
            raise ValueError(f"layout used {row + 1} rows, grid has {self.rows}")

        alloc = ", ".join(f"{f} {p} percent" for _, f, p, _ in TABLE)
        label = (f"Terminal window. whoami returns michael, developer, Nicosia "
                 f"Cyprus. Attention allocation: {alloc}. Then a candlestick "
                 f"chart of a synthetic geometric-Brownian-motion price series "
                 f"from 2009 to 2026, shown as an illustration and not a record "
                 f"of real trading. Stack: C, C++, Python, GLSL, React.")
        body = "\n".join(self.out)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
                f'height="{H}" viewBox="0 0 {W} {H}" role="img" '
                f"font-family='{FONT}' font-size=\"{FS}\" "
                f'aria-label="{esc(label)}">\n{body}\n</svg>\n')


os.makedirs("assets", exist_ok=True)
for layout in (WIDE, COMPACT):
    card = Card(layout)
    svg = card.render()
    path = os.path.join("assets", layout["name"])
    with open(path, "w") as f:
        f.write(svg)
    print(f"wrote {path}  ({card.w}x{card.h} px, {card.cols}x{card.rows} cells, "
          f"{len(svg.encode()) / 1024:.1f} KB)")

up = sum(1 for o, _, _, c in BARS if c >= o)
print(f"series: {PERIODS} half-year candles, {up} up / {PERIODS - up} down, "
      f"{FIRST:.1f} -> {LAST:.1f} ({TOTAL:+.1f}%, cagr {CAGR:.1f}%)")
