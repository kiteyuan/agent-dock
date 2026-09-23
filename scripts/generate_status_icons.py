#!/usr/bin/env python3
"""Generate pixel status-icon spritesheet for Web + Flutter clients.

Layout: 7 rows × 4 frames, each cell 16×16 (RGBA), display at 2×–3×.
Rows: idle, listen, busy, speak, connecting, offline, error

  python scripts/generate_status_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CELL = 16
FRAMES = 4
ROWS = (
    "idle",
    "listen",
    "busy",
    "speak",
    "connecting",
    "offline",
    "error",
)

ACCENT = (62, 207, 142, 255)
ACCENT_DIM = (62, 207, 142, 140)
MUTED = (106, 118, 132, 255)
MUTED_DIM = (106, 118, 132, 150)
ERR = (224, 112, 112, 255)
ERR_DIM = (224, 112, 112, 150)
INK = (10, 14, 18, 255)
CLEAR = (0, 0, 0, 0)


def blank() -> list[list[tuple[int, int, int, int]]]:
    return [[CLEAR for _ in range(CELL)] for _ in range(CELL)]


def put(g, x, y, c) -> None:
    if 0 <= x < CELL and 0 <= y < CELL:
        g[y][x] = c


def fill(g, x0, y0, x1, y1, c) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            put(g, x, y, c)


def stamp(g, lines, ox, oy, c) -> None:
    for dy, row in enumerate(lines):
        for dx, ch in enumerate(row):
            if ch not in ". ":
                put(g, ox + dx, oy + dy, c)


def draw_mic(g, color, *, bold=False) -> None:
    # capsule body
    stamp(
        g,
        [
            ".####.",
            "#....#",
            "#....#",
            "#....#",
            "#....#",
            "#....#",
            ".####.",
        ],
        5,
        1,
        color,
    )
    if bold:
        fill(g, 6, 2, 9, 6, color)
    # yoke + stand
    put(g, 4, 8, color)
    put(g, 11, 8, color)
    fill(g, 4, 9, 11, 9, color)
    fill(g, 7, 10, 8, 11, color)
    fill(g, 5, 12, 10, 12, color)


def mic(color, *, bold=False, sparkle=False) -> list[list[tuple]]:
    g = blank()
    draw_mic(g, color, bold=bold)
    if sparkle:
        for x, y in ((2, 3), (13, 3), (1, 6), (14, 6)):
            put(g, x, y, ACCENT_DIM)
    return g


def busy(frame: int) -> list[list[tuple]]:
    g = blank()
    xs = (3, 7, 11)
    for i, x in enumerate(xs):
        lift = (frame % 3) == i
        y = 6 if lift else 8
        c = ACCENT if lift else ACCENT_DIM
        fill(g, x, y, x + 1, y + 1, c)
    return g


def speak(frame: int) -> list[list[tuple]]:
    g = blank()
    # speaker body (left)
    fill(g, 2, 5, 4, 10, ACCENT)
    put(g, 5, 4, ACCENT)
    put(g, 5, 11, ACCENT)
    fill(g, 5, 5, 6, 10, ACCENT)
    put(g, 7, 3, ACCENT)
    put(g, 7, 12, ACCENT)
    fill(g, 7, 4, 7, 11, ACCENT)
    # concentric wave arcs (frames reveal more)
    arcs = [
        [(9, 5), (9, 6), (9, 9), (9, 10)],
        [(10, 4), (11, 6), (11, 9), (10, 11)],
        [(12, 3), (13, 5), (14, 7), (14, 8), (13, 10), (12, 12)],
    ]
    for wi, pts in enumerate(arcs):
        if frame >= wi:
            c = ACCENT if frame >= wi else ACCENT_DIM
            if frame == wi:
                c = ACCENT
            elif frame > wi:
                c = ACCENT_DIM if frame < 3 else ACCENT
            for x, y in pts:
                put(g, x, y, c)
    if frame == 3:
        for x, y in arcs[0] + arcs[1] + arcs[2]:
            put(g, x, y, ACCENT)
    return g


def connecting(frame: int) -> list[list[tuple]]:
    g = blank()
    # octagonal ring points clockwise from top
    ring = [
        (7, 2),
        (8, 2),
        (10, 3),
        (11, 4),
        (12, 6),
        (12, 7),
        (12, 8),
        (12, 9),
        (11, 11),
        (10, 12),
        (8, 13),
        (7, 13),
        (5, 12),
        (4, 11),
        (3, 9),
        (3, 8),
        (3, 7),
        (3, 6),
        (4, 4),
        (5, 3),
    ]
    for x, y in ring:
        put(g, x, y, MUTED)
    n = len(ring)
    start = (frame % 4) * 5
    for i in range(6):
        x, y = ring[(start + i) % n]
        put(g, x, y, ACCENT)
    # hub
    fill(g, 7, 7, 8, 8, ACCENT_DIM)
    return g


def offline() -> list[list[tuple]]:
    g = mic(MUTED, bold=False)
    # clean diagonal slash
    for i in range(14):
        put(g, 1 + i, 1 + i, ERR)
        put(g, 2 + i, 1 + i, ERR)
    return g


def error_icon(frame: int) -> list[list[tuple]]:
    g = blank()
    c = ERR if frame % 2 == 0 else ERR_DIM
    # filled warning triangle
    stamp(
        g,
        [
            ".......#.......",
            "......###......",
            ".....##.##.....",
            "....##...##....",
            "...##.....##...",
            "..##.......##..",
            ".##.........##.",
            "##...........##",
            "###############",
        ],
        0,
        3,
        c,
    )
    # bang
    fill(g, 7, 5, 8, 8, INK)
    fill(g, 7, 10, 8, 11, INK)
    return g


def frame_for(row: str, fi: int) -> list[list[tuple]]:
    if row == "idle":
        return mic(MUTED if fi % 2 == 0 else MUTED_DIM)
    if row == "listen":
        return mic(ACCENT, bold=True, sparkle=fi % 2 == 1)
    if row == "busy":
        return busy(fi)
    if row == "speak":
        return speak(fi)
    if row == "connecting":
        return connecting(fi)
    if row == "offline":
        return offline()
    if row == "error":
        return error_icon(fi)
    return blank()


def grid_to_image(g) -> Image.Image:
    im = Image.new("RGBA", (CELL, CELL), CLEAR)
    px = im.load()
    for y in range(CELL):
        for x in range(CELL):
            px[x, y] = g[y][x]
    return im


def main() -> None:
    sheet = Image.new("RGBA", (CELL * FRAMES, CELL * len(ROWS)), CLEAR)
    for ri, name in enumerate(ROWS):
        for fi in range(FRAMES):
            cell = grid_to_image(frame_for(name, fi))
            sheet.paste(cell, (fi * CELL, ri * CELL), cell)

    targets = [
        ROOT / "clients" / "shared" / "status-icons.png",
        ROOT / "clients" / "web" / "status-icons.png",
        ROOT / "clients" / "mobile" / "assets" / "status-icons.png",
    ]
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(path, optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({sheet.size[0]}x{sheet.size[1]})")


if __name__ == "__main__":
    main()
