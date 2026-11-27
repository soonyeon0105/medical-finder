#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""밀크 교차 재검수(§15-9) 잔여 4건 후속 수정 실측: 360·375, 라이트/다크."""
from __future__ import annotations
import functools, http.server, json, socketserver, sys, threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def start_server():
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(BASE / "dist"))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


JS_TOUCH = """() => {
  const out = {};
  // 표 안 항목 링크 (지역 페이지 행 제목 링크)
  const rowLinks = [...document.querySelectorAll('table.stack th[scope="row"] a')];
  out.rowLinks = rowLinks.slice(0, 3).map(a => Math.round(a.getBoundingClientRect().height));
  out.rowLinksMin = rowLinks.length ? Math.round(Math.min(...rowLinks.map(a => a.getBoundingClientRect().height))) : null;
  out.rowLinksN = rowLinks.length;
  // 지역 pill (링크 pill)
  const pills = [...document.querySelectorAll('a.pill')];
  out.pillsMin = pills.length ? Math.round(Math.min(...pills.map(a => a.getBoundingClientRect().height))) : null;
  out.pillsN = pills.length;
  // FAQ summary / details.rule summary
  const sum = (s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().height) : null; };
  out.faqSummary = sum('.faq summary');
  out.ruleSummary = sum('details.rule summary');
  // select / input
  const sels = [...document.querySelectorAll('select, input[type="number"], input[type="text"], input[type="search"]')];
  out.inputsMin = sels.length ? Math.round(Math.min(...sels.map(e => e.getBoundingClientRect().height))) : null;
  out.inputsN = sels.length;
  return out;
}"""

JS_HOSP = """() => {
  const out = {docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
  const wrap = document.querySelector('.hosp-table')?.closest('.table-wrap');
  if (wrap) {
    const t = wrap.querySelector('table');
    out.wrapOverflow = wrap.scrollWidth > wrap.clientWidth + 1;
    out.tableScrollW = t.scrollWidth; out.wrapClientW = wrap.clientWidth;
  }
  // 긴 기관명 셀: 카드 오른쪽 경계를 넘는지
  const tds = [...document.querySelectorAll('.hosp-table td[data-label="기관"]')];
  out.longName = null;
  for (const td of tds) {
    if (td.textContent.includes('가톨릭대학교서울성모병원')) {
      const r = td.getBoundingClientRect();
      const card = td.closest('.card') || td.closest('.table-wrap');
      const cr = card.getBoundingClientRect();
      const rects = [...td.getClientRects()].map(x => Math.round(x.width));
      out.longName = {cellRight: Math.round(r.right), cardRight: Math.round(cr.right),
                      overflow: Math.round(r.right - cr.right), lineWidths: rects};
    }
  }
  // 스택 표의 기관 셀 줄바꿈 여부: 셀 높이가 1줄 초과인지
  out.instCellLines = tds.slice(0, 12).map(td => ({n: td.textContent.slice(0, 12), h: Math.round(td.getBoundingClientRect().height)}));
  return out;
}"""

JS_HOME_CMP = """() => {
  const t = document.querySelector('table[data-compare-table]');
  if (!t) return null;
  const row = t.querySelector('tbody tr');
  const cells = [...row.querySelectorAll('td')].map(td => ({
    label: td.getAttribute('data-label'),
    before: getComputedStyle(td, '::before').content,
    text: td.textContent.trim().slice(0, 40),
    rects: [...td.getClientRects()].length,
  }));
  return {cells, docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""

JS_H1 = """() => {
  const h1 = document.querySelector('.page-head h1');
  if (!h1) return null;
  const rects = [...h1.getClientRects()].map(r => ({y: Math.round(r.y), w: Math.round(r.width)}));
  const lines = new Set(rects.map(r => r.y)).size;
  return {text: h1.textContent.trim(), lines, rects,
          lead: document.querySelector('.page-head .section-lead')?.textContent.trim().slice(0, 60),
          docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


def main():
    httpd, port = start_server()
    results = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width, label in [(360, "360"), (375, "375")]:
                for dark in [False, True]:
                    mode = "dark" if dark else "light"
                    ctx = browser.new_context(viewport={"width": width, "height": 800},
                                              color_scheme="dark" if dark else "light")
                    page = ctx.new_page()
                    key = f"{label}-{mode}"
                    r = {}
                    page.goto(f"http://127.0.0.1:{port}/ko/regions/seoul/")
                    page.wait_for_timeout(400)
                    r["touch-seoul"] = page.evaluate(JS_TOUCH)
                    r["h1-seoul"] = page.evaluate(JS_H1)
                    page.goto(f"http://127.0.0.1:{port}/ko/regions/gangwon/")
                    page.wait_for_timeout(400)
                    r["h1-gangwon"] = page.evaluate(JS_H1)
                    page.goto(f"http://127.0.0.1:{port}/ko/regions/")
                    page.wait_for_timeout(400)
                    r["touch-regions"] = page.evaluate(JS_TOUCH)
                    page.goto(f"http://127.0.0.1:{port}/ko/")
                    page.wait_for_timeout(400)
                    r["touch-home"] = page.evaluate(JS_TOUCH)
                    r["home-cmp"] = page.evaluate(JS_HOME_CMP)
                    page.goto(f"http://127.0.0.1:{port}/ko/calc/")
                    page.wait_for_timeout(400)
                    r["touch-calc"] = page.evaluate(JS_TOUCH)
                    page.goto(f"http://127.0.0.1:{port}/ko/items/lasik/")
                    page.wait_for_timeout(600)
                    r["hosp-lasik"] = page.evaluate(JS_HOSP)
                    page.goto(f"http://127.0.0.1:{port}/ko/regions/daegu/")
                    page.wait_for_timeout(600)
                    r["hosp-daegu"] = page.evaluate(JS_HOSP)
                    ctx.close()
                    results[key] = r
            browser.close()
    finally:
        httpd.shutdown()
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
