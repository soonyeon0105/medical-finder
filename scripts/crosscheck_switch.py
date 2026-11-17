#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-M13 — Python 계산 엔진(scripts/switch_engine.py) ↔ 화면 JS 엔진(assets/switch-gen5.js) 전수 교차검증

1) 엔진 대 엔진: 수천 건 조합을 한 번에 JS 로 넘겨 계산 결과(연간 자기부담·보험료 절감·손익 Δ·판단·손익분기·
   그래프 곡선)를 전부 비교한다.
2) 화면 대 엔진: 실제 빌드 페이지에서 입력을 조작해 표시된 숫자를 읽어 파이썬 결과와 비교한다.

사용법: python3 scripts/crosscheck_switch.py [--n 4000] [--quiet]
종료코드 0 = 불일치 0건
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import random
import socketserver
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402
import switch_engine as E  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

DIST = BASE / "dist"
PORT = 8817

AMOUNTS = [0, 10000, 30000, 43850, 100000, 300000, 800000, 1200000, 3000000, 9000000, 30000000]
PREMIUMS = [0, 1, 1000, 24000, 32000, 48000, 88000, 240000]
VISITS = [0, 1, 2, 12, 24, 100]
DISCOUNTS = [None, 10, 30, 50, 70]
INSTS = ["clinic", "hospital", "general", "tertiary"]


def build_combos(n: int) -> list[dict]:
    rnd = random.Random(20261118)
    out = []
    # 경계값 전수(작은 축)
    for gen in (1, 2, 3, 4, 5):
        for pcur in (0, 24000, 32000):
            for mild in (0, 1200000):
                out.append({"gen": gen, "pcur": pcur, "mild": mild, "gen1_rate": 20})
    while len(out) < n:
        gen = rnd.choice([1, 1, 2, 3, 4, 4, 4, 5])
        mode = rnd.choice(["auto", "auto", "auto", "manual"])
        c = {
            "gen": gen,
            "gen1_rate": rnd.choice([None, 0, 5, 20, 30, 50, 100, 120]),
            "gen2_type": rnd.choice(["standard", "select1"]),
            "gen3_type": rnd.choice(["standard", "select2"]),
            "pcur": rnd.choice(PREMIUMS),
            "p5_mode": mode,
            "p5": rnd.choice(PREMIUMS),
            "discount": rnd.choice(DISCOUNTS),
            "in_cov": rnd.choice(AMOUNTS),
            "out_cov": rnd.choice(AMOUNTS),
            "out_visits": rnd.choice(VISITS),
            "severe": rnd.choice(AMOUNTS),
            "mild": rnd.choice(AMOUNTS),
            "mild_visits": rnd.choice(VISITS),
            "inst": rnd.choice(INSTS),
            "managed": rnd.random() < 0.2,
        }
        out.append(c)
    return out


