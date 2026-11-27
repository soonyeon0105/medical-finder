#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_brand.py — K-MediCheck 마크(파비콘) 생성 — 국내 사이트용

  assets/favicon.svg   인라인 로고와 같은 마크
  assets/favicon.ico   16·32·48·64 멀티사이즈 (PIL)

  python3 scripts/make_brand.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

TEAL_LIGHT = (220, 229, 200)
NAVY = (76, 92, 62)
MARK_PATH = "M16 7.4V24.6M7.4 16H20.4L26.6 10.4"


def favicon_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" role="img" aria-label="K-MediCheck">'
        '<rect width="32" height="32" rx="7.5" fill="#4C5C3E"/>'
        '<path d="' + MARK_PATH + '" fill="none" stroke="#DCE5C8" stroke-width="4.6" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>\n"
    )


def ico_image(size: int) -> Image.Image:
    s = 8
    img = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = 7.5 / 32 * size * s
    d.rounded_rectangle([0, 0, size * s - 1, size * s - 1], radius=r, fill=NAVY)
    w = max(2, round(4.6 / 32 * size * s))
    k = size * s / 32
    for pts in ([(16 * k, 7.4 * k), (16 * k, 24.6 * k)],
                [(7.4 * k, 16 * k), (20.4 * k, 16 * k), (26.6 * k, 10.4 * k)]):
        d.line(pts, fill=TEAL_LIGHT, width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=TEAL_LIGHT)
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    ico_image(64).save(ASSETS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("favicon.svg, favicon.ico →", ASSETS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
