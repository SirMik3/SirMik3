#!/usr/bin/env python3
"""
Animated terminal profile card, built on a strict character grid.

Writes four variants of the same card, two layouts x two themes:
    assets/terminal.svg                95 columns, desktop, dark
    assets/terminal-light.svg          95 columns, desktop, light
    assets/terminal-compact.svg        48 columns, phones, dark
    assets/terminal-compact-light.svg  48 columns, phones, light
The README chooses between them with <picture> media queries on max-width
and prefers-color-scheme, which GitHub resolves against the viewer's theme.

The card plays a short session against a binary called ./michael:
    whoami                 who, where
    objdump main           main() calls one function per focus area
    hexdump / xxd          its .rodata, strings coloured by kind

The background is transparent: only the window is painted, so the card sits
on whatever GitHub's page colour is (light or dark theme).

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

import os
import struct

# ---------------------------------------------------------------- metrics ---
FS, CW, CH = 14, 8.4, 18      # font size, cell advance, line height
BASE = 14                     # baseline offset within a cell
PAD, TITLEBAR = 8, 27

FONT = ('ui-monospace,"JetBrains Mono","Cascadia Mono","Segoe UI Mono",'
        '"Noto Sans Mono","SFMono-Regular",Menlo,Consolas,monospace')

# Multiplies every animation start time and duration. 1.0 is the original
# pacing; 0.6 finishes in roughly 5s.
PACE = 0.6

# ----------------------------------------------------------------- palette --
# Content is coloured with semantic tokens; each theme maps them to hex at
# render time, so one layout produces both the dark and the light card.
FG, DIM, NUL = "fg", "dim", "nul"     # nul: zero bytes, present but quiet
RED, YELLOW, GREEN = "red", "yellow", "green"
BLUE, CYAN, MAGENTA = "blue", "cyan", "magenta"

THEMES = {
    "dark": dict(
        frame="#1f1f1f", border="#3a3a3a", bar="#2c2c2c", body="#1e1e1e",
        shadow=0.35,
        fg="#d4d4d4", dim="#7c7c7c", nul="#555555",
        red="#ff5f57", yellow="#febc2e", green="#28c840",
        blue="#4ea1ff", cyan="#29b8db", magenta="#c678dd",
    ),
    # GitHub-light-ish: hues darkened so text clears 4.5:1 on white (nul is
    # deliberately faint, as it is in the dark theme)
    "light": dict(
        frame="#f6f8fa", border="#d0d7de", bar="#eaeef2", body="#ffffff",
        shadow=0.12,
        fg="#1f2328", dim="#656d76", nul="#afb8c1",
        red="#cf222e", yellow="#9a6700", green="#1a7f37",
        blue="#0969da", cyan="#1b7c83", magenta="#8250df",
    ),
}
LIGHTS = ("#ff5f57", "#febc2e", "#28c840")   # window buttons, same in both

# ------------------------------------------------------------------ content --
HOST = "michael@arch"
WHOAMI = "systems & security, nicosia cyprus"

# main(): one call per focus area. Encodings are real (call rel32 is computed
# from the target), so the bytes in the wide card disassemble to what they say.
MAIN = 0x1139
FUNCS = [                         # (symbol, address, colour)
    ("reversing",    0x1160, MAGENTA),
    ("exploit_dev",  0x11a0, RED),
    ("linux_kernel", 0x11e0, BLUE),
    ("net_security", 0x1220, YELLOW),
    ("learn_rust",   0x1260, CYAN),
]


def assemble():
    """(addr, raw bytes, mnemonic, operands, symbol colour or None)"""
    ins, pc = [], MAIN

    def emit(raw, mn, ops="", color=None):
        nonlocal pc
        ins.append((pc, raw, mn, ops, color))
        pc += len(raw)

    emit(b"\x55", "push", "rbp")
    emit(b"\x48\x89\xe5", "mov", "rbp,rsp")
    for name, addr, color in FUNCS:
        rel = addr - (pc + 5)
        emit(b"\xe8" + struct.pack("<i", rel), "call", f"{addr:x} <{name}>",
             color)
    emit(b"\x31\xc0", "xor", "eax,eax")
    emit(b"\x5d", "pop", "rbp")
    emit(b"\xc3", "ret")
    return ins


INSNS = assemble()

STACK = "c / c++ / x86-64 asm / python / bash"
TOOLS = "gdb / ghidra / r2 / wireshark / qemu"

# .rodata of ./michael. Starts with the 01 00 02 00 _IO_stdin_used marker that
# glibc puts at the head of every dynamically linked binary's .rodata, ends
# with a switch jump table (signed offsets relative to the table).
RODATA_VADDR = 0x2000
RODATA = [
    (b"\x01\x00\x02\x00", FG),
    (b"/bin/sh\x00", RED),
    (b"take it apart.\x00", GREEN),
    (b"see how it works.\x00", GREEN),
    (b"build the tool you wish existed.\x00", GREEN),
    (b"https://efarov.com\x00", CYAN),
    (8, None),                                       # align to 8
    (b"[*] leaked libc @ %p\n\x00", YELLOW),
    (8, None),
    (struct.pack("<8i", -0x1f60, -0x1f30, -0x1f00, -0x1ec8,
                 -0x1e98, -0x1e60, -0x1e28, -0x1e00), FG),
]


def build_rodata():
    data, colors = bytearray(), []
    for chunk, color in RODATA:
        if isinstance(chunk, int):               # zero padding to alignment
            chunk, color = b"\x00" * (-len(data) % chunk), None
        data += chunk
        colors += [NUL if b == 0 else color for b in chunk]
    return bytes(data), colors


DATA, DATA_COLORS = build_rodata()


def num(v):
    """Shortest faithful number: 70.0 -> '70', 37.4 -> '37.4'."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(sec):
    """Seconds on the unscaled timeline -> SMIL clock value, scaled by PACE."""
    return f"{round(sec * PACE, 3):g}s"


