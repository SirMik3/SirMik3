#!/usr/bin/env python3
"""
Animated terminal profile card, built on a strict character grid.

Grid metrics reverse-engineered from a console2svg capture:
    font-size      14px
    cell advance    8.4px   (exactly 0.6em)
    line height    18px
    baseline       cell_top + 14
    chrome         27px title bar, 8px body padding, 10px corner radius

The critical technique is textLength + lengthAdjust="spacing" on every run:
it pins a run to an exact pixel width, so the character grid survives even
when the viewer falls back to a font other than the intended one. Everything
is laid out in (col, row) cell coordinates and converted at render time.

No <style> block and no <script>: colours and metrics are presentation
attributes, so nothing breaks if GitHub's SVG sanitiser strips CSS. Motion is
SMIL, which does run inside an <img>-embedded SVG.

Verify changes in a real browser. cairosvg and most SVG rasterisers ignore
textLength and SMIL, so they will show a broken layout that is actually fine.
"""

import math
import os
import random

# ---------------------------------------------------------------- metrics ---
FS, CW, CH = 14, 8.4, 18      # font size, cell advance, line height
BASE = 14                     # baseline offset within a cell
MARGIN, PAD, TITLEBAR = 20, 8, 27
COLS, ROWS = 95, 33           # 95 * 8.4 = 798.0 exactly

WIN_W = COLS * CW + 2 * PAD
WIN_H = ROWS * CH + 2 * PAD + TITLEBAR
W = WIN_W + 2 * MARGIN + 1
H = WIN_H + 2 * MARGIN + 1

X0 = MARGIN + 1 + PAD                 # x of column 0
Y0 = MARGIN + 1 + TITLEBAR + PAD      # y of row 0's top edge

FONT = ('ui-monospace,"JetBrains Mono","Cascadia Mono","Segoe UI Mono",'
        '"Noto Sans Mono","SFMono-Regular",Menlo,Consolas,monospace')

# Candles are drawn as rects by default: pixel-identical to the block glyphs
# but immune to a viewer's font lacking U+2588/U+2502. Flip to True to emit
# real characters instead.
GLYPH_CANDLES = False

# ----------------------------------------------------------------- palette --
FRAME, BORDER, BAR_BG, BODY = "#1f1f1f", "#3a3a3a", "#2c2c2c", "#1e1e1e"
FG, DIM, RULE, TRACK = "#d4d4d4", "#7c7c7c", "#333333", "#2a2a2a"
RED, YELLOW, GREEN = "#ff5f57", "#febc2e", "#28c840"
BLUE, CYAN, MAGENTA = "#4ea1ff", "#29b8db", "#c678dd"
UP, DOWN = "#26a65b", "#e0483d"       # candle bodies, slightly muted

out = []
add = out.append


def px(col, row):
    """Cell coordinate -> (x, baseline y)."""
    return X0 + col * CW, Y0 + row * CH + BASE


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run(col, row, text, fill=FG, bold=False):
    """One text run locked to an exact width, so columns can never drift."""
    x, y = px(col, row)
    weight = ' font-weight="bold"' if bold else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}"{weight} '
            f'textLength="{len(text) * CW:.1f}" lengthAdjust="spacing" '
            f'xml:space="preserve">{esc(text)}</text>')


def block(col, row, n_cells, fill, inner="", inset=0):
    """A run of coloured cells — how a terminal paints a background."""
    x, _ = px(col, row)
    return (f'<rect x="{x:.1f}" y="{Y0 + row * CH + inset}" '
            f'width="{n_cells * CW:.1f}" height="{CH - inset * 2}" fill="{fill}" '
            f'shape-rendering="crispEdges">{inner}</rect>')


def rule(row, col=0, span=COLS):
    x, _ = px(col, row)
    return (f'<rect x="{x:.1f}" y="{Y0 + row * CH + 9}" width="{span * CW:.1f}" '
            f'height="1" fill="{RULE}" shape-rendering="crispEdges"/>')


