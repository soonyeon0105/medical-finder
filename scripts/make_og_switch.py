#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-M13 — 실손 5세대 전환 손익 시뮬레이터 OG 이미지(1200×630 PNG) 생성

assets/og-switch-gen5.png 를 만든다. 한글 폰트(Noto Sans CJK KR)를 쓰고,
폰트가 없으면 실패한다(깨진 글자가 배포되지 않게).
카드와 같은 톤(흰색+teal, 하단 네이비 바)으로 맞춘다.

사용법: python3 scripts/make_og_switch.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "assets" / "og-switch-gen5.png"

FONT_CANDIDATES = [
    "/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

TEAL = (76, 92, 62)
TEAL_INK = (76, 92, 62)
NAVY = (76, 92, 62)
INK = (47, 54, 42)
INK2 = (58, 66, 52)
MUTED = (110, 116, 98)


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("한글 폰트를 찾을 수 없습니다: " + ", ".join(FONT_CANDIDATES))


def gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return img.resize((w, h))


def main() -> int:
    W, H = 1200, 630
    img = gradient(W, H, (255, 253, 247), (232, 236, 220)).convert("RGB")
    d = ImageDraw.Draw(img)
    # 좌상단 포인트 블롭
    blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((820, -180, 1320, 220), fill=(113, 131, 95, 38))
    bd.ellipse((-140, 380, 360, 780), fill=(157, 184, 154, 26))
    img = Image.alpha_composite(img.convert("RGBA"), blob).convert("RGB")
    d = ImageDraw.Draw(img)

    d.rectangle((0, 0, W, 10), fill=NAVY)

    # 로고 마크
    d.rounded_rectangle((72, 60, 128, 116), radius=15, fill=NAVY)
    d.line((100, 74, 100, 102), fill=(220, 229, 200), width=8)
    d.line((86, 88, 114, 88), fill=(220, 229, 200), width=8)
    d.text((146, 72), "K-MediCheck · 내 병원비 계산기", font=font(26), fill=INK2)

    # 제목
    d.text((72, 168), "실손 5세대 전환 손익", font=font(62), fill=NAVY,
           stroke_width=2, stroke_fill=NAVY)
    d.text((72, 250), "보험료는 내려가고 자기부담은 올라갑니다", font=font(30), fill=MUTED)

    # 중앙 큰 숫자
    d.text((72, 300), "연 ±○○원", font=font(98), fill=TEAL,
           stroke_width=3, stroke_fill=TEAL_INK)
    d.text((72, 446), "절약일까, 손해일까? 내 조건으로 1분 만에 확인", font=font(31), fill=INK)

    # 안내 칩
    chips = ["급여 20%·통원 최소 1만 원", "비중증 50%·연 1,000만 원", "차등제 첫 적용 2028-05"]
    x = 72
    for c in chips:
        f = font(22)
        tw = d.textlength(c, font=f)
        d.rounded_rectangle((x, 500, x + tw + 28, 542), radius=21, fill=(255, 255, 255),
                            outline=(201, 210, 180), width=1)
        d.text((x + 14, 508), c, font=f, fill=TEAL_INK)
        x += tw + 40

    # 하단 바
    d.rectangle((0, H - 76, W, H), fill=NAVY)
    d.text((72, H - 50), "kr.kmedicheck.com", font=font(30), fill=(255, 255, 255),
           stroke_width=1, stroke_fill=(255, 255, 255))
    right = "참고용 추정치 · 약관 확인 · 금융감독원 1332"
    rw = d.textlength(right, font=font(22))
    d.text((W - 72 - rw, H - 44), right, font=font(22), fill=(201, 210, 180))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"saved {OUT} {img.size[0]}x{img.size[1]} {OUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
