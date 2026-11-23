#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""변경 전후 스크린샷 캡처: 라이트·다크 × 폭별 × 페이지별.
사용: python3 scripts/shots_milk.py OUTDIR"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import _browser  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

WIDTHS = [320, 360, 390, 480, 720, 768, 1024, 1440]
PAGES = ["/ko/", "/ko/calc/", "/ko/regions/"]


def start_server():
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(BASE / "dist"))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main():
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    httpd, port = start_server()
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for scheme in ("light", "dark"):
                ctx = browser.new_context(
                    color_scheme=scheme, viewport={"width": 390, "height": 844})
                page = ctx.new_page()
                for path in PAGES:
                    slug = path.strip("/").replace("/", "_") or "home"
                    for w in WIDTHS:
                        page.set_viewport_size({"width": w, "height": 844})
                        page.goto(base + path, wait_until="networkidle")
                        page.screenshot(
                            path=str(outdir / f"{scheme}-{slug}-{w}.png"))
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print("done", outdir)


if __name__ == "__main__":
    main()
