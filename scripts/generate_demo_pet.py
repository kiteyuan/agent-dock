#!/usr/bin/env python3
"""Generate examples/pets/demo/spritesheet.webp (8×9 × 192×208 atlas)."""

from __future__ import annotations

from pathlib import Path

CELL_W, CELL_H = 192, 208
COLS, ROWS = 8, 9


def main() -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("Pillow required: pip install pillow") from exc

    root = Path(__file__).resolve().parents[1]
    out = root / "examples" / "pets" / "demo" / "spritesheet.webp"
    out.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (COLS * CELL_W, ROWS * CELL_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Soft coral figure in row 0 (idle) — other rows stay transparent / unused.
    for col in range(4):
        x0, y0 = col * CELL_W, 0
        cx, cy = x0 + CELL_W // 2, y0 + CELL_H // 2
        draw.ellipse(
            (cx - 48, cy - 56, cx + 48, cy + 40),
            fill=(240, 120, 64, 255),
            outline=(40, 40, 40, 255),
            width=3,
        )
        draw.ellipse((cx - 18, cy - 28, cx - 6, cy - 16), fill=(40, 40, 40, 255))
        draw.ellipse((cx + 6, cy - 28, cx + 18, cy - 16), fill=(40, 40, 40, 255))

    img.save(out, format="WEBP", quality=85, method=4)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
