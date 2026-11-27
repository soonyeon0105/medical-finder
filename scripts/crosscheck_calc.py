#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 계산 엔진(scripts/calc_engine.py) ↔ 화면 JS 엔진(assets/calc.js) 전수 교차검증

1) 엔진 대 엔진: 수천 건 조합을 한 번에 JS 로 넘겨 6개 행(1세대 · 2세대 전기 · 2세대 후기 ·
   3세대 · 4세대 · 5세대) × (보장액·부담액·기준액·상태·자기부담표기·한도적용)를 전부 비교한다.
   결과 집계는 2세대 유형(전기/후기 10%형/후기 20%형) 그룹별로 분리해 보고한다.
2) 화면 대 엔진: 실제 빌드 페이지에서 입력을 조작해 표시된 숫자를 읽어 파이썬 결과와 비교한다.

사용법: python3 scripts/crosscheck_calc.py [--max 20000] [--quiet]
종료코드 0 = 불일치 0건
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402
import calc_engine as E  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

DIST = BASE / "dist"
PORT = 8813

AMOUNTS = [0, 1, 999, 5000, 5001, 9999, 10000, 10001, 15000, 20000, 30000, 43850, 49999,
           50000, 50001, 100000, 199999, 200000, 250000, 600000, 1000000, 3000001,
           5000000, 20000000]
VISITS = ["out", "in"]
INSTS = ["tertiary", "general", "hospital", "clinic"]
SEVERE = [False, True]
GEN2 = ["early", "late10", "late20", "sel2", "unknown"]
GROUP_LABEL = {"early": "2세대 전기", "late10": "2세대 후기 10%형", "late20": "2세대 후기 표준형",
               "sel2": "2세대 후기 선택형Ⅱ", "unknown": "2세대 후기(모름)"}
CUMS = [0, 4900000]
ROUNDS = [1, 2, 15]


def build_combos() -> list[dict]:
    items = [it["code"] for it in E.load_catalog()] + ["direct"]
    combos = []
    for code in items:
        for amount in AMOUNTS:
            for visit in VISITS:
                for inst in INSTS:
                    for severe in SEVERE:
                        for gen2 in GEN2:
                            c = {"item_code": code, "amount": amount, "visit": visit,
                                 "institution": inst, "severe": severe, "gen2_type": gen2,
                                 "severe_cum": 0, "rounds": 1}
                            combos.append(c)
                            if severe:      # 5세대 연간 자기부담 상한 경계
                                c2 = dict(c, severe_cum=CUMS[1])
                                combos.append(c2)
    # 관리급여: 회수 1·2·15 (금액은 회수로 결정) — 2세대 유형 5종을 번갈아 적용
    for rounds in ROUNDS:
        for visit in VISITS:
            for inst in INSTS:
                for severe in SEVERE:
                    for gen2 in GEN2:
                        combos.append({"item_code": "MX1220000", "amount": None, "visit": visit,
                                       "institution": inst, "severe": severe,
                                       "gen2_type": gen2, "rounds": rounds})
    return combos