def fade(el, begin, dur=0.16):
    return (f'<g opacity="0">{el}<animate attributeName="opacity" from="0" to="1" '
            f'begin="{begin}s" dur="{dur}s" fill="freeze"/></g>')


PROMPT = [("[", DIM, False), ("michael@arch", GREEN, True), (" ", DIM, False),
          ("~/portfolio", BLUE, False), ("]$ ", DIM, False)]
PROMPT_LEN = sum(len(t) for t, _, _ in PROMPT)


def prompt(row):
    col, parts = 0, []
    for text, color, bold in PROMPT:
        parts.append(run(col, row, text, color, bold))
        col += len(text)
    return "".join(parts)


_typed = 0


def typed(row, text, begin, col=PROMPT_LEN, fill=FG):
    """Reveal a command left-to-right behind an expanding clip, like typing."""
    global _typed
    _typed += 1
    uid = f"type{_typed}"
    x, _ = px(col, row)
    dur = max(0.4, len(text) * 0.05)
    return (f'<clipPath id="{uid}"><rect x="{x:.1f}" y="{Y0 + row * CH}" width="0" '
            f'height="{CH}"><animate attributeName="width" from="0" '
            f'to="{len(text) * CW:.1f}" begin="{begin}s" dur="{dur:.2f}s" '
            f'fill="freeze"/></rect></clipPath>'
            f'<g clip-path="url(#{uid})">{run(col, row, text, fill)}</g>')


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

# ------------------------------------------------------------ chart layout --
CHART_ROW, CHART_ROWS = 16, 11       # plot occupies rows 16..26
AXIS_COL, PLOT_COL, STEP = 6, 8, 2   # y-axis gutter, first candle, cells/candle
PLOT_TOP = Y0 + CHART_ROW * CH
PLOT_H = CHART_ROWS * CH

lo = min(b[2] for b in BARS) * 0.94
hi = max(b[1] for b in BARS) * 1.06
LOG_LO, LOG_HI = math.log(lo), math.log(hi)


def y_of(v):
    """Price -> pixel y, on a log scale (17 years of compounding needs one)."""
    frac = (math.log(v) - LOG_LO) / (LOG_HI - LOG_LO)
    return PLOT_TOP + (1 - frac) * PLOT_H


def snap(y, mode="round"):
    """Clamp to a cell edge so candles read as block characters. Wick ends
    round outward (floor/ceil), otherwise a wick collapses into its body and
    the high/low information disappears."""
    raw = (y - PLOT_TOP) / CH
    r = {"round": round, "up": math.floor, "down": math.ceil}[mode](raw)
    return PLOT_TOP + max(0, min(CHART_ROWS, r)) * CH


def value_at_row(r):
    frac = 1 - (r * CH) / PLOT_H
    return math.exp(LOG_LO + frac * (LOG_HI - LOG_LO))


def candle(i, o, h, l, c):
    """One OHLC bar: a 1-cell body with a centred wick behind it."""
    col = PLOT_COL + i * STEP
    x, _ = px(col, 0)
    color = UP if c >= o else DOWN
    top, bot = snap(y_of(max(o, c))), snap(y_of(min(o, c)))
    if bot - top < CH:                       # doji: never collapse to nothing
        bot = top + CH
    wick_t, wick_b = snap(y_of(h), "up"), snap(y_of(l), "down")

    if GLYPH_CANDLES:
        parts = []
        for yy in range(int(wick_t), int(wick_b), CH):
            r = CHART_ROW + (yy - PLOT_TOP) // CH
            inside = top <= yy < bot
            parts.append(run(col, int(r), "\u2588" if inside else "\u2502", color))
        return "".join(parts)

    return (f'<rect x="{x + CW / 2 - 1:.1f}" y="{wick_t:.1f}" width="2" '
            f'height="{max(1, wick_b - wick_t):.1f}" fill="{color}" '
            f'shape-rendering="crispEdges"/>'
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{CW:.1f}" '
            f'height="{bot - top:.1f}" fill="{color}" '
            f'shape-rendering="crispEdges"/>')


