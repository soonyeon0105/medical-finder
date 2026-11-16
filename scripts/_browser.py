#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
브라우저 실행 환경 보정 헬퍼.

이 작업 환경의 headless Chromium 은 libatk-1.0 / libatk-bridge-2.0 / libatspi 등
시스템 라이브러리가 빠져 있으면 실행되지 않는다(sudo 없음). 그래서 필요한 .deb 를
프로젝트 안 .deps/ 로 내려받아 풀어 두고, 브라우저 프로세스가 그 경로를 먼저 보도록
LD_LIBRARY_PATH 를 잡아 준다. .deps/ 가 없으면 아무 것도 하지 않는다.

  사용:  import _browser   (playwright import 전에)
"""
from __future__ import annotations

import os
from pathlib import Path

DEPS_LIB = Path(__file__).resolve().parent.parent / ".deps" / "usr" / "lib" / "x86_64-linux-gnu"


def ensure_libs() -> str | None:
    if not DEPS_LIB.is_dir():
        return None
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    if str(DEPS_LIB) in cur.split(":"):
        return str(DEPS_LIB)
    os.environ["LD_LIBRARY_PATH"] = f"{DEPS_LIB}:{cur}" if cur else str(DEPS_LIB)
    return str(DEPS_LIB)


ensure_libs()
