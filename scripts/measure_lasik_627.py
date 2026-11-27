#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뮤즈2 #627 잔여 2건 실측: (a) 라식 종별 표 데스크톱 1920px 스크롤,
(b) 모바일 390px 터치 크기 실측."""
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


JS_LASIK_1920 = """() => {
  const out = {docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
  // '심평원 병원급 공개가 시세' 카드 안 종별 표 (첫 번째 .table-wrap in that card)
  const h = [...document.querySelectorAll('h3')].find(e => e.textContent.includes('심평원 병원급 공개가 시세'));
  const card = h ? h.closest('.card') : null;
  const wrap = card ? card.querySelector('.table-wrap') : null;
  if (!wrap) return {...out, found: false};
  const table = wrap.querySelector('table');
  const wr = wrap.getBoundingClientRect();
  out.wrapScroll = wrap.scrollWidth - wrap.clientWidth;
  out.tableScrollW = table.scrollWidth; out.wrapClientW = wrap.clientWidth;
  // 머리글 '최저~최고' 가 카드 경계 안에 완전히 보이는지
  const ths = [...table.querySelectorAll('thead th')];
  out.headers = ths.map(th => {
    const r = th.getBoundingClientRect();
    return {t: th.textContent.trim(), visible: Math.round(r.right) <= Math.round(wr.right) + 1,
            right: Math.round(r.right), wrapRight: Math.round(wr.right)};
  });
  // 첫 행 범위 셀 가시성
  const cell = table.querySelector('tbody tr td[data-label="최저~최고"]');
  if (cell) {
    const r = cell.getBoundingClientRect();
    out.rangeCell = {text: cell.textContent.trim(), right: Math.round(r.right),
                     wrapRight: Math.round(wr.right), clipped: Math.round(r.right) > Math.round(wr.right) + 1,
                     lines: [...cell.getClientRects()].length};
  }
  return out;
}"""

JS_TOUCH = """() => {
  const out = {};
  const rowLinks = [...document.querySelectorAll('table.stack th[scope="row"] a')];
  out.rowLinks = rowLinks.slice(0, 3).map(a => Math.round(a.getBoundingClientRect().height));
  out.rowLinksMin = rowLinks.length ? Math.round(Math.min(...rowLinks.map(a => a.getBoundingClientRect().height))) : null;
  out.rowLinksN = rowLinks.length;
  const pills = [...document.querySelectorAll('a.pill')];
  out.pillsMin = pills.length ? Math.round(Math.min(...pills.map(a => a.getBoundingClientRect().height))) : null;
  out.pillsN = pills.length;
  const sum = (s) => { const e = document.querySelector(s); return e ? Math.round(e.getBoundingClientRect().height) : null; };
  out.faqSummary = sum('.faq summary');
  out.ruleSummary = sum('details.rule summary');
  const sels = [...document.querySelectorAll('select, input[type="number"], input[type="text"], input[type="search"]')];
  out.inputsMin = sels.length ? Math.round(Math.min(...sels.map(e => e.getBoundingClientRect().height))) : null;
  out.inputsN = sels.length;
  out.docOverflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  return out;
}"""


def main():
    httpd, port = start_server()
    results = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # (a) 데스크톱 1920
            ctx = browser.new_context(viewport={"width": 1920, "height": 1000})
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{port}/ko/items/lasik/")
            page.wait_for_timeout(600)
            results["1920-lasik"] = page.evaluate(JS_LASIK_1920)
            ctx.close()
            # (b) 모바일 390, 라이트/다크
            for dark in [False, True]:
                mode = "dark" if dark else "light"
                ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                          color_scheme="dark" if dark else "light")
                page = ctx.new_page()
                r = {}
                for path, key in [("/ko/regions/seoul/", "touch-seoul"),
                                  ("/ko/regions/", "touch-regions"),
                                  ("/ko/", "touch-home"),
                                  ("/ko/calc/", "touch-calc"),
                                  ("/ko/items/lasik/", "touch-lasik"),
                                  ("/ko/regions/daegu/", "touch-daegu")]:
                    page.goto(f"http://127.0.0.1:{port}{path}")
                    page.wait_for_timeout(500)
                    r[key] = page.evaluate(JS_TOUCH)
                results[f"390-{mode}"] = r
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