# ---------------------------------------------------------------- backdrop --
add('<defs><linearGradient id="desk" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0%" stop-color="#20243a"/>'
    '<stop offset="55%" stop-color="#171a2b"/>'
    '<stop offset="100%" stop-color="#0d0f19"/></linearGradient>'
    '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
    '<feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" '
    'flood-opacity="0.55"/></filter></defs>')
add(f'<rect width="{W:.0f}" height="{H:.0f}" fill="url(#desk)"/>')

# ------------------------------------------------------------------ window --
add('<g filter="url(#shadow)" opacity="0.97">')
add(f'<rect x="{MARGIN + 0.5}" y="{MARGIN + 0.5}" rx="10" ry="10" '
    f'width="{WIN_W:.0f}" height="{WIN_H:.0f}" fill="{FRAME}" stroke="{BORDER}"/>')
add(f'<rect x="{MARGIN + 1}" y="{MARGIN + 1}" rx="9" ry="9" width="{WIN_W - 1:.0f}" '
    f'height="{TITLEBAR}" fill="{BAR_BG}"/>')
for i, c in enumerate([RED, YELLOW, GREEN]):
    add(f'<circle cx="{MARGIN + 14 + i * 16}" cy="{MARGIN + 14}" r="5" fill="{c}"/>')
add(f'<text x="{W / 2:.0f}" y="{MARGIN + 18}" fill="{DIM}" font-size="12" '
    f'text-anchor="middle">michael@arch: ~/portfolio</text>')
add(f'<rect x="{MARGIN + 1}" y="{MARGIN + 1 + TITLEBAR}" rx="9" ry="9" '
    f'width="{WIN_W - 1:.0f}" height="{WIN_H - TITLEBAR:.0f}" fill="{BODY}"/>')

# ------------------------------------------------------------ whoami block --
add(fade(prompt(0), 0.15))
add(typed(0, "whoami", 0.4))
add(fade(run(0, 1, "michael", FG, True)
         + run(8, 1, "developer, nicosia cyprus", DIM), 1.1))

# -------------------------------------------------------------- allocation --
add(fade(prompt(3), 1.5))
add(typed(3, "./portfolio --show-allocation", 1.7))

T = 3.2
SYM_C, FOCUS_C, BAR_C, PCT_C, BAR_CELLS = 0, 8, 50, 72, 20

add(fade(run(SYM_C, 5, "SYMBOL", DIM, True), T))
add(fade(run(FOCUS_C, 5, "FOCUS", DIM, True), T))
add(fade(run(BAR_C, 5, "ATTENTION", DIM, True), T))
add(fade(rule(6), T))

TABLE = [
    ("QNT", "market modelling, backtesting",     30, GREEN),
    ("GFX", "real-time rendering, glsl, opengl", 25, MAGENTA),
    ("SYS", "linux internals, networking",       20, BLUE),
    ("SEC", "hardening, network security",       15, YELLOW),
    ("W3",  "vyper (learning)",                  10, CYAN),
]

for i, (sym, focus, pct, color) in enumerate(TABLE):
    row, t = 7 + i, T + 0.25 + i * 0.15
    filled = round(BAR_CELLS * pct / 100)
    add(fade(run(SYM_C, row, sym, color, True), t))
    add(fade(run(FOCUS_C, row, focus, FG), t))
    add(fade(block(BAR_C, row, BAR_CELLS, TRACK, inset=3), t))
    grow = (f'<animate attributeName="width" from="0" to="{filled * CW:.1f}" '
            f'begin="{t + 0.1}s" dur="0.6s" fill="freeze"/>')
    add(fade(block(BAR_C, row, 0, color, grow, inset=3), t))
    add(fade(run(PCT_C, row, f"{pct:>3}%", DIM), t + 0.3))

# ----------------------------------------------------------------- returns --
R = 4.7
add(fade(prompt(13), R - 0.2))
add(typed(13, "./portfolio --returns", R))

C = R + 1.3
first, last = BARS[0][0], BARS[-1][3]
total = (last / first - 1) * 100
cagr = ((last / first) ** (1 / 17.0) - 1) * 100