def compare(c: dict, js: dict, py: dict) -> list[str]:
    errs = []
    simple = ("ok", "hold", "gen", "pcur", "p5", "p5_estimated", "discount",
              "oop_cur", "oop5", "premium_saving", "oop_increase", "delta",
              "verdict", "break_even", "break_even_dir")
    for k in simple:
        if js.get(k) != py.get(k):
            errs.append(f"{k}: JS={js.get(k)!r} PY={py.get(k)!r}")
    jc = (js.get("chart") or {}).get("points") or []
    pc = (py.get("chart") or {}).get("points") or []
    if (js.get("chart") or {}).get("xmax") != (py.get("chart") or {}).get("xmax"):
        errs.append("chart.xmax 불일치")
    if len(jc) != len(pc):
        errs.append(f"chart 점 개수 {len(jc)} != {len(pc)}")
    else:
        for a, b in zip(jc, pc):
            if list(a) != list(b):
                errs.append(f"chart 점 {a} != {b}")
                break
    for side in ("cur", "gen5"):
        ja = (js.get("parts") or {}).get(side) or {}
        pa = (py.get("parts") or {}).get(side) or {}
        for k in ("cov_in", "cov_out", "severe", "mild", "total"):
            if ja.get(k) != pa.get(k):
                errs.append(f"parts.{side}.{k}: JS={ja.get(k)!r} PY={pa.get(k)!r}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000, help="엔진 대 엔진 비교 조합 수")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    combos = build_combos(args.n)
    print(f"조합 {len(combos):,}건 × (값 15 + 그래프 200점 + 항목 10) = {len(combos) * 225:,}개 값")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"

    mismatches: list[str] = []
    ui_checked = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
        page = ctx.new_page()
        page.goto(base + "/ko/switch-gen5/", wait_until="load")
        page.wait_for_selector("[data-sim][data-ready='1']", timeout=15000)

        chunk = 1000
        for start in range(0, len(combos), chunk):
            part = combos[start:start + chunk]
            got = page.evaluate("(args) => args.map(c => window.Gen5Sim.compute(c))", part)
            for c, g in zip(part, got):
                errs = compare(c, g, E.compute(dict(c)))
                if errs:
                    mismatches.append(f"{c} → " + " | ".join(errs[:3]))
            if not args.quiet:
                print(f"  엔진 비교 {min(start + chunk, len(combos)):,}/{len(combos):,}")
        ctx.close()

        # ---------------------------------------------------------- 화면 대 엔진(표본)
        ctx2 = browser.new_context(viewport={"width": 390, "height": 900}, locale="ko-KR")
        pg = ctx2.new_page()
        pg.goto(base + "/ko/switch-gen5/", wait_until="load")
        pg.wait_for_selector("[data-sim][data-ready='1']", timeout=15000)

        ui_cases = []
        for gen in (1, 2, 3, 4, 5):
            for pcur in (24000, 48000, 0):
                for mild in (0, 1200000):
                    for in_cov in (0, 800000):
                        ui_cases.append({"gen": gen, "pcur": pcur, "mild": mild, "in_cov": in_cov,
                                         "gen1_rate": 20, "gen2_type": "standard",
                                         "gen3_type": "standard", "p5_mode": "auto",
                                         "discount": None, "out_cov": 300000, "out_visits": 6,
                                         "severe": 0, "mild_visits": 0, "inst": "clinic"})
        for c in ui_cases[:60]:
            pg.click(f'[data-seg="gen"][data-v="{c["gen"]}"]')
            if c["gen"] == 1:
                pg.fill('[data-k="gen1_rate"]', str(c["gen1_rate"]))
            pg.fill('[data-k="pcur"]', str(c["pcur"]))
            for k in ("mild", "in_cov", "out_cov", "out_visits"):
                pg.fill(f'[data-k="{k}"]', str(c[k]))
            pg.dispatch_event('[data-k="pcur"]', "input")
            pg.dispatch_event('[data-k="mild"]', "input")
            pg.wait_for_timeout(40)
            py = E.compute(dict(c, gen1_rate=c["gen1_rate"]))
            txt = pg.inner_text("#sim-out")
            if py.get("hold"):
                hold_txt = {"already_gen5": "이미 5세대", "premium_unknown": "현재 월 보험료를 입력하면",
                            "gen1_rate": "약관상 자기부담률을 직접 입력"}.get(py["hold"])
                if hold_txt and hold_txt not in txt:
                    mismatches.append(f"UI hold 문구 불일치 ({py['hold']}): {txt[:80]}")
            else:
                show = "{:,}원".format(abs(py["delta"]))
                if show not in txt:
                    mismatches.append(f"UI 금액 불일치 {c}: 화면에 {show} 없음")
                label = {"save": "전환 유리", "loss": "유지 유리", "hold": "판단 보류"}[py["verdict"]]
                if label not in txt:
                    mismatches.append(f"UI 판단 불일치 {c}: {label} 없음")
            ui_checked += 1
        ctx2.close()
        browser.close()
    httpd.shutdown()

    print(f"\n화면(UI) 표본 검증 {ui_checked}건")
    if mismatches:
        print(f"불일치 {len(mismatches)}건")
        for m in mismatches[:15]:
            print("  -", m)
        return 1
    print(f"불일치 0건 · 엔진 비교 {len(combos):,}건 × 225개 값 = {len(combos) * 225:,}개 일치")
    out = {"combos": len(combos), "values_compared": len(combos) * 225,
           "ui_cases": ui_checked, "mismatches": 0}
    (BASE / "scripts" / "crosscheck_switch_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
