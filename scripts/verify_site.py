#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빌드 결과 브라우저 검수 (Playwright + headless Chromium)

· dist/ 를 로컬 http 서버로 띄우고, 모바일 390px / 데스크톱 1440px 뷰포트로 렌더링한다.
· 화면 배너·계산기 동작·5세대 보장 제외 배지·관리급여 전환·가로 스크롤·콘솔 오류를 확인한다.
· 스크린샷은 downloads/medical-mvp/m03-*.png 로 저장한다(MED_SHOTS_DIR 로 변경 가능).

사용법
  python3 scripts/verify_site.py [--headed]
  MED_SHOTS_DIR=/workspace/downloads/medical-mvp python3 scripts/verify_site.py
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socketserver
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402  (LD_LIBRARY_PATH 보정)

from playwright.sync_api import sync_playwright  # noqa: E402

DIST = BASE / "dist"
OUT = Path(os.environ.get("MED_SHOTS_DIR", "/workspace/downloads/medical-mvp"))
PORT = 8811
SHOTS = os.environ.get("MED_SHOT_PREFIX", "m04")
results: dict = {"checks": [], "screenshots": [], "console_errors": [], "viewport_notes": []}


def check(name: str, ok: bool, detail="") -> bool:
    results["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + ((" · " + str(detail)) if detail else ""))
    return bool(ok)


def shot(page, name: str, full: bool = False) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{SHOTS}-{name}.png"
    page.screenshot(path=str(path), full_page=full)
    results["screenshots"].append(str(path))
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--live", action="store_true", help="--live 빌드(dist) 기준 검수: 프리뷰 배너가 없어야 함")
    args = ap.parse_args()
    live = args.live

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  locale="ko-KR", is_mobile=True, has_touch=True,
                                  user_agent=("Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
                                              "(KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36"))
        page = ctx.new_page()
        page.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: results["console_errors"].append(str(e)))

        # ------------------------------------------------------------ 랜딩(모바일 390)
        page.goto(base + "/ko/", wait_until="load")
        page.wait_for_selector("[data-calc][data-ready='1']", timeout=8000)
        if live:
            check("랜딩: 프리뷰 배너 없음", not page.is_visible("#preview-banner"), "")
            check("랜딩: noindex 없음",
                  page.eval_on_selector("meta[name=robots]", "e => e.content").startswith("index"),
                  page.eval_on_selector("meta[name=robots]", "e => e.content"))
        else:
            check("랜딩: 프리뷰 배너 노출", page.is_visible("#preview-banner"),
                  page.inner_text("#preview-banner")[:60])
        check("랜딩: 제목", "실손" in page.title() or "비급여" in page.title(), page.title())
        h1 = page.inner_text("h1")
        check("랜딩: h1 노출", "비급여" in h1, h1.replace("\n", " ")[:50])
        check("랜딩: 범위 고지 문구", "병원급 이상" in page.inner_text(".hero, .scope-note"),
              "hero/scope-note 에 '병원급 이상' 포함")

        first_row = page.inner_text("#result-table tbody tr:first-child")
        check("랜딩: 계산기 초기 렌더", "1세대" in first_row and "원" in first_row, first_row[:40].replace("\n", " "))
        meta = page.inner_text("#result-meta")
        check("랜딩: 입력 요약 표시", "비급여 금액" in meta, meta)

        # 요약(가장 유리한 세대)
        best_txt = page.inner_text("#result-summary")
        check("랜딩: 최적 세대 요약", "가장 많이 돌려받는 세대" in best_txt, best_txt.replace("\n", " ")[:60])

        # 5개 세대 행
        n_rows = page.eval_on_selector_all("#result-table tbody tr", "els => els.length")
        check("랜딩: 5개 세대 모두 표시", n_rows == 5, f"rows={n_rows}")
        gen5 = page.inner_text("#result-table tbody tr[data-gen='5']")
        check("랜딩: 5세대 행 존재", "5세대" in gen5, gen5.replace("\n", " ")[:60])

        # 가로 스크롤 없음
        ov = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check("모바일390: 페이지 가로 스크롤 없음", ov <= 1, f"overflow={ov}px")

        # 터치 타깃·글자 크기 표본
        fs = page.evaluate("getComputedStyle(document.querySelector('#result-table .covered')).fontSize")
        check("모바일390: 보장액 글자 크기 ≥15px", float(fs.replace("px", "")) >= 15, fs)

        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(150)
        shot(page, "mobile-390-home-top")
        page.evaluate("document.querySelector('#calc').scrollIntoView()")
        page.wait_for_timeout(250)
        shot(page, "mobile-390-home-calc")
        shot(page, "mobile-390-home-full", full=True)

        # ------------------------------------------------------------ 5세대 보장 제외 항목
        page.select_option("#item-select", "SZ0840000")
        page.wait_for_timeout(250)
        row5 = page.inner_text("#result-table tbody tr[data-gen='5']")
        row5_cls = page.get_attribute("#result-table tbody tr[data-gen='5']", "class")
        check("5세대 제외: 행에 제외 클래스", "is-excluded" in (row5_cls or ""), row5_cls)
        check("5세대 제외: 보장액 0원 표시", "0원" in row5, row5.replace("\n", " ")[:80])
        has_badge = page.eval_on_selector_all(
            "#result-table tbody tr[data-gen='5'] .badge",
            "els => els.map(e => e.textContent.trim())")
        check("5세대 제외: '5세대 보장 제외' 배지", any("5세대 보장 제외" in b for b in has_badge), has_badge)
        check("5세대 제외: 전액 본인부담 안내", "보장 제외" in row5, row5.split("\n")[-1][:40])
        # 배지 실제 렌더 크기(가독성)
        bbox = page.eval_on_selector("#result-table tbody tr[data-gen='5'] .badge",
                                    "el => { const r = el.getBoundingClientRect(); "
                                    "const s = getComputedStyle(el); "
                                    "return {w: Math.round(r.width), h: Math.round(r.height), fs: s.fontSize, fw: s.fontWeight}; }")
        check("5세대 제외 배지: 최소 44x16px·굵기 700 이상",
              bbox["w"] >= 44 and bbox["h"] >= 16 and int(bbox["fw"]) >= 700, bbox)
        page.evaluate("document.querySelector('#result-table tbody tr[data-gen=\\'5\\']').scrollIntoView({block:'center'})")
        page.wait_for_timeout(250)
        shot(page, "mobile-390-gen5-excluded")

        # ------------------------------------------------------------ 관리급여(도수치료)
        page.select_option("#item-select", "MX1220000")
        page.wait_for_timeout(250)
        amount = page.input_value("#amount-input")
        check("관리급여: 금액이 43,850으로 설정", amount == "43850", amount)
        check("관리급여: 회수 입력 노출", page.is_visible("#rounds-input"))
        check("관리급여: 안내 박스 노출", page.is_visible("#managed-box"),
              page.inner_text("#managed-box")[:60])
        row5m = page.inner_text("#result-table tbody tr[data-gen='5']")
        check("관리급여: 5세대는 급여 규칙 적용(제외 아님)",
              "is-excluded" not in (page.get_attribute("#result-table tbody tr[data-gen='5']", "class") or ""),
              row5m.replace("\n", " ")[:70])
        page.fill("#rounds-input", "2")
        page.dispatch_event("#rounds-input", "input")
        page.wait_for_timeout(200)
        check("관리급여: 2회 선택 시 총액 87,700", page.input_value("#amount-input") == "87700",
              page.input_value("#amount-input"))
        check("관리급여: 회당 한도/횟수 안내 포함", "연간 15회" in row5m or "15회" in row5m, "안내 문구 확인")
        page.evaluate("document.querySelector('#result').scrollIntoView()")
        page.wait_for_timeout(250)
        shot(page, "mobile-390-managed-therapy")

        # ------------------------------------------------------------ 입원 + 중증 토글
        page.select_option("#item-select", "HE1010001")
        page.wait_for_timeout(150)
        page.click("#visit-group button[data-visit='in']")
        page.wait_for_timeout(150)
        check("입원 선택: 버튼 pressed", page.get_attribute("#visit-group button[data-visit='in']", "aria-pressed") == "true")
        before = page.inner_text("#result-table tbody tr[data-gen='5']")
        page.click("#severe-group button[data-severe='1']")
        page.wait_for_timeout(200)
        after = page.inner_text("#result-table tbody tr[data-gen='5']")
        check("중증 토글: 5세대 계산 변화", before != after, f"{before.replace(chr(10),' ')[:40]} → {after.replace(chr(10),' ')[:40]}")
        check("중증: 누적 자기부담 입력 노출", page.is_visible("#severe-cum-input"))
        check("중증: 500만원 상한 안내", "500만원" in after, "상한 안내 문구")
        page.click("#severe-group button[data-severe='0']")
        page.wait_for_timeout(150)

        # ------------------------------------------------------------ 종별·직접입력
        page.click("#inst-group button[data-inst='clinic']")
        page.wait_for_timeout(200)
        warn = page.inner_text("#result-warnings")
        check("의원 선택: 공개 범위 경고", "의원은 심평원 비급여 공개 API 대상이 아닙니다" in warn, warn[:60])
        page.click("#inst-group button[data-inst='tertiary']")
        page.select_option("#item-select", "direct")
        page.wait_for_timeout(150)
        page.fill("#amount-input", "1234567")
        page.dispatch_event("#amount-input", "input")
        page.wait_for_timeout(200)
        r1 = page.inner_text("#result-table tbody tr[data-gen='1']")
        check("직접입력: 금액 반영", "1234567" in page.inner_text("#result-meta").replace(",", "") or
              "1,234,567" in page.inner_text("#result-meta"), page.inner_text("#result-meta"))

        # 무결성: 보장액 + 최종부담 = 기준액 (전 세대)
        sums = page.eval_on_selector_all("#result-table tbody tr", """els => els.map(tr => {
            const c = tr.querySelector('.covered').textContent.replace(/[^0-9]/g,'');
            const p = tr.querySelector('.copay').textContent.replace(/[^0-9]/g,'');
            return {gen: tr.dataset.gen, sum: Number(c) + Number(p)};
        })""")
        uniq = {s["sum"] for s in sums if s["gen"] != "5"}
        check("무결성: 보장액+부담액=기준액(1~4세대 동일)", len(uniq) == 1, sums)

        # ------------------------------------------------------------ 딥링크
        page.goto(base + "/ko/calc/?item=SZ0840000&visit=out&inst=hospital", wait_until="load")
        page.wait_for_selector("[data-calc][data-ready='1']")
        page.wait_for_timeout(200)
        check("딥링크: 항목 선택 반영", page.input_value("#item-select") == "SZ0840000",
              page.input_value("#item-select"))
        check("딥링크: 종별 반영", page.get_attribute("#inst-group button[data-inst='hospital']", "aria-pressed") == "true")
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(150)
        shot(page, "mobile-390-calc-deeplink")

        # ------------------------------------------------------------ 계산기 페이지(모바일)
        page.goto(base + "/ko/calc/", wait_until="load")
        page.wait_for_selector("[data-calc][data-ready='1']")
        page.wait_for_timeout(200)
        ov2 = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check("계산기 페이지: 가로 스크롤 없음", ov2 <= 1, f"overflow={ov2}px")
        shot(page, "mobile-390-calc-top")
        page.evaluate("document.querySelector('#result').scrollIntoView()")
        page.wait_for_timeout(250)
        shot(page, "mobile-390-calc-compare")

        # ------------------------------------------------------------ 항목 목록/상세
        page.goto(base + "/ko/items/", wait_until="load")
        n_items = page.eval_on_selector_all(".item-grid .item-card", "els => els.length")
        check("항목 목록: 카드 13개", n_items >= 13, f"cards={n_items}")
        shot(page, "mobile-390-items")

        page.goto(base + "/ko/items/manual-therapy/", wait_until="load")
        h1i = page.inner_text("h1")
        body_i = page.inner_text("main")
        check("항목 상세: 관리급여 표시", "관리급여" in body_i and "43,850" in body_i, h1i)
        check("항목 상세: 관리급여 전환 상단 고지", page.is_visible("[data-managed-notice]"),
              page.inner_text("[data-managed-notice]")[:70].replace("\n", " "))
        if live:
            check("항목 상세: 실데이터 시세 표시", "전수 수집" in body_i and "병원급 기관별 공개가" in body_i, "")
        else:
            check("항목 상세: 가격 미수집 안내", "인증키" in body_i, "가격 데이터 상태 박스")
        shot(page, "mobile-390-item-manual-therapy")

        page.goto(base + "/ko/items/brain-mri/", wait_until="load")
        check("항목 상세: 뇌 MRI", "뇌 MRI" in page.inner_text("h1"))
        check("항목 상세: 공식 분류 표기", "자기공명영상진단료" in page.inner_text("main"))
        if live:
            main_txt = page.inner_text("main")
            check("항목 상세: 전수 수집 표기", "932/932" in main_txt, "")
            check("항목 상세: KOSIS 의원급 카드", page.is_visible("[data-kosis]") and "379,927" in main_txt, "")
            # 기관 목록 필터 동작
            page.wait_for_function("document.querySelector('[data-hosp-body] tr') && document.querySelector('[data-hosp-count]').textContent.includes('전체')", timeout=8000)
            n_all = page.eval_on_selector_all("[data-hosp-body] tr", "els => els.length")
            count_txt = page.inner_text("[data-hosp-count]")
            check("기관 목록: JSON 로드·렌더", n_all >= 10 and "932" in count_txt, count_txt[:60])
            page.select_option("[data-hosp-sido]", label="경기")
            page.wait_for_timeout(200)
            count_gy = page.inner_text("[data-hosp-count]")
            rows_gy = page.eval_on_selector_all("[data-hosp-body] tr", "els => els.map(e => e.children[2].textContent)")
            check("기관 목록: 시도 필터(경기)", "213곳" in count_gy and rows_gy and all("경기" in r for r in rows_gy),
                  count_gy[:60])
            page.select_option("[data-hosp-cl]", label="상급종합")
            page.wait_for_timeout(200)
            rows_cl = page.eval_on_selector_all("[data-hosp-body] tr", "els => els.map(e => e.children[1].textContent)")
            check("기관 목록: 종별 필터(상급종합)", rows_cl and all("상급종합" in r for r in rows_cl),
                  str(rows_cl[:3]))
            page.select_option("[data-hosp-sido]", label="전체 시도")
            page.select_option("[data-hosp-cl]", label="전체 종별")
            page.fill("[data-hosp-q]", "성빈센트")
            page.wait_for_timeout(250)
            rows_q = page.eval_on_selector_all("[data-hosp-body] tr", "els => els.map(e => e.children[0].textContent)")
            check("기관 목록: 병원명 검색", any("성빈센트" in r for r in rows_q), str(rows_q[:2]))
            page.fill("[data-hosp-q]", "")
            page.wait_for_timeout(200)
            page.evaluate("document.querySelector('[data-kosis]').scrollIntoView({block:'start'})")
            page.wait_for_timeout(250)
            shot(page, "mobile-390-item-brain-mri-kosis")

        # ------------------------------------------------------------ 세대 정리 · 안내 페이지
        page.goto(base + "/ko/insurance/", wait_until="load")
        body_ins = page.inner_text("main")
        for token in ("특약1", "특약2", "43,850", "Max(50%, 5만원)"):
            check(f"실손 정리: '{token}' 포함", token in body_ins, "")
        shot(page, "mobile-390-insurance")

        page.goto(base + "/ko/guide/", wait_until="load")
        body_g = page.inner_text("main")
        for token in ("공공누리 제1유형", "15001700", "병원급 이상", "cmmtTxt"):
            check(f"이용 안내: '{token}' 포함", token in body_g, "")
        shot(page, "mobile-390-guide")

        # ------------------------------------------------------------ 모든 페이지 가로 스크롤·배너
        pages = ["/ko/", "/ko/calc/", "/ko/items/", "/ko/insurance/", "/ko/guide/", "/ko/privacy/",
                 "/ko/items/brain-mri/", "/ko/items/manual-therapy/", "/ko/items/zirconia-implant/"]
        for path in pages:
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(120)
            o = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            vw = page.evaluate("window.innerWidth")
            if live:
                check(f"모바일390 스크롤·배너없음 {path}",
                      o <= 1 and vw == 390 and not page.is_visible("#preview-banner"),
                      f"overflow={o}, innerWidth={vw}")
            else:
                b = page.is_visible("#preview-banner")
                check(f"모바일390 스크롤·배너 {path}", o <= 1 and b and vw == 390,
                      f"overflow={o}, innerWidth={vw}, banner={b}")

        ctx.close()

        # ------------------------------------------------------------ 데스크톱 1440
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR",
                                   device_scale_factor=1)
        d = ctx2.new_page()
        d.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
        d.on("pageerror", lambda e: results["console_errors"].append(str(e)))

        d.goto(base + "/ko/", wait_until="load")
        d.wait_for_selector("[data-calc][data-ready='1']")
        d.wait_for_timeout(300)
        check("데스크톱1440: 랜딩 렌더", "비급여" in d.inner_text("h1"))
        ov3 = d.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check("데스크톱1440: 가로 스크롤 없음", ov3 <= 1, f"overflow={ov3}px")
        # 계산기·결과가 2단으로 배치되는지
        cols = d.evaluate("""() => {
            const a = document.querySelector('.grid.g2'); if (!a) return 'none';
            return getComputedStyle(a).gridTemplateColumns;
        }""")
        results["viewport_notes"].append(f"desktop .grid.g2 columns = {cols}")
        check("데스크톱1440: 2단 레이아웃", "px" in cols and len(cols.split()) >= 2, cols)
        shot(d, "desktop-1440-home-top")
        shot(d, "desktop-1440-home-full", full=True)

        d.goto(base + "/ko/calc/", wait_until="load")
        d.wait_for_selector("[data-calc][data-ready='1']")
        d.wait_for_timeout(250)
        shot(d, "desktop-1440-calc")

        # 5세대 제외 데스크톱(배지 가독성)
        d.select_option("#item-select", "SZ0840000")
        d.wait_for_timeout(250)
        row5d = d.inner_text("#result-table tbody tr[data-gen='5']")
        check("데스크톱1440: 5세대 제외 표시", "0원" in row5d and "보장 제외" in row5d, row5d.replace("\n", " ")[:60])
        d.evaluate("document.querySelector('#result').scrollIntoView()")
        d.wait_for_timeout(200)
        shot(d, "desktop-1440-gen5-excluded")

        d.goto(base + "/ko/items/", wait_until="load")
        d.wait_for_timeout(200)
        shot(d, "desktop-1440-items")
        d.goto(base + "/ko/insurance/", wait_until="load")
        d.wait_for_timeout(200)
        shot(d, "desktop-1440-insurance")
        if live:
            d.goto(base + "/ko/items/brain-mri/", wait_until="load")
            d.wait_for_function("document.querySelector('[data-hosp-count]').textContent.includes('전체')", timeout=8000)
            d.evaluate("document.querySelector('[data-kosis]').scrollIntoView({block:'start'})")
            d.wait_for_timeout(300)
            ov = d.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check("데스크톱1440: 뇌MRI KOSIS·기관목록 가로스크롤 없음", ov <= 1, f"overflow={ov}px")
            shot(d, "desktop-1440-item-brain-mri-real")
            d.goto(base + "/ko/", wait_until="load")
            d.wait_for_selector("[data-calc][data-ready='1']")
            d.wait_for_timeout(300)
            d.evaluate("document.querySelector('[data-compare-table]').scrollIntoView({block:'center'})")
            d.wait_for_timeout(250)
            shot(d, "desktop-1440-compare")
            d.goto(base + "/ko/privacy/", wait_until="load")
            check("개인정보처리방침 렌더", "개인정보처리방침" in d.inner_text("h1"))
            shot(d, "desktop-1440-privacy")
        ctx2.close()
        browser.close()
    httpd.shutdown()

    check("콘솔 오류 없음", not results["console_errors"], results["console_errors"][:3])
    fails = [c for c in results["checks"] if not c["ok"]]
    (BASE / "scripts" / "verify_result.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(results['checks']) - len(fails)}/{len(results['checks'])} 통과 · 스크린샷 {len(results['screenshots'])}장")
    if fails:
        for f in fails[:10]:
            print("  FAIL:", f["name"], "·", f["detail"][:120])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
