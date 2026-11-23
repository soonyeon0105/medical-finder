#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""밀크 검수 지적 실측: 헤더 메뉴 가시성 + 다크 채움 버튼 대비 + 탭 타겟 크기.
dist/ 를 로컬 http 서버로 띄우고 headless Chromium 으로 측정한다.
사용: python3 scripts/measure_milk.py [--out DIR]"""
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
import _browser  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

WIDTHS = [320, 360, 390, 480, 720, 768, 1024, 1440]
PAGES = ["/ko/", "/ko/calc/", "/ko/insurance/", "/ko/regions/"]


def start_server():
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(BASE / "dist"))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


HEADER_JS = """() => {
  const wrap = document.querySelector('.site-header .wrap');
  const logo = document.querySelector('.logo');
  const txt = document.querySelector('.logo .txt');
  const nav = document.querySelector('.nav');
  const links = [...document.querySelectorAll('.nav a')];
  const navR = nav.getBoundingClientRect();
  const items = links.map(a => {
    const r = a.getBoundingClientRect();
    const vis = r.left >= navR.left - 0.5 && r.right <= navR.right + 0.5;
    return {label: a.textContent.trim(), left: Math.round(r.left - navR.left),
            right: Math.round(r.right - navR.left), w: Math.round(r.width),
            h: Math.round(r.height), visible: vis};
  });
  const pills = [...document.querySelectorAll('.hero .pills .pill')].map(p => {
    const r = p.getBoundingClientRect();
    return {t: p.textContent.trim().slice(0, 12), w: Math.round(r.width), h: Math.round(r.height)};
  });
  return {
    viewport: window.innerWidth,
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    wrapW: Math.round(wrap.getBoundingClientRect().width),
    wrapContentW: Math.round(wrap.clientWidth),
    logoW: Math.round(logo.getBoundingClientRect().width),
    txtW: txt ? Math.round(txt.getBoundingClientRect().width) : null,
    txtFont: txt ? getComputedStyle(txt).fontSize : null,
    navClientW: Math.round(nav.clientWidth),
    navScrollW: Math.round(nav.scrollWidth),
    navHidden: Math.round(nav.scrollWidth - nav.clientWidth),
    items, pills,
  };
}"""

CONTRAST_JS = """() => {
  function lum(rgb) {
    const m = rgb.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
    if (!m) return null;
    const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    const [r, g, b] = [f(+m[1]), f(+m[2]), f(+m[3])];
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function ratio(fg, bg) {
    const l1 = lum(fg), l2 = lum(bg);
    if (l1 === null || l2 === null) return null;
    const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  }
  const out = [];
  // 채움 버튼: .btn(기본), aria-pressed=true인 .seg 버튼
  document.querySelectorAll('.btn, .seg button[aria-pressed="true"]').forEach(el => {
    const cs = getComputedStyle(el);
    out.push({sel: el.className || el.tagName, text: (el.textContent || '').trim().slice(0, 18),
              color: cs.color, bg: cs.backgroundColor, ratio: ratio(cs.color, cs.backgroundColor)});
  });
  return out;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    httpd, port = start_server()
    base = f"http://127.0.0.1:{port}"
    result = {"header": {}, "contrast": {}}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for scheme in ("light", "dark"):
                ctx = browser.new_context(
                    color_scheme=scheme, viewport={"width": 390, "height": 844})
                page = ctx.new_page()
                for w in WIDTHS:
                    page.set_viewport_size({"width": w, "height": 844})
                    page.goto(base + "/ko/", wait_until="networkidle")
                    result["header"][f"{scheme}-{w}"] = page.evaluate(HEADER_JS)
                # 다크 대비: 계산기·보험 페이지의 채움 버튼
                for path in ("/ko/calc/", "/ko/insurance/", "/ko/"):
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.goto(base + path, wait_until="networkidle")
                    result["contrast"][f"{scheme}-{path}"] = page.evaluate(CONTRAST_JS)
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
