#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화면검수 후속 수정 전/후 실측: 14개 항목."""
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


JS_HEADER = """() => {
  const nav = document.querySelector('.nav');
  const links = [...document.querySelectorAll('.nav a')];
  const navR = nav.getBoundingClientRect();
  return {
    navScrollW: nav.scrollWidth, navClientW: nav.clientWidth,
    isScrollable: nav.classList.contains('is-scrollable'),
    mask: getComputedStyle(nav).webkitMaskImage.slice(0, 40),
    links: links.map(a => { const r = a.getBoundingClientRect();
      return {t: a.textContent.trim(), l: Math.round(r.left - navR.left),
              r: Math.round(r.right - navR.left), vis: r.right <= navR.right + 0.5}; }),
    docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}"""

JS_CHIP = """() => {
  const chip = document.querySelector('#amount-chip');
  if (!chip) return null;
  const rs = [...chip.getClientRects()].map(r => ({x: Math.round(r.x), y: Math.round(r.y),
    w: Math.round(r.width), h: Math.round(r.height)}));
  return {rects: rs, cs: getComputedStyle(chip).whiteSpace};
}"""

JS_TABLES = """() => {
  const out = {};
  document.querySelectorAll('.table-wrap').forEach((w, i) => {
    const t = w.querySelector('table');
    out['wrap' + i] = {cls: t.className, wrapClientW: w.clientWidth,
      tableScrollW: t.scrollWidth, overflow: w.scrollWidth > w.clientWidth + 1,
      wrapScrollW: w.scrollWidth};
  });
  return out;
}"""

JS_STACK_GAP = """() => {
  // /ko/insurance/ 첫 번째 스택 표의 '통원 공제 · 한도' 셀: ::before 라벨과 값 사이 간격
  const td = document.querySelector('table.stack td[data-label="통원 공제 · 한도"]');
  if (!td) return null;
  const cs = getComputedStyle(td, '::before');
  const tr = td.getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(td);
  const textRect = range.getBoundingClientRect();
  return {tdLeft: Math.round(tr.left), tdW: Math.round(tr.width),
    beforeW: cs.width, beforeContent: cs.content,
    textLeft: Math.round(textRect.left), gap: Math.round(textRect.left - tr.left - parseFloat(cs.width) - 24)};
}"""

JS_FONTS = """() => {
  const q = s => { const e = document.querySelector(s); if (!e) return null;
    const cs = getComputedStyle(e); return {fs: cs.fontSize, fw: cs.fontWeight, color: cs.color}; };
  return {
    regionNum: q('.plain.stack td.num'),
    regionMinMax: [...document.querySelectorAll('.plain.stack td.num')].map(e => getComputedStyle(e).fontSize),
    breadcrumbCur: q('.breadcrumb [aria-current="page"]'),
    breadcrumbSep: (() => { const e = document.querySelector('.breadcrumb span'); return e ? getComputedStyle(e).color : null; })(),
    amberBadge: q('.pill.amber'),
    mutedText: q('.section-lead'),
    copayCell: q('td.copay-cell'),
    coveredCell: q('td.covered-cell'),
    bestWho: q('.best .who'),
    bestBig: q('.best .big'),
    segBtn: (() => { const e = document.querySelector('.seg button'); if (!e) return null;
      const r = e.getBoundingClientRect(); return {h: Math.round(r.height)}; })(),
    chipBtn: (() => { const e = document.querySelector('.chip-btn'); if (!e) return null;
      const r = e.getBoundingClientRect(); return {h: Math.round(r.height)}; })(),
  };
}"""

PAGES = {
    "home": "/ko/",
    "calc": "/ko/calc/",
    "insurance": "/ko/insurance/",
    "brain-mri": "/ko/items/brain-mri/",
    "seoul": "/ko/regions/seoul/",
    "contact": "/ko/contact/",
    "guide": "/ko/guide/silson-1-5-generation-guide/",
}


def main():
    httpd, port = start_server()
    base = f"http://127.0.0.1:{port}"
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width in (360, 390, 400):
            pg = b.new_page(viewport={"width": width, "height": 800})
            pg.goto(base + "/ko/", wait_until="networkidle")
            res[f"header@{width}"] = pg.evaluate(JS_HEADER)
            res[f"chip@{width}"] = pg.evaluate(JS_CHIP)
            res[f"fonts@{width}"] = pg.evaluate(JS_FONTS)
            pg.close()
        # tables
        pg = b.new_page(viewport={"width": 360, "height": 800})
        pg.goto(base + "/ko/items/brain-mri/", wait_until="networkidle")
        res["tables@brain-mri"] = pg.evaluate(JS_TABLES)
        pg.goto(base + "/ko/regions/seoul/", wait_until="networkidle")
        res["tables@seoul"] = pg.evaluate(JS_TABLES)
        res["fonts@seoul"] = pg.evaluate(JS_FONTS)
        pg.goto(base + "/ko/insurance/", wait_until="networkidle")
        res["stackGap@insurance"] = pg.evaluate(JS_STACK_GAP)
        pg.goto(base + "/ko/contact/", wait_until="networkidle")
        res["contact@360"] = pg.evaluate("""() => {
          const f = document.querySelector('.form-embed iframe');
          const r = f ? f.getBoundingClientRect() : null;
          return {iframe: r ? {w: Math.round(r.width), h: Math.round(r.height)} : null,
            formVisible: f ? getComputedStyle(f).display : null,
            hasBadLink: !!document.querySelector('a[href*="mri-brain"]'),
            bodyText: document.body.innerText.includes('/ko/items/mri-brain/')};
        }""")
        # scope duplication on home
        pg.goto(base + "/ko/", wait_until="networkidle")
        res["scopeDup@home"] = pg.evaluate("""() => {
          const t = '동네 의원 개별 가격은 공개 범위 외이므로';
          return {count: document.body.innerText.split(t).length - 1};
        }""")
        b.close()
    httpd.shutdown()
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