# caption: says plainly what the series is, so nobody reads it as a track record
add(fade(run(0, 15, "SIM", CYAN, True)
         + run(6, 15, "synthetic gbm", DIM)
         + run(22, 15, f"seed {SEED}  mu {MU:.0%}  sigma {SIGMA:.0%}", DIM)
         + run(52, 15, "2009-2026", DIM)
         + run(64, 15, f"{total:+.0f}%", UP if total >= 0 else DOWN)
         + run(72, 15, f"cagr {cagr:.1f}%", DIM), C - 0.15))

# axes
add(fade(f'<rect x="{px(AXIS_COL, 0)[0]:.1f}" y="{PLOT_TOP}" width="1" '
         f'height="{PLOT_H + 1}" fill="{RULE}" shape-rendering="crispEdges"/>'
         f'<rect x="{px(AXIS_COL, 0)[0]:.1f}" y="{PLOT_TOP + PLOT_H}" '
         f'width="{(PLOT_COL + PERIODS * STEP - AXIS_COL) * CW:.1f}" height="1" '
         f'fill="{RULE}" shape-rendering="crispEdges"/>', C - 0.15))

for r in range(0, CHART_ROWS, 3):                       # y-axis price ticks
    add(fade(run(0, CHART_ROW + r, f"{value_at_row(r):>5.0f}", DIM), C - 0.15))

for i, yr in [(0, "2009"), (8, "2013"), (16, "2017"), (24, "2021"), (34, "2026")]:
    col = PLOT_COL + i * STEP - (2 if i else 0)
    add(fade(run(col, 27, yr, DIM), C + 1.5))

# candles, revealed left to right as if the series were streaming in
candles = "".join(candle(i, *b) for i, b in enumerate(BARS))
x_start, _ = px(PLOT_COL, 0)
sweep = (PERIODS * STEP + 1) * CW
add(f'<clipPath id="sweep"><rect x="{x_start - 2:.1f}" y="{PLOT_TOP - 4}" width="0" '
    f'height="{PLOT_H + 8}"><animate attributeName="width" from="0" to="{sweep:.1f}" '
    f'begin="{C}s" dur="1.7s" fill="freeze"/></rect></clipPath>'
    f'<g clip-path="url(#sweep)">{candles}</g>')

# ------------------------------------------------------------------ footer --
F = C + 1.9
add(fade(run(0, 29, "stack", DIM, True), F))
add(fade(run(8, 29, "c / c++ / python / glsl / react", FG), F))
add(fade(prompt(31), F + 0.25))
blink = (f'<animate attributeName="opacity" values="1;1;0;0" dur="1.06s" '
         f'begin="{F + 0.45}s" repeatCount="indefinite"/>')
add(fade(block(PROMPT_LEN, 31, 1, FG, blink), F + 0.25))

body = "\n".join("  " + o for o in out)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}"
     viewBox="0 0 {W:.0f} {H:.0f}" role="img" font-family='{FONT}' font-size="{FS}"
     aria-label="Terminal window. whoami returns michael, developer, Nicosia Cyprus.
     Attention allocation: real-time rendering and GLSL 30 percent, market modelling
     and backtesting 25 percent, Linux internals and networking 20 percent, hardening
     and network security 15 percent, learning Vyper 10 percent. Then a candlestick
     chart of a synthetic geometric-Brownian-motion price series from 2009 to 2026,
     shown as an illustration and not a record of real trading. Stack: C, C++,
     Python, GLSL, React.">
{body}
  </g>
</svg>
'''

os.makedirs("assets", exist_ok=True)
open("assets/terminal.svg", "w").write(svg)
up = sum(1 for o, _, _, c in BARS if c >= o)
print(f"wrote assets/terminal.svg  ({W:.0f}x{H:.0f} px, {COLS}x{ROWS} cells)")
print(f"series: {PERIODS} half-year candles, {up} up / {PERIODS - up} down, "
      f"{first:.1f} -> {last:.1f} ({total:+.1f}%, cagr {cagr:.1f}%)")