def compare(c: dict, js: dict, py: dict) -> list[str]:
    errs = []
    if js["summary"]["best_gen"] != py["summary"]["best_gen"]:
        errs.append(f"best_gen {js['summary']['best_gen']} != {py['summary']['best_gen']}")
    if js["summary"].get("best_key") != py["summary"].get("best_key"):
        errs.append(f"best_key {js['summary'].get('best_key')} != {py['summary'].get('best_key')}")
    if len(js["generations"]) != len(py["generations"]):
        errs.append(f"행 개수 {len(js['generations'])} != {len(py['generations'])}")
    for gj, gp in zip(js["generations"], py["generations"]):
        for key in ("covered", "copay", "base", "status", "rate_label", "cap_applied",
                    "copay_hi", "covered_lo", "same_amount"):
            if gj.get(key) != gp.get(key):
                errs.append(f"{gp['key']} {key}: JS={gj.get(key)!r} PY={gp.get(key)!r}")
        if gj["gen"] != gp["gen"] or gj.get("sub") != gp.get("sub") or gj.get("key") != gp.get("key"):
            errs.append("generation 순서·구분 불일치")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=30000, help="엔진 대 엔진 비교 최대 건수")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    combos = build_combos()[: args.max]
    items = E.load_catalog()
    print(f"조합 {len(combos):,}건 (행 6개 × 비교항목 9개 = {len(combos) * 54:,}개 값)")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"

    mismatches: list[str] = []
    dom_checked = 0
    group_totals = {g: 0 for g in GEN2}
    group_bad = {g: 0 for g in GEN2}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
        page = ctx.new_page()
        page.goto(base + "/ko/calc/", wait_until="load")
        page.wait_for_selector("[data-calc][data-ready='1']", timeout=10000)

        # ---------------------------------------------------------- 1) 엔진 대 엔진
        chunk = 1500
        for start in range(0, len(combos), chunk):
            part = combos[start:start + chunk]
            got = page.evaluate(
                """(args) => {
                    const items = window.MED_CATALOG.items;
                    return args.map(c => {
                        const req = Object.assign({}, c);
                        if (req.amount === null) { delete req.amount; }
                        return window.MedCalc.compute(req, items);
                    });
                }""", part)
            for c, g in zip(part, got):
                want = E.compute({**c}, items)
                errs = compare(c, g, want)
                grp = c.get("gen2_type")
                if grp in group_totals:
                    group_totals[grp] += 1
                if errs:
                    if grp in group_bad:
                        group_bad[grp] += 1
                    mismatches.append(f"{c} → " + " | ".join(errs[:3]))
            if not args.quiet:
                print(f"  엔진 비교 {min(start + chunk, len(combos)):,}/{len(combos):,}")

        ctx.close()

        # ---------------------------------------------------------- 2) 화면 대 엔진(표본)
        ctx2 = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
        pg = ctx2.new_page()
        pg.goto(base + "/ko/calc/", wait_until="load")
        pg.wait_for_selector("[data-calc][data-ready='1']", timeout=10000)

        ui_cases = []
        for code in ["HE1010001", "HE1200000", "EB4410000", "EA0010000", "UB0010051",
                     "SZ0840000", "MY1420000", "MX1220000", "MZ0070000", "direct"]:
            for amount in [0, 30000, 250000, 1000000]:
                for visit in ("out", "in"):
                    for inst in ("tertiary", "hospital"):
                        for severe in (False, True):
                            ui_cases.append({"item_code": code, "amount": amount, "visit": visit,
                                             "institution": inst, "severe": severe,
                                             "gen2_type": "late20"})
        # 48건으로 축소(결정적 선별) 후 2세대 유형 5종을 번갈아 배정(전기/후기 분리 검증)
        ui_cases = [ui_cases[i] for i in range(0, len(ui_cases), max(1, len(ui_cases) // 48))][:48]
        for i, c in enumerate(ui_cases):
            c["gen2_type"] = GEN2[i % len(GEN2)]

        for c in ui_cases:
            pg.select_option("#item-select", c["item_code"])
            pg.wait_for_timeout(30)
            if c["item_code"] == "MX1220000":
                # 관리급여는 회수로 금액이 정해진다 → 화면 값을 그대로 사용
                c["amount"] = int(pg.input_value("#amount-input"))
            else:
                pg.fill("#amount-input", str(c["amount"]))
                pg.dispatch_event("#amount-input", "input")
                pg.wait_for_timeout(20)
            if c["amount"] <= 0:
                # M-03: 0·음수는 화면이 계산하지 않고 입력 안내를 띄운다(엔진 비교는 위에서 이미 끝남).
                if not pg.is_visible("#amount-error"):
                    mismatches.append(f"UI 0/음수 금액 안내 없음 ({c})")
                continue
            pg.click(f"#visit-group button[data-visit='{c['visit']}']")
            pg.click(f"#inst-group button[data-inst='{c['institution']}']")
            pg.click(f"#severe-group button[data-severe='{1 if c['severe'] else 0}']")
            pg.select_option("#gen2-select", c["gen2_type"])
            pg.wait_for_timeout(40)
            shown = pg.eval_on_selector_all(
                "#result-table tbody tr",
                """els => els.map(tr => ({
                     gen: Number(tr.dataset.gen),
                     sub: tr.dataset.sub || '',
                     covered: tr.querySelector('.covered').textContent.trim(),
                     copay: tr.querySelector('.copay').textContent.trim(),
                     rate: tr.querySelector('.rate-cell').textContent.trim()}))""")
            want = E.compute({**c}, items)
            if len(shown) != 6:
                mismatches.append(f"UI 행 개수 {len(shown)} != 6 ({c})")
                continue
            for s, w in zip(shown, want["generations"]):
                if s["sub"] != w["sub"]:
                    mismatches.append(f"UI sub {c} {w['key']}: {s['sub']} != {w['sub']}")
                # 범위 행('모르겠어요' 후기)은 "하한 ~ 상한" 두 끝으로 비교한다.
                want_cov = (f"{w['covered_lo']:,}원 ~ {w['covered']:,}원"
                            if w.get("covered_lo") is not None else f"{w['covered']:,}원")
                want_cop = (f"{w['copay']:,}원 ~ {w['copay_hi']:,}원"
                            if w.get("copay_hi") is not None else f"{w['copay']:,}원")
                if s["covered"] != want_cov:
                    mismatches.append(f"UI covered {c} {w['key']}: {s['covered']} != {want_cov}")
                if s["copay"] != want_cop:
                    mismatches.append(f"UI copay {c} {w['key']}: {s['copay']} != {want_cop}")
                if s["rate"] != w["rate_label"]:
                    mismatches.append(f"UI rate {c} {w['key']}: {s['rate']} != {w['rate_label']}")
            dom_checked += 1
        ctx2.close()
        browser.close()
    httpd.shutdown()

    print(f"\n화면(UI) 표본 검증 {dom_checked}건 · 행×값 {dom_checked * 18:,}개")
    print("2세대 유형 그룹별 엔진 대조 (전기/후기 분리):")
    for g in GEN2:
        print(f"  - {GROUP_LABEL[g]}: {group_totals[g]:,}건 · 불일치 {group_bad[g]}건")
    if mismatches:
        print(f"불일치 {len(mismatches)}건")
        for m in mismatches[:15]:
            print("  -", m)
        return 1
    print(f"불일치 0건 · 엔진 비교 {len(combos):,}건 × 행6 × 항목9 = {len(combos) * 54:,}개 값 일치")
    out = {"combos": len(combos), "values_compared": len(combos) * 54,
           "ui_cases": dom_checked, "mismatches": 0,
           "gen2_groups": {g: {"combos": group_totals[g], "mismatches": group_bad[g]}
                           for g in GEN2}}
    (BASE / "scripts" / "crosscheck_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
