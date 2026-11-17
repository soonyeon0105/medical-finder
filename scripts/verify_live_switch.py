#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-M13 — 배포된 라이브 사이트(https://medical-finder-kr.pages.dev) 검증 + 스크린샷

확인
  · /ko/switch-gen5/ 200 · 핵심 요소·고지 문구·OG 메타
  · /assets/og-switch-gen5.png 200 · 1200×630
  · /assets/switch-gen5.js 200 · UTM 규격
  · /sitemap.xml 에 새 URL 포함
  · /ko/calc/ 하단 시뮬레이터 링크
  · 실제 브라우저에서 계산·차트·카드 저장 동작 (데스크톱 1440 · 모바일 390)
  · 스크린샷을 downloads/medical-mvp/ 에 저장

사용법: python3 scripts/verify_live_switch.py [--base https://medical-finder-kr.pages.dev]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = Path(os.environ.get("MED_SHOTS_DIR", "/workspace/downloads/medical-mvp"))
SHOTS = os.environ.get("MED_SHOT_PREFIX", "tm13-live")
results: dict = {"checks": [], "screenshots": [], "console_errors": []}


def check(name: str, ok: bool, detail="") -> bool:
    results["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + ((" · " + str(detail)) if detail else ""))
    return bool(ok)


def fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (med-finder verify)"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.status, r.read()


def shot(page, name: str, full: bool = False) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{SHOTS}-{name}.png"
    page.screenshot(path=str(p), full_page=full)
    results["screenshots"].append(str(p))
    return str(p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://medical-finder-kr.pages.dev")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    # ---------------------------------------------------------------- HTTP 확인
    try:
        st, body = fetch(base + "/ko/switch-gen5/?v=verify")
    except Exception as exc:  # noqa: BLE001
        check("라이브 /ko/switch-gen5/ 응답", False, str(exc)[:120])
        body = b""
        st = 0
    html = body.decode("utf-8", "ignore")
    check("라이브 /ko/switch-gen5/ 200", st == 200, st)
    check("라이브 페이지: 시뮬레이터 요소", 'data-sim' in html and 'id="sim-out"' in html, "")
    check("라이브 페이지: canonical·OG", f'{base}/ko/switch-gen5/' in html
          and f'{base}/assets/og-switch-gen5.png' in html, "")
    check("라이브 페이지: 고지(1332·2028년 5월·할증)",
          all(k in html for k in ("1332", "2028년 5월", "할증", "관리급여")), "")
    check("라이브 페이지: 초안 표기 0건", not any(x in html for x in ("(추정", "추정)", "확인 필요")), "")
    try:
        st_og, og = fetch(base + "/assets/og-switch-gen5.png")
    except Exception as exc:  # noqa: BLE001
        st_og, og = 0, b""
        check("라이브 OG 이미지", False, str(exc)[:120])
    if og:
        import struct
        w, h = struct.unpack(">II", og[16:24])
        check("라이브 OG 이미지 200·1200×630", st_og == 200 and (w, h) == (1200, 630), f"{st_og} {w}×{h}")
    try:
        st_js, js = fetch(base + "/assets/switch-gen5.js")
    except Exception as exc:  # noqa: BLE001
        st_js, js = 0, b""
        check("라이브 시뮬레이터 JS", False, str(exc)[:120])
    jst = js.decode("utf-8", "ignore")
    check("라이브 JS: 200·UTM 규격", st_js == 200 and all(
        x in jst for x in ("kakaotalk", "og_share", "link_copy", "utm_medium=share_card",
                           "utm_campaign=gen5-simulator", "result-hold")), st_js)
    try:
        _, sm = fetch(base + "/sitemap.xml")
        smt = sm.decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        smt = ""
        check("라이브 sitemap", False, str(exc)[:120])
    check("라이브 sitemap: /ko/switch-gen5/ 포함", f"<loc>{base}/ko/switch-gen5/</loc>" in smt, "")
    check("라이브 sitemap URL 수(57)", smt.count("<loc>") == 57, smt.count("<loc>"))
    try:
        _, calc = fetch(base + "/ko/calc/")
        calch = calc.decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        calch = ""
        check("라이브 계산기", False, str(exc)[:120])
    check("라이브 계산기 → 시뮬레이터 링크", 'href="/ko/switch-gen5/"' in calch, "")
    check("라이브 robots.txt", "Sitemap:" in fetch(base + "/robots.txt")[1].decode("utf-8", "ignore"), "")

    # ---------------------------------------------------------------- 브라우저 확인
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, w, h, mobile in (("desktop-1440", 1440, 900, False), ("mobile-390", 390, 844, True)):
            ctx = browser.new_context(viewport={"width": w, "height": h}, locale="ko-KR",
                                      is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
            page = ctx.new_page()
            page.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: results["console_errors"].append(str(e)))
            page.goto(base + "/ko/switch-gen5/", wait_until="load", timeout=45000)
            page.wait_for_selector("[data-sim][data-ready='1']", timeout=20000)
            page.wait_for_timeout(300)
            check(f"{label}: 타이틀·h1", "시뮬레이터" in page.title() and "전환 손익" in page.inner_text("h1"),
                  page.title()[:40])
            ov = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"{label}: 가로 스크롤 없음", ov <= 1, f"overflow={ov}px")
            page.click('[data-seg="gen"][data-v="4"]')
            page.fill('[data-k="pcur"]', "32000")
            page.fill('[data-k="in_cov"]', "800000")
            page.fill('[data-k="mild"]', "1200000")
            page.dispatch_event('[data-k="pcur"]', "input")
            page.wait_for_timeout(350)
            out = page.inner_text("#sim-out")
            check(f"{label}: 계산 결과(연 124,800원 손해)",
                  "124,800원" in out and "유지 유리" in out, out[:50].replace("\n", " "))
            check(f"{label}: 판단 근거 3줄·차트",
                  page.eval_on_selector_all(".sim-why li", "e => e.length") == 3
                  and page.query_selector(".sim-chart-svg") is not None, "")
            check(f"{label}: 공유 버튼 활성",
                  page.eval_on_selector_all("[data-share]", "els => els.every(b => !b.disabled)"), "")
            if mobile:
                shot(page, f"{label}-switch-top")
                page.evaluate("document.querySelector('#sim-result').scrollIntoView({block:'start'})")
                page.wait_for_timeout(250)
                shot(page, f"{label}-switch-result")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(200)
                shot(page, f"{label}-switch-bottom")
                try:
                    with page.expect_download(timeout=10000) as dl:
                        page.click("[data-share='card']")
                    d = dl.value
                    card = OUT / f"{SHOTS}-card.png"
                    d.save_as(str(card))
                    results["screenshots"].append(str(card))
                    check(f"{label}: 카드 PNG 저장", card.exists() and card.stat().st_size > 15000,
                          f"{d.suggested_filename} {card.stat().st_size:,}B")
                except Exception as exc:  # noqa: BLE001
                    check(f"{label}: 카드 PNG 저장", False, str(exc)[:100])
            else:
                shot(page, f"{label}-switch-top")
                page.evaluate("document.querySelector('#sim-result').scrollIntoView({block:'start'})")
                page.wait_for_timeout(250)
                shot(page, f"{label}-switch-result")
                shot(page, f"{label}-switch-full", full=True)
                # OG 이미지 실제 렌더(네트워크) 확인
                nat = page.evaluate("""async (src) => {
                    const img = new Image();
                    const ok = await new Promise(r => { img.onload = () => r(true); img.onerror = () => r(false); img.src = src; });
                    return ok ? [img.naturalWidth, img.naturalHeight] : [0, 0];
                }""", base + "/assets/og-switch-gen5.png")
                check(f"{label}: OG 이미지 라이브 로드 1200×630", nat == [1200, 630], str(nat))
                page.goto(base + "/ko/calc/", wait_until="load")
                page.wait_for_selector("[data-calc][data-ready='1']", timeout=15000)
                page.evaluate("document.querySelector('.sim-teaser').scrollIntoView({block:'center'})")
                page.wait_for_timeout(250)
                shot(page, f"{label}-calc-teaser")
            ctx.close()
        browser.close()

    check("콘솔 오류 없음", not results["console_errors"], results["console_errors"][:3])
    fails = [c for c in results["checks"] if not c["ok"]]
    (BASE / "scripts" / "verify_live_result.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(results['checks']) - len(fails)}/{len(results['checks'])} 통과 · 스크린샷 {len(results['screenshots'])}장")
    for f in fails[:8]:
        print("  FAIL:", f["name"], "·", f["detail"][:100])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