def type_dur(text):
    return max(0.4, len(text) * 0.05)


def ascii_of(b, color):
    """Printable bytes show as themselves in the byte's colour, others as a
    dim dot. A space is colourless so it can join neighbouring runs."""
    if 32 < b < 127:
        return chr(b), color
    if b == 32:
        return " ", None
    return ".", NUL


def hexdump_c(data, colors, base):
    """`hexdump -C`: offset, 16 bytes split 8+8, |ascii|, final offset line."""
    lines = []
    for off in range(0, len(data), 16):
        chunk, cc = data[off:off + 16], colors[off:off + 16]
        text, col = f"{base + off:08x}  ", [DIM] * 8 + [None] * 2
        for j, (b, c) in enumerate(zip(chunk, cc)):
            if j == 8:
                text += " "
                col.append(None)
            text += f"{b:02x} "
            col += [c, c, None]
        text += " |"
        col += [None, DIM]
        for b, c in zip(chunk, cc):
            ch, c = ascii_of(b, c)
            text += ch
            col.append(c)
        text += "|"
        col.append(DIM)
        lines.append((text, col))
    end = f"{base + len(data):08x}"
    lines.append((end, [DIM] * len(end)))
    return lines


def xxd(data, colors, base, per_line=8):
    """`xxd -c N`: offset, 2-byte groups, two spaces, ascii."""
    lines = []
    for off in range(0, len(data), per_line):
        chunk, cc = data[off:off + per_line], colors[off:off + per_line]
        text, col = f"{base + off:08x}: ", [DIM] * 9 + [None]
        for j, (b, c) in enumerate(zip(chunk, cc)):
            if j and j % 2 == 0:
                text += " "
                col.append(None)
            text += f"{b:02x}"
            col += [c, c]
        text += "  "
        col += [None, None]
        for b, c in zip(chunk, cc):
            ch, c = ascii_of(b, c)
            text += ch
            col.append(c)
        lines.append((text, col))
    return lines


def objdump(raw_bytes):
    """`objdump -M intel --disassemble=main`, tabs expanded at 8-column stops."""
    head = f"{MAIN:016x} <main>:"
    lines = [(head, [DIM] * 17 + [GREEN] * (len(head) - 17))]
    for addr, raw, mn, ops, color in INSNS:
        text = f"{addr:>8x}:".ljust(16)
        col = [None] * 4 + [DIM] * 5 + [None] * 7
        if raw_bytes:
            hexb = " ".join(f"{b:02x}" for b in raw).ljust(24)
            text += hexb
            col += [NUL if ch != " " else None for ch in hexb]
        text += mn.ljust(7) if ops else mn
        col += [BLUE] * len(mn) + [None] * (len(text) - len(col) - len(mn))
        if ops:
            sym = ops.find("<")
            text += ops
            if sym < 0:
                col += [FG if ch != "," else DIM for ch in ops]
            else:
                col += ([FG] * sym + [DIM] + [color] * (len(ops) - sym - 2)
                        + [DIM])
        lines.append((text, col))
    return lines


# ================================================================== layouts ==
WIDE = dict(
    name="terminal.svg", cols=95, rows=34, margin=20,  # 95 * 8.4 = 798.0
    cwd="~/lab",
    dis_cmd="objdump -M intel --disassemble=main ./michael | tail -n +7",
    dis=objdump(raw_bytes=True),
    dump_cmd=f"hexdump -C -s {RODATA_VADDR:#x} -n {len(DATA)} ./michael",
    dump=hexdump_c(DATA, DATA_COLORS, RODATA_VADDR),
    notes={0: "; .rodata", 8: "; jump table"}, note_c=80,
)

COMPACT_BYTES = 104                    # 13 lines of 8: through the url
COMPACT = dict(
    name="terminal-compact.svg", cols=48, rows=37, margin=14,
    cwd="~",
    # long enough to wrap onto a second line, as it would in a real terminal
    dis_cmd=("objdump -M intel --no-show-raw-insn --disassemble=main "
             "./michael | tail -n +7"),
    dis=objdump(raw_bytes=False),
    dump_cmd=f"xxd -c8 -s{RODATA_VADDR:#x} -l{COMPACT_BYTES} michael",
    dump=xxd(DATA[:COMPACT_BYTES], DATA_COLORS[:COMPACT_BYTES], RODATA_VADDR),
    notes={}, note_c=0,
)


# ===================================================================== card ==
class Card:
    def __init__(self, L, theme):
        self.L, self.th = L, THEMES[theme]
        self.cols, self.rows, m = L["cols"], L["rows"], L["margin"]
        self.win_w = self.cols * CW + 2 * PAD
        self.win_h = self.rows * CH + 2 * PAD + TITLEBAR
        self.w = round(self.win_w + 2 * m + 1)
        self.h = round(self.win_h + 2 * m + 1)
        self.x0 = m + 1 + PAD                 # x of column 0
        self.y0 = m + 1 + TITLEBAR + PAD      # y of row 0's top edge
        self.out = []
        self.n_typed = 0
        self.prompt_parts = [("[", DIM, False), (HOST, GREEN, True),
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
        return (f'<text x="{num(x)}" y="{num(y)}" fill="{self.th[fill]}"{weight}{space} '
                f'textLength="{num(len(text) * CW)}">{esc(text)}</text>')

    def paint(self, col0, row, text, colors):
        """A line with per-character colour, emitted as the fewest runs.
        A None colour (spaces) joins whichever run surrounds it."""
        out, i, n = [], 0, len(text)
        while i < n:
            if colors[i] is None:
                i += 1
                continue
            c, end, j = colors[i], i + 1, i + 1
            while j < n and colors[j] in (None, c):
                if colors[j] == c:
                    end = j + 1
                j += 1
            out.append(self.run(col0 + i, row, text[i:end], c))
            i = end
        return "".join(out)

    def block(self, col, row, n_cells, fill, inner=""):
        """A run of coloured cells — how a terminal paints a background."""
        x, _ = self.px(col, row)
        return (f'<rect x="{num(x)}" y="{num(self.y0 + row * CH)}" '
                f'width="{num(n_cells * CW)}" height="{CH}" '
                f'fill="{self.th[fill]}">{inner}</rect>')

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
        """Reveal a command left-to-right behind an expanding clip, like
        typing. A command longer than the line wraps onto the next row, the
        way a terminal soft-wraps it. Returns the number of rows used."""
        segs, col, room = [], self.prompt_len, self.cols - self.prompt_len
        while text:
            segs.append((col, text[:room]))
            text, col, room = text[room:], 0, self.cols
        rate = type_dur("".join(s for _, s in segs)) / sum(len(s) for _, s in segs)
        for i, (col, seg) in enumerate(segs):
            self.n_typed += 1
            uid = f"k{self.n_typed}"
            x, _ = self.px(col, row + i)
            self.add(f'<clipPath id="{uid}"><rect x="{num(x)}" '
                     f'y="{num(self.y0 + (row + i) * CH)}" width="0" '
                     f'height="{CH}"><animate attributeName="width" '
                     f'to="{num(len(seg) * CW)}" begin="{t(begin)}" '
                     f'dur="{t(len(seg) * rate)}" fill="freeze"/></rect>'
                     f'</clipPath><g clip-path="url(#{uid})">'
                     f'{self.run(col, row + i, seg)}</g>')
            begin += len(seg) * rate
        return len(segs)

    def command(self, row, text, at):
        """Prompt, then the typed command. Returns (when output appears,
        first output row)."""
        self.add(self.fade(self.prompt(row), at))
        n = self.typed(row, text, at + 0.2)
        return at + 0.2 + type_dur(text) + 0.25, row + n

    def output(self, row, lines, at, notes=None, step=0.07):
        """Stream pre-coloured lines in one after another. Returns the time
        the last line lands and the row after it."""
        notes = notes or {}
        for i, (text, colors) in enumerate(lines):
            el = self.paint(0, row + i, text, colors)
            if i in notes:
                el += self.run(self.L["note_c"], row + i, notes[i], DIM)
            self.add(self.fade(el, at + i * step, 0.1))
        return at + len(lines) * step, row + len(lines)

    # -------------------------------------------------------------- render --
    def render(self):
        L, add = self.L, self.add
        W, H, m = self.w, self.h, L["margin"]

        # Window chrome only; the canvas around it stays transparent. The
        # shadow is the only filtered element and nothing animated lives
        # inside it, so it is rasterised once.
        add('<defs><filter id="shadow" x="-20%" y="-20%" width="140%" '
            'height="140%"><feDropShadow dx="0" dy="6" stdDeviation="9" '
            'flood-color="#000000" '
            f'flood-opacity="{self.th["shadow"]}"/></filter></defs>')
        add(f'<rect x="{m + 0.5}" y="{m + 0.5}" rx="10" width="{num(self.win_w)}" '
            f'height="{num(self.win_h)}" fill="{self.th["frame"]}" stroke="{self.th["border"]}" '
            f'filter="url(#shadow)"/>')
        add(f'<rect x="{m + 1}" y="{m + 1}" rx="9" width="{num(self.win_w - 1)}" '
            f'height="{TITLEBAR}" fill="{self.th["bar"]}"/>')
        for i, c in enumerate(LIGHTS):
            add(f'<circle cx="{m + 14 + i * 16}" cy="{m + 14}" r="5" fill="{c}"/>')
        add(f'<text x="{W / 2:.0f}" y="{m + 18}" fill="{self.th[DIM]}" font-size="12" '
            f'text-anchor="middle">{HOST}: {L["cwd"]}</text>')
        add(f'<rect x="{m + 1}" y="{m + 1 + TITLEBAR}" rx="9" '
            f'width="{num(self.win_w - 1)}" height="{num(self.win_h - TITLEBAR)}" '
            f'fill="{self.th["body"]}"/>')

        # grid content: crisp edges inherited by every rect in this group
        add('<g shape-rendering="crispEdges">')
        fade, run = self.fade, self.run

        # ---------------------------------------------------------- whoami --
        at, row = self.command(0, "whoami", 0.15)
        add(fade(run(0, row, "michael", FG, True) + run(8, row, WHOAMI, DIM), at))

        # ----------------------------------------------------- disassembly --
        at, row = self.command(row + 2, L["dis_cmd"], at + 0.4)
        at, row = self.output(row, L["dis"], at)

        # ------------------------------------------------------------ dump --
        at, row = self.command(row + 1, L["dump_cmd"], at + 0.3)
        at, row = self.output(row, L["dump"], at, L["notes"])
        F = at + 0.3

        # ---------------------------------------------------------- footer --
        row += 1
        add(fade(run(0, row, "stack", DIM, True) + run(8, row, STACK, FG), F))
        add(fade(run(0, row + 1, "tools", DIM, True) + run(8, row + 1, TOOLS, FG),
                 F + 0.1))
        row += 3
        add(fade(self.prompt(row), F + 0.35))
        # hard on/off blink like a real terminal: two repaints per cycle,
        # instead of a continuous fade that repaints every frame
        blink = (f'<animate attributeName="opacity" values="1;0" '
                 f'calcMode="discrete" dur="1.06s" begin="{t(F + 0.55)}" '
                 f'repeatCount="indefinite"/>')
        add(fade(self.block(self.prompt_len, row, 1, FG, blink), F + 0.35))
        add('</g>')

        if row != self.rows - 2:           # keep one blank row below the prompt
            raise ValueError(f"layout used {row + 2} rows, grid has {self.rows}")

        calls = ", ".join(n.replace("_", " ") for n, _, _ in FUNCS)
        label = (f"Terminal window. whoami returns michael, {WHOAMI}. "
                 f"objdump disassembles main of ./michael, which calls "
                 f"{calls}. Then a hex dump of the binary's .rodata "
                 f"containing the strings /bin/sh, take it apart, see how it "
                 f"works, build the tool you wish existed, and efarov.com. "
                 f"Stack: {STACK.replace(' / ', ', ')}. "
                 f"Tools: {TOOLS.replace(' / ', ', ')}.")
        body = "\n".join(self.out)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
                f'height="{H}" viewBox="0 0 {W} {H}" role="img" '
                f"font-family='{FONT}' font-size=\"{FS}\" "
                f'aria-label="{esc(label)}">\n{body}\n</svg>\n')


if __name__ == "__main__":
    # terminal.svg / terminal-compact.svg are dark; *-light.svg are light.
    # The README picks one per viewer with <picture> media queries.
    os.makedirs("assets", exist_ok=True)
    for layout in (WIDE, COMPACT):
        for theme in THEMES:
            card = Card(layout, theme)
            svg = card.render()
            stem, ext = os.path.splitext(layout["name"])
            suffix = "" if theme == "dark" else f"-{theme}"
            path = os.path.join("assets", f"{stem}{suffix}{ext}")
            with open(path, "w") as f:
                f.write(svg)
            print(f"wrote {path:<32} ({card.w}x{card.h} px, "
                  f"{card.cols}x{card.rows} cells, "
                  f"{len(svg.encode()) / 1024:.1f} KB)")
    print(f".rodata: {len(DATA)} bytes at {RODATA_VADDR:#x}")
