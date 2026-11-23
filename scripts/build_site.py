#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
메디컬·비급여 시세 비교 파인더 — 국내(/ko/) 정적 사이트 빌더 (M-03 뼈대)

입력
  data/catalog_items.json      비급여 항목 카탈로그(개수는 catalog_items.json 이 정한다)
  data/hira_dataset.json       prepare_data.py 산출물(실데이터 또는 픽스처). 없으면 픽스처 모드로 동작

출력 (dist/)
  /ko/                    랜딩 + 계산기
  /ko/calc/               계산기(전체 옵션)
  /ko/items/              항목 전체 목록
  /ko/items/{slug}/       항목 상세
  /ko/insurance/          1~5세대 실손 정리(2026 개편 반영)
  /ko/guide/              가이드 허브 · 이용 안내 · 데이터 출처 · 범위 고지
  /ko/guide/{slug}/       실손·비급여 해설 가이드 8편(T-M12 5편 + T-M12-B 3편)
  /assets/*, robots.txt, sitemap.xml, 404.html

사용법: python3 scripts/build_site.py [--out DIR] [--base URL] [--live]
  --live 를 주지 않으면 '테스트 픽스처 프리뷰' 모드로 빌드한다(배너 표시 + noindex).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys_path_dir = str(Path(__file__).resolve().parent)
import sys as _sys  # noqa: E402
if sys_path_dir not in _sys.path:
    _sys.path.insert(0, sys_path_dir)
from guides import GUIDES as GUIDE_ARTICLES  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DATA = BASE_DIR / "data"
ASSETS = BASE_DIR / "assets"
DIST = BASE_DIR / "dist"

SITE_NAME = "메디컬 비급여 시세 파인더"
SITE_BASE = "https://kr.kmedicheck.com"   # --base 로 교체
OWNER = "내 손안에 복지 (9welfare)"

# ── 브랜딩 (2026-11-17 K-MediCheck 클린 메디컬 톤 통일)
BRAND = "K-MediCheck"
COL_TEAL = "#0F766E"
COL_NAVY = "#0F2942"
MARK_PATH = "M16 7.4V24.6M7.4 16H20.4L26.6 10.4"
# 구글 폼 (tearsstream52@gmail.com · 2026-11-17 생성 · 응답자 이메일 미수집 · 게시·응답중)
GOOGLE_FORM_KO = ("https://docs.google.com/forms/d/e/"
                  "1FAIpQLSe-mSKsokTH-X-Pmvrlv5CUSMQjXzUNlzK_-gNK0ZPPy0-YIQ/viewform")
ADS_TXT = "google.com, pub-9496998678693709, DIRECT, f08c47fec0942fa0\n"


def logo_svg(size: int = 30, cls: str = "logo-mark") -> str:
    return (
        f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 32 32" '
        'aria-hidden="true" focusable="false">'
        f'<rect width="32" height="32" rx="7.5" fill="{COL_NAVY}"/>'
        f'<path d="{MARK_PATH}" fill="none" stroke="#14B8A6" stroke-width="4.6" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
BUILD_TS = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
DATA_DATE = "2026-11-17"          # 오픈API 수집·조회일
DATA_PERIOD = "건강보험심사평가원 2026년 비급여 공개 자료 기준 · 오픈API 조회 2026-11-17"
KOSIS_PERIOD = "통계청 KOSIS 2026년(자료갱신 2026-10-23)"
KOSIS_APPROVAL = "354006"

# ---------------------------------------------------------------- 분석 태그 (GA4)
GA4_ID = "G-9EQ04J49YZ"
GA4_SNIPPET = (
    "<!-- Google Analytics 4 (GA4) · 방문 통계 -->\n"
    f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>\n'
    "<script>\n"
    "window.dataLayer = window.dataLayer || [];\n"
    "function gtag(){dataLayer.push(arguments);}\n"
    "gtag('js', new Date());\n"
    f"gtag('config', '{GA4_ID}', {{ anonymize_ip: true }});\n"
    "</script>"
)

PREVIEW = True     # --live 로 끌 수 있다
ITEM_COUNT = 0   # build() 가 카탈로그 길이로 채운다(화면 문구용)
HOSP_ROWS = 0    # build() 가 실제 수집 기관 행 수로 채운다(화면 문구용)
COLLECTED_ITEMS = 0  # build() 가 기관 행이 있는 항목 수로 채운다(화면 문구용)
DATASET: dict | None = None      # data/hira_dataset.json (없으면 가격 미표시)
HOSPITALS: dict | None = None    # data/hospitals.json (병원급 기관 목록)

# ---------------------------------------------------------------- 검색엔진 소유확인
# 네이버 서치어드바이저(tearsstream) → https://medical-finder-kr.pages.dev 추가 시 발급.
# 메타태그·확인파일 둘 다 빌드에 넣는다(지우면 소유확인이 풀린다).
NAVER_VERIFY = "65f0d284f2bc3f6c8cf5590d03848e4e70783bae"
NAVER_VERIFY_FILE = "naver8272c0d9d8609fb2d25fc7ee9ed8f0d9.html"

NAV = [
    ("/ko/calc/", "실손 계산기", "계산기"),
    ("/ko/switch-gen5/", "5세대 전환 손익", "전환"),
    ("/ko/items/", "비급여 항목", "항목"),
    ("/ko/regions/", "지역별 시세", "지역"),
    ("/ko/insurance/", "1~5세대 실손", "세대별"),
    ("/ko/guide/", "가이드", "가이드"),
]

SCOPE_LINE = ("병원급 이상 심평원 공개 가격 기준(공공누리 제1유형) · 동네 의원 개별 가격은 공개 범위 외이므로 "
              "방문 전 확인 (참고용 전국 의원 평균·중간값은 통계청 KOSIS 통계 기준)")
SCOPE_LONG = (
    "이 서비스의 가격은 건강보험심사평가원이 공공데이터포털로 공개하는 <b>병원급 이상</b> 의료기관"
    "(상급종합·종합병원·병원·요양병원·정신병원·치과병원·한방병원)의 비급여 진료비입니다. "
    "동네 <b>의원·치과의원·한의원</b>의 <b>개별 기관 가격은 공개 API 제공 범위가 아니어서 표시하지 않으며</b>, "
    "방문 전 유선 확인을 안내합니다. 대신 <b>전국 의원급 규모의 평균·중간값</b>만 통계청 KOSIS"
    "(승인번호 354006, 심평원 작성) 공개 통계표에서 수집해 <b>참고값</b>으로 함께 보여 줍니다."
)

GEN_TABLE = [
    ("1세대", "~2009.9",
     "입원 0%(전액 보장) · 통원 5,000원 공제",
     "입원 0%(전액 보장) · 통원 5,000원 공제",
     "상품·시기별 약관 차이가 가장 큼"),
    ("2세대", "2009.10~2017.3",
     "표준형 20% · 선택형Ⅱ 10%",
     "20%",
     "통원 Max(20%, 의원 1만·병원 1.5만·종합/상급 2만)"),
    ("3세대(착한실손)", "2017.4~2021.6",
     "20%",
     "기본 20% · 특약 30%",
     "특약(도수·체외충격파·증식·비급여 주사·MRI) 통원 Max(30%, 2만원) · 갱신 15년"),
    ("4세대", "2021.7~2026.4",
     "입원 20% · 통원 Max(20%, 1·2만원)",
     "입원 30% · 통원 Max(30%, 3만원)",
     "통원 회당 보장 20만원 · 연 5천만원 · 비급여 차등할증"),
    ("5세대", "2026.5.6 출시~",
     "입원 20% · 통원 Max(건보 본인부담률, 20%, 1·2만원)",
     "특약1(중증) 입원 30% · 통원 Max(30%, 3만원) / 특약2(비중증) 입원 50% · 통원 Max(50%, 5만원)",
     "특약1 연 5천만·통원 회당 20만 / 특약2 연 1천만·통원 일당 20만·입원 회당 300만"),
]

EXCLUDED5 = [
    ("근골격계 물리치료", "도수치료(2026.7 관리급여 전환)·신장분사치료 등", "MZ0070000"),
    ("체외충격파치료", "어깨 석회화·족저근막염 등", "SZ0840000"),
    ("비급여 주사제", "증식치료·신경성형술 등 주사 계열", "MY1420000"),
    ("시력교정술(라식·라섹)", "미용·생활 편의 목적 — 세대와 관계없이 보장 제외", "2Z9610001"),
    ("예방접종", "질병 치료 목적이 아니라 보장 대상 아님(대상포진·HPV 등)", "3Z5200303"),
    ("치과 비급여 보철", "크라운·임플란트 등 치과치료 비급여 — 약관상 보장 제외", "UW609F350"),
    ("미등재 신의료기술", "첨단재생의료 등 미등재 기술", None),
    ("D등급 치료", "한국보건의료연구원 재평가 D등급(권고하지 않음)", None),
]


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def won(n) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}원"


def ds_item(code: str) -> dict | None:
    for it in (DATASET or {}).get("items", []):
        if it["code"] == code:
            return it
    return None


def default_amount(item: dict) -> int:
    """계산기 초기 금액 — 실데이터가 있으면 병원급 중간값, 없으면 카탈로그 예시값.
    price_fixture가 null인 항목(심평원 공개 목록 미수록)은 지어낸 금액을 넣지 않고 0."""
    if item.get("payment") == "관리급여":
        return int(item["price_fixture"])
    ds = ds_item(item["code"])
    if ds and ds.get("has_data") and (ds.get("stats") or {}).get("price"):
        return int(ds["stats"]["price"]["median"] or ds["stats"]["price"]["avg"])
    return int(item.get("price_fixture") or 0)


def not_listed(item: dict) -> bool:
    """심평원 비급여 공개 목록(15001700) 미수록 확정 항목 — 공개 코드·가격이 없다."""
    return item.get("code_status") == "not_listed"


def code_disp(item: dict) -> str:
    """카드·표의 코드 표기. 미수록 항목은 내부 코드를 심평원 코드처럼 보이지 않게 한다."""
    return "심평원 공개 코드 없음" if not_listed(item) else item["code"]


def codes_inline(item: dict) -> str:
    """복수 코드 항목의 전체 코드 병기 (대표 코드 포함)."""
    return "<br>".join(
        f"<code>{esc(c['code'])}</code> {esc(c['label'])}" for c in item.get("codes") or [])


# ------------------------------------------------------------------ 공통 레이아웃
def breadcrumb_html(crumbs: list[tuple[str, str]]) -> str:
    parts = []
    for i, (href, label) in enumerate(crumbs):
        if i:
            parts.append('<span>›</span>')
        if href:
            parts.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        else:
            parts.append(f'<span aria-current="page">{esc(label)}</span>')
    return f'<nav class="breadcrumb" aria-label="위치"><div class="wrap">{"".join(parts)}</div></nav>'


def breadcrumb_jsonld(crumbs: list[tuple[str, str]]) -> dict:
    items = []
    for i, (href, label) in enumerate(crumbs, start=1):
        url = SITE_BASE + href if href else SITE_BASE + "/ko/"
        items.append({"@type": "ListItem", "position": i, "name": label, "item": url})
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def layout(path: str, title: str, desc: str, body: str, crumbs: list[tuple[str, str]],
           jsonld: list[dict] | None = None, current: str = "", og_image: str = "",
           extra_js: str = "") -> str:
    canonical = SITE_BASE + path
    nav_html = "".join(
        f'<a href="{esc(href)}"{" aria-current=\"page\"" if href == current else ""}>'
        f'<span class="full">{esc(label)}</span><span class="abbr">{esc(short)}</span></a>'
        for href, label, short in NAV)
    robots = ('<meta name="robots" content="noindex,nofollow">' if PREVIEW
              else '<meta name="robots" content="index,follow">')
    banner = (
        '<div class="preview-banner" id="preview-banner" role="note">'
        '<span class="pb-dot"></span><strong>테스트 픽스처 프리뷰</strong> · '
        '화면의 금액은 UI 동작 확인용 <strong>예시</strong>이며 실제 심평원 공개 가격이 아닙니다. '
        'data.go.kr 인증키를 연결하면 실제 수집 데이터로 대체됩니다.'
        '</div>' if PREVIEW else "")
    scope_strip = ('<div class="scope-strip"><div class="wrap">' + SCOPE_LINE + '</div></div>')
    ld = ""
    for obj in (jsonld or []):
        ld += f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'
    og_extra = ('<meta property="og:locale" content="ko_KR">\n')
    if og_image:
        og_extra += (
            f'<meta property="og:image" content="{esc(og_image)}">\n'
            '<meta property="og:image:type" content="image/png">\n'
            '<meta property="og:image:width" content="1200">\n'
            '<meta property="og:image:height" content="630">\n'
            '<meta property="og:image:alt" content="실손 5세대 전환 손익 시뮬레이터 — 연간 절약·손해와 손익분기">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:image" content="{esc(og_image)}">\n')
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
{og_extra}<meta name="color-scheme" content="light dark">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f6f8f7">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#101613">
<meta name="naver-site-verification" content="{esc(NAVER_VERIFY)}">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="preload" href="/assets/fonts/PretendardVariable.subset.91.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/fonts/pretendardvariable-dynamic-subset.css">
<link rel="stylesheet" href="/assets/style.css">
{GA4_SNIPPET}
{ld}
</head>
<body>
{banner}
<header class="site-header">
  <div class="wrap">
    <a class="logo" href="/ko/">{logo_svg(28)}<span class="txt">{esc(SITE_NAME)}</span></a>
    <nav class="nav" aria-label="주요 메뉴">{nav_html}</nav>
  </div>
</header>
{breadcrumb_html(crumbs)}
<main id="main">
{scope_strip}
{body}
</main>
<footer class="site-footer">
  <div class="wrap">
    <div class="cols">
      <div>
        <b>{esc(SITE_NAME)}</b><br>
        병원급 이상 비급여 공개가와 1~5세대 실손 보장액을 함께 계산하는 중립 정보 사이트입니다.
        특정 병원 추천·예약·상담 알선은 하지 않습니다.
      </div>
      <div>
        <b>바로가기</b><br>
        <a href="/ko/calc/">실손 계산기</a><br>
        <a href="/ko/items/">비급여 항목 {ITEM_COUNT}개</a><br>
        <a href="/ko/regions/">지역별 시세 17개 시·도</a><br>
        <a href="/ko/insurance/">1~5세대 실손 정리</a><br>
        <a href="/ko/guide/">이용 안내 · 데이터 출처</a>
      </div>
      <div>
        <b>사이트 정보</b><br>
        <a href="/ko/about/">사이트 소개</a><br>
        <a href="/ko/editorial-policy/">편집·데이터 정책</a><br>
        <a href="/ko/medical-disclaimer/">의료 면책 고지</a><br>
        <a href="/ko/contact/">문의 및 오류 제보</a><br>
        <a href="/ko/privacy/">개인정보처리방침</a>
      </div>
      <div>
        <b>데이터</b><br>
        건강보험심사평가원 비급여진료비정보조회서비스<br>
        공공데이터포털 15001700 · 공공누리 제1유형<br>
        통계청 KOSIS 승인번호 {esc(KOSIS_APPROVAL)}(의원·치과의원 규모, 2026)<br>
        <span class="muted">{esc(DATA_PERIOD)} · 빌드 {esc(BUILD_TS)}</span>
      </div>
    </div>
    <div class="legal">
      본 사이트의 계산 결과는 입력값과 공개된 제도 기준으로 산출한 <b>추정치</b>이며, 실제 보험금 지급액은
      가입 상품·약관·청구 이력에 따라 달라집니다. 의료기관 가격은 인력·시설·장비에 따라 달라질 수 있고
      변경 보고의 행정 처리 기간 때문에 실시간 반영되지 않을 수 있습니다.
      본 사이트는 병원급 이상 공개 가격만 다루며 의원급 <b>개별</b> 가격은 제공하지 않습니다
      (전국 의원급 평균·중간값은 통계청 KOSIS 통계 기준 참고값).
      의료법 제27조에 따라 특정 의료기관의 환자 유인·알선·광고를 하지 않습니다.
      <a href="/ko/privacy/">개인정보처리방침</a> · <a href="/ko/medical-disclaimer/">의료 면책 고지</a><br>
      {BRAND} 패밀리 — 글로벌 의료 가격 인덱스 <a href="https://kmedicheck.com/en/" rel="noopener" target="_blank">kmedicheck.com</a> ·
      {esc(OWNER)} · {esc(BUILD_TS)} 빌드.
    </div>
  </div>
</footer>
<script src="/assets/calc.js" defer></script>
<script src="/assets/med-data.js" defer></script>
<script src="/assets/app.js" defer></script>
{extra_js}
</body>
</html>
"""


# ------------------------------------------------------------------ 계산기 블록
def calc_block(items: list[dict], default_code: str, heading: str = "1~5세대 실손 보장액 계산",
               sub: str = "항목·금액·입원/통원만 고르면 5개 세대를 한 번에 비교합니다.") -> str:
    opts = "".join(
        f'<option value="{esc(it["code"])}">{esc(it["name"])} '
        f'({"공개 코드 없음" if not_listed(it) else esc(it["code"])})</option>' for it in items)
    first = next((it for it in items if it["code"] == default_code), items[0])
    return f"""
<section class="calc" data-calc aria-labelledby="calc-title">
  <div class="calc-head">
    <h2 id="calc-title">{esc(heading)}</h2>
    <p>{esc(sub)}</p>
    <div class="scope-note" style="margin-bottom:14px">
      {SCOPE_LINE}
    </div>
  </div>
  <div class="calc-body">
    <div class="field">
      <label for="item-select">비급여 항목</label>
      <select id="item-select">{opts}<option value="direct">직접 입력 (금액만)</option></select>
    </div>
    <div class="field">
      <label for="amount-input">진료비 금액 <span class="hint">(병원에서 받은 비급여 금액)</span>
        <span class="chip-inline" id="amount-chip">예시 금액</span></label>
      <div class="amount-row">
        <input type="number" id="amount-input" inputmode="numeric" min="0" step="1000"
               value="{default_amount(first)}" aria-describedby="item-hint amount-error">
        <span class="unit">원</span>
      </div>
      <p class="field-error" id="amount-error" role="alert" aria-live="polite" hidden></p>
      <div class="row-note" id="item-hint">{esc(first['name'])} · {esc(first['summary'])}</div>
    </div>
    <div class="field">
      <span class="label" id="visit-label">입원 / 통원</span>
      <div class="seg two" id="visit-group" role="group" aria-labelledby="visit-label">
        <button type="button" data-visit="out" aria-pressed="true">통원(외래)</button>
        <button type="button" data-visit="in" aria-pressed="false">입원</button>
      </div>
    </div>
    <div class="field">
      <span class="label" id="inst-label">의료기관 종별 <span class="hint">(공제액 계산 기준)</span></span>
      <div class="seg" id="inst-group" role="group" aria-labelledby="inst-label">
        <button type="button" data-inst="tertiary" aria-pressed="true">상급종합</button>
        <button type="button" data-inst="general" aria-pressed="false">종합병원</button>
        <button type="button" data-inst="hospital" aria-pressed="false">병원</button>
        <button type="button" data-inst="clinic" aria-pressed="false">의원(참고)</button>
      </div>
      <div class="row-note">의원은 공개 API 범위가 아니며, 종별 공제액 계산을 위한 참고 선택입니다.</div>
    </div>
    <div class="two-col">
      <div class="field">
        <span class="label" id="severe-label">중증(산정특례) 질환 치료</span>
        <div class="seg two" id="severe-group" role="group" aria-labelledby="severe-label">
          <button type="button" data-severe="0" aria-pressed="true">아니오</button>
          <button type="button" data-severe="1" aria-pressed="false">예</button>
        </div>
        <div class="row-note">5세대 특약1(중증)/특약2(비중증) 구분에만 적용됩니다.</div>
      </div>
      <div class="field">
        <label for="gen2-select">2세대 가입유형</label>
        <select id="gen2-select">
          <option value="standard">표준형 (급여 80%)</option>
          <option value="select2">선택형Ⅱ (급여 90%)</option>
        </select>
      </div>
    </div>
    <div class="field" id="rounds-row" style="display:none">
      <label for="rounds-input">관리급여 시행 횟수 <span class="hint">(1회 {won(43850)} · 연 15회/예외 24회)</span></label>
      <input type="number" id="rounds-input" inputmode="numeric" min="1" max="24" step="1" value="1">
    </div>
    <div class="field" id="severe-cum-row" style="display:none">
      <label for="severe-cum-input">올해 중증 입원 자기부담 누적액 <span class="hint">(선택 · 5세대 연 500만원 상한 계산)</span></label>
      <div class="amount-row">
        <input type="number" id="severe-cum-input" inputmode="numeric" min="0" step="10000" value="">
        <span class="unit">원</span>
      </div>
    </div>
    <div class="managed-box" id="managed-box"></div>
  </div>

  <div class="result" id="result">
    <div class="result-head">
      <h3>세대별 예상 보장액</h3>
      <span class="sub" id="result-meta">조건을 확인하는 중</span>
    </div>
    <div id="result-summary"></div>
    <div class="cmp-wrap">
      <table class="cmp" id="result-table">
        <caption class="sr-only">1세대부터 5세대까지 같은 조건에서의 예상 보장액 비교</caption>
        <thead>
          <tr>
            <th scope="col">세대</th>
            <th scope="col">자기부담 기준</th>
            <th scope="col">예상 보장액</th>
            <th scope="col">환자 최종 부담</th>
            <th scope="col">적용 규칙 · 한도</th>
          </tr>
        </thead>
        <tbody>
          <tr><td colspan="5" style="color:var(--muted)">계산 결과를 불러오는 중…</td></tr>
        </tbody>
      </table>
    </div>
    <ul class="warn-list" id="result-warnings" style="display:none"></ul>
    <p class="calc-foot">
      ※ 예상 보장액은 공개된 제도 기준으로 계산한 추정치입니다. 실제 지급액은 가입 약관, 자기부담금 누적,
      청구 이력에 따라 달라집니다. 연간 한도(5세대 특약1 5천만원 / 특약2 1천만원 등)는 누적 청구가 필요해
      안내로만 표시합니다.
    </p>
    <details class="rule">
      <summary>계산 기준 자세히 보기</summary>
      <ul class="limits" style="font-size:12.5px">
        <li>1세대: 입원 100%, 통원 5,000원 공제 후 100% (표준형 기준 · 약관 차이 있음)</li>
        <li>2세대: 비급여 80% · 통원은 20%와 외래공제(의원 1만·병원 1.5만·종합/상급 2만) 중 큰 금액</li>
        <li>3세대: 기본 비급여 20% · 특약(도수·체외충격파·증식·비급여 주사·MRI)은 통원 Max(30%, 2만원)</li>
        <li>4세대: 비급여 입원 30% · 통원 Max(30%, 3만원), 통원 회당 보장 20만원 한도</li>
        <li>5세대: 특약1(중증) 입원 30%·통원 Max(30%, 3만원) / 특약2(비중증) 입원 50%·통원 Max(50%, 5만원),
          제외 항목은 보장 0원</li>
        <li>도수치료: 2026.7.1부터 관리급여 — 1회 43,850원(종별 동일), 본인부담률 95%로 급여 규칙 적용</li>
      </ul>
    </details>
  </div>
</section>
"""


def gen_table_html() -> str:
    rows = "".join(
        f"<tr><th scope=\"row\">{esc(n)}<br><span style=\"font-weight:500;color:var(--muted)\">{esc(p)}</span></th>"
        f"<td data-label=\"급여 자기부담\">{esc(g)}</td>"
        f"<td data-label=\"비급여 자기부담\">{esc(b)}</td>"
        f"<td data-label=\"통원 공제 · 한도\">{esc(l)}</td></tr>"
        for n, p, g, b, l in GEN_TABLE)
    return f"""
<div class="table-wrap">
  <table class="plain stack">
    <thead><tr><th scope="col">세대</th><th scope="col">급여 자기부담</th><th scope="col">비급여 자기부담</th><th scope="col">통원 공제 · 한도</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<p class="calc-foot">표의 %는 모두 <b>자기부담률</b>(환자가 부담하는 비중)입니다.
<b>Max(A, B)</b>는 '비율 A로 계산한 금액'과 '최소공제액 B' 중 <b>큰 금액을 공제</b>한다는 뜻입니다.
상품별 약관(연간 한도·자기부담금 누적·갱신 조건)에 따라 실제 금액은 달라집니다.</p>
"""


def faq_html(faqs: list[tuple[str, str]]) -> str:
    return '<div class="faq">' + "".join(
        f'<details><summary>{esc(q)}</summary><div class="a">{esc(a)}</div></details>' for q, a in faqs
    ) + "</div>"


def faq_jsonld(faqs: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs
        ],
    }


def coverage_label(it: dict) -> str:
    """목록·표에 쓰는 한 줄 보장 표기(세대별 제외 → 관리급여 → 5세대 제외 → 비중증)."""
    excl = it.get("excluded_gens") or []
    if len(excl) >= 5:
        return "전 세대 보장 제외"
    if excl:
        return "일부 세대 보장 제외"
    if it.get("payment") == "관리급여":
        return "관리급여 95%"
    if it.get("excluded5"):
        return "5세대 보장 제외"
    return "비중증 보장"


def ds_item(code: str) -> dict | None:
    for it in (DATASET or {}).get("items", []):
        if it["code"] == code:
            return it
    return None


def kosis_card(it: dict) -> str:
    """KOSIS(승인번호 354006) 의원급 참고 카드 — 실제 수집한 통계표 값만 표시한다."""
    ds = ds_item(it["code"])
    kk = (ds or {}).get("kosis")
    if not kk:
        return ""
    table_nm = kk.get("table", "의원 비급여 진료비용")
    path = " › ".join(kk.get("path") or [])
    caveat = (f'<div class="notice amber" style="margin-top:10px">{esc(kk["caveat"])}</div>'
              if kk.get("caveat") else "")
    hosp_avg = (((ds or {}).get("stats") or {}).get("price") or {}).get("avg")
    diff = ""
    if hosp_avg and kk.get("avg"):
        gap = int(hosp_avg) - int(kk["avg"])
        pct = round(gap / int(kk["avg"]) * 100, 1) if kk["avg"] else 0
        diff = (f'<p class="calc-foot">같은 항목의 병원급 평균 {won(hosp_avg)} 대비 '
                f'{"+" if gap >= 0 else "−"}{abs(gap):,}원({abs(pct)}%) 차이입니다. '
                '병원급과 의원급은 모집단이 달라 단순 우열 비교로 쓸 수 없습니다.</p>')
    return f"""
<div class="card kosis" data-kosis>
  <h3>참고: 전국 의원급 평균·중간값 <span class="pill violet">통계청 KOSIS</span></h3>
  <div class="row-note" style="margin-bottom:10px">{esc(table_nm)} · {esc(path)}</div>
  <div class="kpi-row" style="grid-template-columns:repeat(2,1fr)">
    <div class="kpi"><div class="k">평균</div><div class="v">{won(kk.get('avg'))}</div></div>
    <div class="kpi"><div class="k">중간값</div><div class="v">{won(kk.get('median'))}</div></div>
    <div class="kpi"><div class="k">최저</div><div class="v" style="font-size:14px">{won(kk.get('min'))}</div></div>
    <div class="kpi"><div class="k">최고</div><div class="v" style="font-size:14px">{won(kk.get('max'))}</div></div>
  </div>
  {caveat}
  {diff}
  <p class="calc-foot">출처: <b>통계청 국가통계포털 KOSIS 승인번호 {esc(KOSIS_APPROVAL)}</b>(작성기관 건강보험심사평가원) ·
    {esc(table_nm)} · {esc(KOSIS_PERIOD)}. 로그인·API키 없이 공개된 통계표에서 직접 수집한 값입니다.<br>
    <b>동네 의원의 개별 가격은 공개 대상이 아니며</b>, 위 값은 전국 의원급 규모의 통계(최저·최고·평균·중간)입니다.
    방문할 의원의 실제 비용은 전화로 확인하세요.</p>
</div>
"""


def hospital_table(it: dict) -> str:
    """병원급 기관별 공개가 — 시도/종별 필터 + 검색(데이터는 /assets/hospitals.json)."""
    ds = ds_item(it["code"])
    if not ds or not ds.get("has_data"):
        return ""
    st = ds["stats"]
    sidos = sorted((st.get("by_sido") or {}).keys())
    cls = sorted((st.get("by_clcd") or {}).keys())
    sido_opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in sidos)
    cl_opts = "".join(f'<option value="{esc(c)}">{esc(c)}</option>' for c in cls)
    rows = "".join(
        f"<tr><td>{esc(h['name'])}</td><td>{esc(h['clCdNm'])}</td>"
        f"<td>{esc(h['sido'])} {esc(h['sggu'])}</td><td class=\"num\">{won(h['min'])}</td>"
        f"<td class=\"num\">{won(h['max'])}</td></tr>" for h in (st.get("hospitals") or [])[:12])
    return f"""
<div class="card" data-hosp data-code="{esc(it['code'])}">
  <h3>병원급 기관별 공개가 <span class="pill teal">전수 {st['n']:,}곳</span></h3>
  <div class="hosp-filters">
    <label class="sr-only" for="hosp-sido-{esc(it['slug'])}">시도</label>
    <select data-hosp-sido id="hosp-sido-{esc(it['slug'])}"><option value="">전체 시도</option>{sido_opts}</select>
    <label class="sr-only" for="hosp-cl-{esc(it['slug'])}">종별</label>
    <select data-hosp-cl id="hosp-cl-{esc(it['slug'])}"><option value="">전체 종별</option>{cl_opts}</select>
    <input type="search" data-hosp-q placeholder="병원명 검색" aria-label="병원명 검색">
  </div>
  <div class="table-wrap">
    <table class="plain hosp-table" style="font-size:12.5px">
      <thead><tr><th scope="col">기관</th><th scope="col">종별</th><th scope="col">지역</th>
        <th scope="col" class="num">최저</th><th scope="col" class="num">최고</th></tr></thead>
      <tbody data-hosp-body>{rows}</tbody>
    </table>
  </div>
  <p class="hosp-count" data-hosp-count>낮은 금액 순 상위 12곳을 먼저 보여 줍니다. 필터를 선택하면 전체 {st['n']:,}곳에서 다시 찾습니다.</p>
  <button type="button" class="btn ghost sm" data-hosp-more>더 보기 (50곳씩)</button>
  <p class="calc-foot">기관명·종별·지역·금액은 심평원 공개 원본 그대로이며 <b>추천·순위 매김·예약 알선이 아닙니다</b>(의료법 제27조).
    표시 금액은 기관이 신고한 비급여 최저·최고가로, 실제 청구액·할인·보험 적용은 방문 전 확인이 필요합니다.</p>
</div>
"""


# ------------------------------------------------------------------ 지역(17개 시·도)
# 심평원 오픈API 는 지역을 sidoCdNm 으로 주는데, 전남·광주는 '전남광주' 한 라벨로,
# 세종은 '세종시' 로 내려온다. 17개 시·도 화면을 만들기 위해
#   · 전남광주 → 시군구명이 '광주'로 시작하면 광주, 아니면 전남
#   · 세종시 → 세종
# 으로 나눈다. (기관 행의 시군구명은 원본 그대로이며 추정하지 않는다.)
REGIONS = [
    ("seoul", "서울", "서울특별시", ("서울",)),
    ("busan", "부산", "부산광역시", ("부산",)),
    ("daegu", "대구", "대구광역시", ("대구",)),
    ("incheon", "인천", "인천광역시", ("인천",)),
    ("gwangju", "광주", "광주광역시", ("전남광주",)),
    ("daejeon", "대전", "대전광역시", ("대전",)),
    ("ulsan", "울산", "울산광역시", ("울산",)),
    ("sejong", "세종", "세종특별자치시", ("세종시",)),
    ("gyeonggi", "경기", "경기도", ("경기",)),
    ("gangwon", "강원", "강원특별자치도", ("강원",)),
    ("chungbuk", "충북", "충청북도", ("충북",)),
    ("chungnam", "충남", "충청남도", ("충남",)),
    ("jeonbuk", "전북", "전북특별자치도", ("전북",)),
    ("jeonnam", "전남", "전라남도", ("전남광주",)),
    ("gyeongbuk", "경북", "경상북도", ("경북",)),
    ("gyeongnam", "경남", "경상남도", ("경남",)),
    ("jeju", "제주", "제주특별자치도", ("제주",)),
]
REGION_BY_SLUG = {r[0]: r for r in REGIONS}
SIDO_TO_REGION = {label: r[0] for r in REGIONS for label in r[3]}
REGION_CACHE: dict[str, dict] = {}
REP_CODES = ("HE1010001", "EB4410000", "MX1220000")   # 지역 요약 표의 대표 3개 항목


def region_match(slug: str, sido: str, sggu: str) -> bool:
    """기관 행 1건이 해당 시·도에 속하는지 판정한다."""
    if slug == "gwangju":
        return sido == "전남광주" and (sggu or "").startswith("광주")
    if slug == "jeonnam":
        return sido == "전남광주" and not (sggu or "").startswith("광주")
    return sido in REGION_BY_SLUG[slug][3]


def _agg_price(rows: list) -> dict:
    """기관별 (최저+최고)/2 의 평균·중간값 — hira_dataset 과 같은 산식."""
    vals = [(int(r[4] or 0) + int(r[5] or 0)) // 2 for r in rows]
    return {"n": len(rows), "avg": round(sum(vals) / len(vals)),
            "median": int(statistics.median(vals)),
            "min": min(int(r[4] or 0) for r in rows),
            "max": max(int(r[5] or 0) for r in rows)}


def region_data(slug: str) -> dict:
    """지역 1곳의 항목·종별·시군구 집계(병원급 기관 행 기준)."""
    if slug in REGION_CACHE:
        return REGION_CACHE[slug]
    hs = (HOSPITALS or {}).get("items") or {}
    per_item: dict[str, dict] = {}
    hosp: dict[tuple, int] = {}
    by_clcd: dict[str, set] = {}
    by_sggu: dict[str, dict] = {}
    rows_total = 0
    for code, rows in hs.items():
        sel = [r for r in rows if region_match(slug, r[2], r[3])]
        if not sel:
            continue
        rows_total += len(sel)
        per_item[code] = _agg_price(sel)
        for r in sel:
            key = (r[0], r[3], r[1])
            hosp[key] = 1
            by_clcd.setdefault(r[1], set()).add(key)
            sg = by_sggu.setdefault(r[3] or "—", {"hosp": set(), "vals": {}})
            sg["hosp"].add(key)
            sg["vals"].setdefault(code, []).append((int(r[4] or 0) + int(r[5] or 0)) // 2)
    out = {"slug": slug, "per_item": per_item, "hospitals": len(hosp), "rows": rows_total,
           "by_clcd": {k: len(v) for k, v in by_clcd.items()}, "by_sggu": by_sggu}
    REGION_CACHE[slug] = out
    return out


def national_avg(code: str) -> int | None:
    ds = ds_item(code) or {}
    price = ((ds.get("stats") or {}).get("price") or {})
    return price.get("avg")


def region_chips(current: str = "") -> str:
    """17개 시·도 바로가기 칩."""
    out = []
    for slug, name, _full, _labels in REGIONS:
        cls = "pill teal" if slug == current else "pill line"
        attr = ' aria-current="page"' if slug == current else ""
        out.append(f'<a class="{cls}" style="text-decoration:none" href="/ko/regions/{slug}/"{attr}>{esc(name)}</a>')
    return '<div style="display:flex;flex-wrap:wrap;gap:6px">' + "".join(out) + "</div>"


def sido_cell(label: str) -> str:
    """시도명 표기 — 가능한 경우 해당 지역 페이지로 링크한다."""
    if label == "전남광주":
        return ('<a href="/ko/regions/jeonnam/">전남</a> · '
                '<a href="/ko/regions/gwangju/">광주</a>')
    slug = SIDO_TO_REGION.get(label)
    if slug:
        return f'<a href="/ko/regions/{slug}/">{esc(label)}</a>'
    return esc(label)


def region_hosp_card(slug: str, items: list[dict]) -> str:
    """지역 페이지용 기관·항목별 공개가 검색 카드(항목·시군구·병원명 필터)."""
    name = REGION_BY_SLUG[slug][1]
    if slug in ("gwangju", "jeonnam"):
        sido_label = "전남광주"
    else:
        sido_label = REGION_BY_SLUG[slug][3][0]
    prefix_attr = ' data-region-sggu-prefix="광주"' if slug == "gwangju" else ""
    noprefix_attr = ' data-region-sggu-not-prefix="광주"' if slug == "jeonnam" else ""
    opts = "".join(f'<option value="{esc(it["code"])}">{esc(it["name"])}</option>' for it in items)
    return f"""
<div class="card" data-hosp data-region="{esc(sido_label)}"{prefix_attr}{noprefix_attr}>
  <h3>{esc(name)} 병원급 기관별 공개가 찾기</h3>
  <p class="row-note" style="margin-bottom:10px">항목·시·군·구를 고르면 이 지역 병원급 기관의 신고 최저·최고가를 낮은 금액 순으로 보여 줍니다.
    (동네 의원은 공개 범위 밖입니다.)</p>
  <div class="hosp-filters">
    <label class="sr-only" for="reg-item-{esc(slug)}">비급여 항목</label>
    <select data-hosp-item id="reg-item-{esc(slug)}">{opts}</select>
    <label class="sr-only" for="reg-sggu-{esc(slug)}">시·군·구</label>
    <select data-hosp-sggu id="reg-sggu-{esc(slug)}"><option value="">전체 시·군·구</option></select>
    <input type="search" data-hosp-q placeholder="병원명 검색" aria-label="병원명 검색">
  </div>
  <div class="table-wrap">
    <table class="plain hosp-table" style="font-size:12.5px">
      <thead><tr><th scope="col">기관</th><th scope="col">종별</th><th scope="col">시·군·구</th>
        <th scope="col" class="num">최저</th><th scope="col" class="num">최고</th></tr></thead>
      <tbody data-hosp-body></tbody>
    </table>
  </div>
  <p class="hosp-count" data-hosp-count>기관 목록을 불러오는 중…</p>
  <button type="button" class="btn ghost sm" data-hosp-more>더 보기 (50곳씩)</button>
  <p class="calc-foot">기관명·종별·시·군·구·금액은 심평원 공개 원본 그대로이며 <b>추천·순위 매김·예약 알선이 아닙니다</b>(의료법 제27조).
    표시 금액은 기관이 신고한 비급여 최저·최고가로 실제 청구액·할인·보험 적용은 다를 수 있습니다.</p>
</div>
"""


def page_regions(items: list[dict]) -> str:
    """17개 시·도 허브 — 지역별 기관 수와 대표 항목 시세를 카드 그리드로."""
    cards = []
    total_hosp = 0
    total_rows = 0
    for slug, name, full, _labels in REGIONS:
        d = region_data(slug)
        total_hosp += d["hospitals"]
        total_rows += d["rows"]
        prices = []
        for code in REP_CODES:
            st = d["per_item"].get(code)
            if st:
                label = next((i["name"] for i in items if i["code"] == code), code)
                prices.append(f"{esc(label)} 중간값 {won(st['median'])}")
        price_line = (f'<span class="rc-price">{" · ".join(prices)}</span>'
                      if prices else "")
        cards.append(
            f'<a class="region-card" href="/ko/regions/{slug}/">'
            f'<span class="rc-head"><span class="rc-name">{esc(name)}</span>'
            f'<span class="rc-full">{esc(full)}</span>'
            f'<span class="rc-arrow" aria-hidden="true">›</span></span>'
            f'<span class="rc-meta">공개 기관 {d["hospitals"]:,}곳 · 항목 응답 {d["rows"]:,}건</span>'
            f'{price_line}</a>')
    faqs = [
        ("지역별로 비급여 가격이 다른가요?",
         "같은 항목이라도 지역·기관 규모·장비에 따라 신고 가격이 다릅니다. 이 사이트는 심평원이 공개한 "
         "병원급 이상 기관의 신고 최저·최고가를 지역별로 집계해 중간값과 평균을 보여 줍니다. "
         "지역별 기관 수(표본)가 다르므로 순위가 곧 지역의 우열은 아닙니다."),
        ("우리 동네 의원 가격도 지역별로 볼 수 있나요?",
         "없습니다. 공개 오픈API는 병원급 이상만 제공합니다. 의원·치과의원·한의원의 개별 가격은 공개 범위 밖이며, "
         "전국 의원급 규모의 통계(통계청 KOSIS 승인번호 354006)만 항목 페이지에서 참고값으로 안내합니다. "
         "방문 전 유선 확인이 필요합니다."),
        ("시·도 페이지의 금액은 어떤 기준인가요?",
         "각 기관이 신고한 비급여 최저가와 최고가의 중간값을 기관별로 구한 뒤, 그 값의 평균·중간값을 계산합니다. "
         "항목마다 공개에 응답한 기관 수가 달라 모든 지역에 같은 항목이 있는 것은 아닙니다."),
        ("실손 보장액도 지역에 따라 달라지나요?",
         "아닙니다. 실손보험 보장액은 가입 세대·입원/통원·기관 종별·중증(산정특례) 여부로 결정되며 지역과는 관계가 없습니다. "
         "지역별 가격 차이는 환자가 부담하는 진료비 쪽에서 생깁니다."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>지역별 비급여 시세 — 17개 시·도</h1>
      <p class="section-lead">서울부터 제주까지, 시·도마다 병원급 이상 기관이 신고한 비급여 공개가를 항목별로 모았습니다.
        지역을 누르면 그 지역의 항목별 평균·중간값·최저~최고와 시·군·구별 시세를 볼 수 있습니다.</p>
      <div class="meta">
        <span class="pill teal">17개 시·도</span>
        <span class="pill blue">병원급 기관 {total_hosp:,}곳(중복 제거)</span>
        <span class="pill line">항목·기관 응답 {total_rows:,}건</span>
      </div>
    </div>
    <div class="region-grid">
      {''.join(cards)}
    </div>
    <p class="calc-foot">기관 수는 같은 병원이 여러 항목에 응답한 경우 1곳으로 셉니다. 금액은 병원급 이상 공개가(기관별 최저·최고의 중간값)의 지역 중간값이며,
      도수치료는 2026-07-01 관리급여 전환 전 공개자료 기준입니다. {esc(DATA_PERIOD)}</p>
    <div class="card" style="margin-top:14px">
      <h3>바로 가기</h3>
      {region_chips()}
      <p class="calc-foot">시·도 단위 외에 지역 페이지 안에서 시·군·구 필터와 항목별 공개가 검색을 쓸 수 있습니다.
        동네 의원 가격은 공개 범위 밖이므로 방문 전 유선 확인이 필요합니다.</p>
    </div>
    <div class="card prose" style="margin-top:14px">
      <h2 style="font-size:17px">자주 묻는 질문</h2>
      {faq_html(faqs)}
    </div>
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/regions/", "지역별 시세")]),
        faq_jsonld(faqs),
        {"@context": "https://schema.org", "@type": "ItemList", "name": "17개 시·도 비급여 시세",
         "numberOfItems": len(REGIONS),
         "itemListElement": [{"@type": "ListItem", "position": i, "name": f"{r[1]} 비급여 시세",
                               "url": SITE_BASE + f"/ko/regions/{r[0]}/"}
                              for i, r in enumerate(REGIONS, start=1)]},
    ]
    return layout("/ko/regions/", f"지역별 비급여 시세 17개 시·도 · {SITE_NAME}",
                  "서울·경기·인천·부산 등 17개 시·도의 병원급 이상 비급여 공개가를 항목별로 비교합니다. 지역별 평균·중간값과 시·군·구 시세, 실손 보장 계산 안내.",
                  body, [("/ko/", "홈"), ("/ko/regions/", "지역별 시세")], jsonld, current="/ko/regions/")


def page_region(slug: str, items: list[dict]) -> str:
    """시·도 1곳 — 항목별 시세·종별 분포·시군구 시세·기관 검색."""
    _slug, name, full, _labels = REGION_BY_SLUG[slug]
    d = region_data(slug)
    if not d["per_item"]:
        # 데이터가 없는 지역도 페이지는 만든다(정직한 상태 안내).
        pass
    rows = []
    higher = lower = 0
    for it in items:
        st = d["per_item"].get(it["code"])
        na = national_avg(it["code"])
        if not st:
            rows.append(f'<tr><th scope="row"><a href="/ko/items/{esc(it["slug"])}/">{esc(it["name"])}</a></th>'
                        '<td class="num" data-label="기관">—</td><td class="num" data-label="평균">—</td>'
                        '<td class="num" data-label="중간값">—</td><td class="num" data-label="최저~최고">—</td>'
                        '<td class="num" data-label="전국 대비">공개 없음</td></tr>')
            continue
        diff_cell = '—'
        if na:
            pct = (st["avg"] - na) / na * 100
            up = pct >= 0
            higher += 1 if up else 0
            lower += 0 if up else 1
            diff_cell = (f'<span class="{"pct-up" if up else "pct-dn"}">'
                         f'{"+" if up else "−"}{abs(pct):.1f}%</span>')
        rows.append(
            f'<tr><th scope="row"><a href="/ko/items/{esc(it["slug"])}/">{esc(it["name"])}</a>'
            f'{(" <span class=\"pill blue\">관리급여</span>" if it["payment"] == "관리급여" else "")}</th>'
            f'<td class="num" data-label="기관">{st["n"]:,}곳</td>'
            f'<td class="num" data-label="평균">{won(st["avg"])}</td>'
            f'<td class="num" data-label="중간값">{won(st["median"])}</td>'
            f'<td class="num" data-label="최저~최고" style="font-size:11.5px">{won(st["min"])} ~ {won(st["max"])}</td>'
            f'<td class="num" data-label="전국 대비">{diff_cell}</td></tr>')

    # 종별 분포
    cl_order = ["상급종합", "종합병원", "병원", "요양병원", "정신병원", "치과병원", "한방병원"]
    cl_rows = "".join(
        f'<tr><th scope="row">{esc(cl)}</th><td class="num">{d["by_clcd"][cl]:,}곳</td>'
        f'<td class="num">{d["by_clcd"][cl] / max(d["hospitals"], 1) * 100:.1f}%</td></tr>'
        for cl in cl_order if cl in d["by_clcd"])

    # 시·군·구 요약(대표 3개 항목의 중간값)
    sg_rows = []
    rep_labels = [next((i["name"] for i in items if i["code"] == c), c) for c in REP_CODES]
    for sg, info in d["by_sggu"].items():
        cells = []
        nvals = 0
        for code in REP_CODES:
            vals = info["vals"].get(code)
            nvals += len(vals) if vals else 0
            if vals and len(vals) >= 3:
                cells.append(f'<td class="num">{won(int(statistics.median(vals)))}</td>')
            elif vals:
                cells.append(f'<td class="num muted">{won(int(statistics.median(vals)))}¹</td>')
            else:
                cells.append('<td class="num">—</td>')
        sg_rows.append((len(info["hosp"]), nvals, sg, cells))
    sg_rows.sort(key=lambda x: (-x[0], x[2]))
    sg_html = "".join(
        f'<tr><th scope="row">{esc(sg)}</th><td class="num" data-label="공개 기관">{nh:,}곳</td>'
        f'<td class="num" data-label="항목 응답">{nv:,}건</td>'
        + "".join(c.replace('<td class="num">', f'<td class="num" data-label="{esc(label)}">')
                  .replace('<td class="num muted">', f'<td class="num muted" data-label="{esc(label)}">')
                  for c, label in zip(cells, rep_labels))
        + "</tr>"
        for nh, nv, sg, cells in sg_rows)

    top_item = max(d["per_item"].items(), key=lambda kv: kv[1]["n"])
    top_name = next((i["name"] for i in items if i["code"] == top_item[0]), top_item[0])
    rank = sorted(items, key=lambda it: -(d["per_item"].get(it["code"], {}).get("n") or 0))[:6]
    top_cards = "".join(
        f'<a class="item-card" href="/ko/items/{esc(it["slug"])}/"><div class="top">'
        f'<span class="nm">{esc(it["name"])}</span></div>'
        f'<div class="cd">이 지역 {d["per_item"].get(it["code"], {}).get("n", 0):,}곳 공개</div>'
        f'<div class="sm">{esc(it["summary"])}</div></a>' for it in rank)
    n_sang = d["by_clcd"].get("상급종합", 0)
    merged_note = ""
    if slug in ("gwangju", "jeonnam"):
        merged_note = (
            '<div class="notice" role="note" style="margin-bottom:14px">심평원 오픈API는 전남·광주를 <b>‘전남광주’</b> 한 라벨로 제공합니다. '
            '이 페이지는 기관의 시·군·구명이 <b>‘광주’로 시작하면 광주광역시</b>, 그 외는 전라남도로 나누어 집계했습니다. '
            '원본 표기는 <a href="/ko/guide/">이용 안내</a>에서 확인할 수 있습니다.</div>')

    faqs = [
        (f"{name} 병원급 비급여 시세는 어떤 기준인가요?",
         f"건강보험심사평가원이 공개한 병원급 이상(상급종합·종합병원·병원·요양병원·정신병원·치과병원·한방병원) 기관의 "
         f"비급여 신고 최저·최고가를 {name} 기준으로 모아, 기관별 중간값의 평균·중간값을 계산한 값입니다. "
         f"{name}에서 공개에 응답한 기관은 {d['hospitals']:,}곳, 항목·기관 응답은 {d['rows']:,}건입니다."),
        (f"{name}은 전국 평균보다 비싼 편인가요?",
         f"항목별로 다릅니다. 이 페이지의 ‘전국 대비’ 열에서 항목마다 전국 병원급 평균과 비교한 차이를 볼 수 있습니다. "
         f"이 지역에서 공개된 {len(items)}개 항목 가운데 전국 평균보다 높은 항목이 {higher}개, 낮은 항목이 {lower}개입니다. "
         "다만 지역마다 응답 기관 수와 종별 구성(상급종합 비중)이 달라 단순 비교로 우열을 판단할 수는 없습니다."),
        (f"{name}에서 의원·치과의원 가격도 알 수 있나요?",
         "공개 오픈API는 병원급 이상만 제공해 동네 의원의 개별 가격은 표시할 수 없습니다. "
         "대신 전국 의원급 규모의 평균·중간값(통계청 KOSIS 승인번호 354006)을 항목 페이지에서 참고값으로 보여 줍니다. "
         "방문할 의원의 실제 비용은 전화로 확인하세요."),
        ("같은 지역 안에서도 가격이 크게 다른 이유는?",
         "상급종합·종합병원은 장비(3.0T MRI 등)·판독 인력·시설 수준이 달라 비급여 신고가가 높게 형성되는 경우가 많습니다. "
         "또 기관마다 치료재료·조영제·판독료 포함 여부가 달라 같은 항목명이라도 조건이 다를 수 있으니 유선 확인이 필요합니다."),
        ("실손보험으로 돌려받는 금액은 지역과 관계가 있나요?",
         "없습니다. 보장액은 가입 세대(1~5세대)·입원/통원·기관 종별·중증(산정특례) 여부로 결정됩니다. "
         "지역 차이는 병원이 신고한 진료비 쪽에서 발생하며, 계산기에서 금액을 넣어 세대별 보장액을 비교할 수 있습니다."),
    ]

    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>{esc(name)} 비급여 진료비 시세 — MRI·초음파·도수치료 병원급 공개가</h1>
      <p class="section-lead">{esc(full)} 병원급 이상 기관의 비급여 공개가를 항목별로 모았습니다.
        기관별 최저·최고가의 중간값을 기준으로 평균·중간값·최저~최고와 전국 평균 대비 차이를 보여 줍니다.</p>
      <div class="meta">
        <span class="pill line">병원급 이상 {d['hospitals']:,}곳</span>
        <span class="pill teal">항목 {len(items)}개</span>
        <span class="pill blue">항목·기관 응답 {d['rows']:,}건</span>
        {'<span class="pill amber">상급종합 ' + str(n_sang) + '곳</span>' if n_sang else ''}
      </div>
    </div>
    {merged_note}
    <div class="kpi-row">
      <div class="kpi"><div class="k">공개 기관(중복 제거)</div><div class="v">{d['hospitals']:,}곳</div></div>
      <div class="kpi"><div class="k">가장 많이 응답한 항목</div><div class="v" style="font-size:13.5px">{esc(top_name)}<br><span class="muted">{top_item[1]['n']:,}곳</span></div></div>
      <div class="kpi"><div class="k">상급종합 · 종합병원</div><div class="v" style="font-size:13.5px">상급 {d['by_clcd'].get('상급종합', 0)}곳<br><span class="muted">종합 {d['by_clcd'].get('종합병원', 0)}곳</span></div></div>
      <div class="kpi"><div class="k">데이터 기준</div><div class="v" style="font-size:12.5px">2026년 심평원 공개자료</div></div>
    </div>

    <div class="card">
      <h2 style="font-size:18px">항목별 시세 (병원급 이상)</h2>
      <div class="table-wrap">
        <table class="plain stack" style="font-size:12.5px">
          <thead><tr><th scope="col">항목</th><th scope="col">기관</th><th scope="col">평균</th>
            <th scope="col">중간값</th><th scope="col">최저 ~ 최고</th><th scope="col">전국 대비</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <p class="calc-foot">병원급 이상 공개가 기준 · {esc(DATA_PERIOD)}. ‘전국 대비’는 전국 병원급 평균과의 차이이며 기관 구성이 달라 우열 비교가 아닙니다.
        의원급 개별 가격은 공개 범위 외이므로 방문 전 유선 확인이 필요합니다. 항목 이름을 누르면 기관별 공개가·실손 처리 설명으로 이동합니다.</p>
    </div>

    <div class="grid g2" style="margin-top:14px">
      <div class="card">
        <h3>종별 분포</h3>
        <div class="table-wrap">
          <table class="plain" style="font-size:12.5px">
            <thead><tr><th scope="col">종별</th><th scope="col" class="num">기관</th><th scope="col" class="num">비중</th></tr></thead>
            <tbody>{cl_rows or '<tr><td colspan="3">공개된 기관이 없습니다.</td></tr>'}</tbody>
          </table>
        </div>
        <p class="calc-foot">같은 기관이 여러 항목에 응답해도 1곳으로 셉니다.</p>
      </div>
      <div class="card prose">
        <h3>이 표를 읽는 법</h3>
        <ul style="font-size:13px;padding-left:18px">
          <li><b>평균·중간값</b> — 기관별 (최저+최고)/2 를 구한 뒤 지역 전체로 평균·중간값을 낸 값입니다.</li>
          <li><b>최저~최고</b> — 그 지역에서 공개된 가장 싼 신고가와 가장 비싼 신고가입니다.</li>
          <li><b>전국 대비</b> — 전국 병원급 평균과 비교한 차이입니다. 기관 구성이 달라 우열 비교는 아닙니다.</li>
          <li><b>의원·치과의원</b> — 공개 범위 밖이라 표에 없습니다. 방문 전 유선 확인이 필요합니다.</li>
        </ul>
        <a class="btn ghost sm" href="/ko/calc/">내 실손 보장액 계산하기</a>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3>시·군·구별 시세</h3>
      <div class="table-wrap">
        <table class="plain stack" style="font-size:12.5px">
          <thead><tr><th scope="col">시·군·구</th><th scope="col">공개 기관</th><th scope="col">항목 응답</th>
            <th scope="col">뇌 MRI</th><th scope="col">복부 초음파</th><th scope="col">도수치료</th></tr></thead>
          <tbody>{sg_html or '<tr><td colspan="6">공개된 기관이 없습니다.</td></tr>'}</tbody>
        </table>
      </div>
      <p class="calc-foot">금액은 해당 시·군·구 기관의 중간값입니다. ¹ 표시는 응답 기관이 3곳 미만인 값으로, 참고만 하세요.
        기관명에 구가 붙은 경우(예: 수원팔달구)는 심평원 공개 원본의 시·군·구 표기 그대로입니다.</p>
    </div>

    <div style="margin-top:14px">{region_hosp_card(slug, items)}</div>

    <div class="card prose" style="margin-top:14px">
      <h2 style="font-size:17px">자주 묻는 질문</h2>
      {faq_html(faqs)}
    </div>

    <div class="card" style="margin-top:14px">
      <h3>다른 지역 시세</h3>
      {region_chips(slug)}
      <p class="calc-foot"><a href="/ko/regions/">17개 시·도 전체 표로 보기</a> · <a href="/ko/calc/">실손 보장액 계산하기</a></p>
    </div>

    <div class="card" style="margin-top:14px">
      <h3>이 지역에서 많이 보는 항목</h3>
      <div class="grid" style="gap:8px">{top_cards}</div>
    </div>
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/regions/", "지역별 시세"), (f"/ko/regions/{slug}/", f"{name} 비급여 시세")]),
        faq_jsonld(faqs),
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"{name} 비급여 항목 시세",
         "numberOfItems": len(items),
         "itemListElement": [{"@type": "ListItem", "position": i, "name": it["name"],
                               "url": SITE_BASE + f"/ko/items/{it['slug']}/"}
                              for i, it in enumerate(items, start=1)]},
    ]
    desc = (f"{name} 병원급 {d['hospitals']:,}곳의 비급여 시세. 뇌 MRI·초음파·도수치료 등 {len(items)}개 항목의 평균·중간값·최저~최고와 "
            f"시·군·구별 가격, 전국 평균 대비 차이를 정리했습니다.")
    return layout(f"/ko/regions/{slug}/", f"{name} 비급여 시세 — MRI·초음파·도수치료 병원급 공개가 · {SITE_NAME}",
                  desc, body,
                  [("/ko/", "홈"), ("/ko/regions/", "지역별 시세"), (f"/ko/regions/{slug}/", f"{name}")],
                  jsonld, current="/ko/regions/")


def price_block(item: dict) -> str:
    """수집된 실제 가격이 있으면 시세 표를, 없으면 정직한 상태 안내를 그린다."""
    ds = ds_item(item["code"])
    if ds and ds.get("has_data") and ds.get("stats"):
        st = ds["stats"]
        p = st["price"]
        cl = "".join(
            f"<tr><th scope=\"row\">{esc(k)}</th><td class=\"num\">{v['n']}</td>"
            f"<td class=\"num\">{won(v['avg'])}</td><td class=\"num\">{won(v['median'])}</td>"
            f"<td class=\"num\">{won(v['min'])} ~ {won(v['max'])}</td></tr>"
            for k, v in (st.get("by_clcd") or {}).items())
        sd_rows = "".join(
            f"<tr><th scope=\"row\">{sido_cell(k)}</th><td class=\"num\">{v['n']}</td>"
            f"<td class=\"num\">{won(v['avg'])}</td><td class=\"num\">{won(v['median'])}</td></tr>"
            for k, v in sorted((st.get("by_sido") or {}).items(), key=lambda kv: -kv[1]["n"])[:9])
        if st.get("by_sido"):
            sd_rows += ('<tr><td colspan="4" style="font-size:12px">'
                        '<a href="/ko/regions/">17개 시·도 항목별 시세 전체 보기</a></td></tr>')
        cov = ds.get("coverage") or {}
        complete = cov.get("complete")
        cov_html = (
            f'<div class="data-coverage"><span class="pill teal">전수 수집</span> '
            f'{cov["collected"]:,}/{cov["total"]:,}곳 응답(100%) · {esc(DATA_PERIOD)}</div>'
            if complete else
            f'<div class="data-coverage"><span class="pill amber">부분 수집</span> '
            f'{cov.get("collected", 0):,}/{cov.get("total") or 0:,}곳 응답 기준이며 전체 수집 후 시세가 달라질 수 있습니다.</div>')
        mat = ds.get("material") or {}
        mat_html = (f'<div class="notice" style="margin-top:10px">{esc(mat.get("note") or "")}</div>'
                    if mat.get("note") else "")
        return f"""
<div class="card">
  <h3>심평원 병원급 공개가 시세</h3>
  {cov_html}
  <div class="kpi-row" style="grid-template-columns:repeat(2,1fr)">
    <div class="kpi"><div class="k">기관 수</div><div class="v">{st['n']:,}곳</div></div>
    <div class="kpi"><div class="k">평균</div><div class="v">{won(p['avg'])}</div></div>
    <div class="kpi"><div class="k">최저 / 최고</div><div class="v" style="font-size:13.5px">{won(p['min'])} / {won(p['max'])}</div></div>
    <div class="kpi"><div class="k">중간 / 최빈</div><div class="v" style="font-size:13.5px">{won(p['median'])} / {won(p['mode'] or 0)}</div></div>
  </div>
  <div class="table-wrap">
    <table class="plain" style="font-size:12.5px">
      <thead><tr><th scope="col">종별</th><th scope="col" class="num">기관</th><th scope="col" class="num">평균</th>
        <th scope="col" class="num">중간</th><th scope="col" class="num">최저~최고</th></tr></thead>
      <tbody>{cl}</tbody>
    </table>
  </div>
  <details class="rule" style="margin-top:8px">
    <summary>시도별 요약 보기</summary>
    <div class="table-wrap">
      <table class="plain" style="font-size:12.5px">
        <thead><tr><th scope="col">시도</th><th scope="col" class="num">기관</th><th scope="col" class="num">평균</th><th scope="col" class="num">중간</th></tr></thead>
        <tbody>{sd_rows}</tbody>
      </table>
    </div>
    <p class="calc-foot">시도는 기관 응답의 시도명을 그대로 집계했습니다(전남광주 통합 표기).</p>
  </details>
  {mat_html}
  <p class="calc-foot">기준: 병원급 이상 공개 자료 · 산출 {p['basis']}</p>
</div>
"""

    fix = ""
    if ds and ds.get("raw_stats_preview"):
        n = ds["raw_stats_preview"].get("n", 0)
        fix = (f'<br><span style="color:var(--amber)"><b>파이프라인 검증용 픽스처</b>: {n}개 기관 행이 정상 정제되었으나 '
               '실제 공개가가 아니므로 화면에는 표시하지 않습니다.</span>')
    if not_listed(item):
        price_row = ('<b>심평원 공개 가격</b> — 심평원 비급여 진료비 공개 목록(15001700)에 수록되지 않은 항목이라 '
                     '공개 가격이 없습니다. 금액을 지어내 표시하지 않으며, 실제 비용은 기관마다 달라 방문 전 확인이 필요합니다.')
        code_row = (f'<b>항목 코드</b> — 없음 (2026-11-20 심평원 API 전수 대조로 미수록 확정). '
                    f'카탈로그 코드 <code>{esc(item["code"])}</code>는 이 사이트 내부 구분용이며 심평원 코드가 아닙니다.')
    else:
        price_row = ('<b>심평원 공개 가격</b> — 이 항목의 실수집 데이터가 없어 금액을 표시하지 않습니다. '
                     '수집 파이프라인(<code>scripts/fetch_hira.py</code> → <code>scripts/prepare_data.py</code>)을 실행하면 '
                     f'기관별 최저·최고·평균·중간 금액이 이 자리에 채워집니다.{fix}')
        if item.get("codes"):
            code_row = (f'<b>항목 코드</b> — <code>{esc(item["code"])}</code> (대표) 외 {len(item["codes"]) - 1}개<br>'
                        f'{codes_inline(item)}<br>'
                        f'({esc(item["official_mid"])} &gt; {esc(item["official_sub"])}'
                        f'{("&gt; " + esc(item["official_dtl"])) if item["official_dtl"] else ""})')
        else:
            code_row = (f'<b>항목 코드</b> — <code>{esc(item["code"])}</code> '
                        f'({esc(item["official_mid"])} &gt; {esc(item["official_sub"])}'
                        f'{("&gt; " + esc(item["official_dtl"])) if item["official_dtl"] else ""})')
    return f"""
<div class="card">
  <h3>가격 데이터 상태</h3>
  <div class="data-status">
    <div class="row"><span class="dot off"></span><div>
      {price_row}
    </div></div>
    <div class="row"><span class="dot on"></span><div>{code_row}</div></div>
    <div class="row"><span class="dot on"></span><div><b>공개 범위</b> — 병원급 이상(상급종합·종합병원·병원·요양병원·정신병원·치과병원·한방병원).
      {esc('치과병원만 공개 대상' if item['code'].startswith('UB') else '의원은 공개 범위 밖')}.</div></div>
  </div>
</div>
"""


def _unused_data_status(item: dict) -> str:
    return f"""
<div class="card">
  <h3>가격 데이터 상태</h3>
  <div class="data-status">
    <div class="row"><span class="dot off"></span><div>
      <b>심평원 공개 가격</b> — {'수집 데이터 표시 중' if live else
      'data.go.kr 인증키 발급 전이라 금액을 표시하지 않습니다.'}
      키를 넣고 <code>scripts/fetch_hira.py</code> → <code>scripts/prepare_data.py</code>를 실행하면
      기관별 최저·최고·평균·중간 금액이 이 자리에 채워집니다.
    </div></div>
    <div class="row"><span class="dot on"></span><div><b>항목 코드</b> — <code>{esc(item['code'])}</code>
      ({esc(item['official_mid'])} &gt; {esc(item['official_sub'])}
      {('&gt; ' + esc(item['official_dtl'])) if item['official_dtl'] else ''})</div></div>
    <div class="row"><span class="dot on"></span><div><b>공개 범위</b> — 병원급 이상(상급종합·종합병원·병원·요양병원·치과병원·한방병원).
      {esc('치과의원은 범위 밖' if item['code'].startswith('UB') else '의원은 범위 밖')}.</div></div>
  </div>
</div>
"""


# ------------------------------------------------------------------ 페이지
def compare_table_html(items: list[dict]) -> str:
    """홈 비교표 — 병원급 실수집 평균과 KOSIS 의원급 통계를 나란히 보여 준다."""
    rows = []
    for it in items:
        ds = ds_item(it["code"]) or {}
        st = ds.get("stats") or {}
        price = st.get("price") or {}
        kk = ds.get("kosis") or {}
        h_avg = won(price.get("avg")) if price else "—"
        h_n = f"{st.get('n'):,}곳" if st.get("n") else "—"
        c_avg = won(kk.get("avg")) if kk else "—"
        c_mid = won(kk.get("median")) if kk else "—"
        rows.append(
            f"<tr><th scope=\"row\"><a href=\"/ko/items/{esc(it['slug'])}/\">{esc(it['name'])}</a></th>"
            f"<td class=\"num\">{h_avg}<br><span class=\"muted\">{h_n}</span></td>"
            f"<td class=\"num\">{c_avg}<br><span class=\"muted\">중간 {c_mid}</span></td>"
            f"<td data-label=\"비고\">{'관리급여 95% 전환' if it['payment'] == '관리급여' else ('전 세대 보장 제외' if len(it.get('excluded_gens') or []) >= 5 else ('일부 세대 보장 제외' if it.get('excluded_gens') else ('5세대 제외' if it['excluded5'] else '비중증 보장')))}</td></tr>")
    return f"""
<div class="table-wrap">
  <table class="plain stack" data-compare-table>
    <thead><tr><th scope="col">항목</th><th scope="col">병원급 평균(기관)</th>
      <th scope="col">전국 의원급 평균(중간값)</th><th scope="col">5세대 처리</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def page_landing(items: list[dict]) -> str:
    cards = "".join(f"""
      <a class="item-card" href="/ko/items/{esc(it['slug'])}/">
        <div class="top"><span class="nm">{esc(it['name'])}</span>
          {'<span class="pill red">전 세대 제외</span>' if len(it.get('excluded_gens') or []) >= 5
           else ('<span class="pill amber">일부 세대 제외</span>' if it.get('excluded_gens')
           else ('<span class="pill red">5세대 제외</span>' if it['excluded5'] and it['payment'] == '비급여'
                 else ('<span class="pill blue">관리급여 95%</span>' if it['payment'] == '관리급여'
                       else ('<span class="pill violet">3세대 특약</span>' if it['special3'] else ''))))}</div>
        <div class="cd">{esc(code_disp(it))}</div>
        <div class="sm">{esc(it['summary'])}</div>
      </a>""" for it in items)

    faqs = [
        ("비급여 가격은 어디까지 비교할 수 있나요?",
         "건강보험심사평가원이 공공데이터포털로 공개하는 병원급 이상(상급종합·종합병원·병원·요양병원·치과병원·한방병원) "
         "비급여 진료비입니다. 동네 의원·치과의원·한의원 가격은 공개 API 제공 범위가 아니어서 표시하지 않습니다."),
        ("5세대 실손은 언제부터 가입할 수 있나요?",
         "2026년 5월 6일부터 판매가 시작되었습니다. 중증 비급여(특약1)와 비중증 비급여(특약2)로 나뉘고, "
         "근골격계 물리치료·체외충격파·비급여 주사제 등은 특약2 보장 대상에서 제외됩니다."),
        ("도수치료는 이제 비급여가 아닌가요?",
         "2026년 7월 1일부터 관리급여(선별급여)로 전환되어 1회 43,850원(종별 동일), 본인부담률 95%가 적용됩니다. "
         "비급여 특약이 아니라 급여로 계산해야 합니다."),
        ("계산 결과와 실제 보험금이 다른 이유는?",
         "가입 시기·상품(표준형/선택형)·약관의 연간 한도·자기부담금 누적·청구 이력에 따라 달라집니다. "
         "이 계산기는 공개된 제도 기준의 추정치를 보여줍니다."),
    ]

    body = f"""
<section class="hero">
  <div class="wrap">
    <h1>비급여 진료비, <em>내 실손보험으로</em><br>얼마나 돌려받을까?</h1>
    <p class="lede">병원급 이상 심평원 공개가와 1~5세대 실손 보장액을 한 화면에서 비교합니다.
      2026년 5월 출시된 <b>5세대 실손</b>과 2026년 7월 <b>도수치료 관리급여 전환</b>까지 반영했습니다.</p>
    <div class="pills">
      <span class="pill teal">병원급 이상 공개가</span>
      <span class="pill blue">1~5세대 동시 비교</span>
      <span class="pill violet">5세대 특약1·2 반영</span>
      <span class="pill amber">도수치료 관리급여 95%</span>
    </div>
    <div class="kpi-row">
      <div class="kpi"><div class="k">핵심 항목</div><div class="v">{len(items)}개</div></div>
      <div class="kpi"><div class="k">실손 세대</div><div class="v">1~5세대</div></div>
      <div class="kpi"><div class="k">공개 대상</div><div class="v">병원급 이상</div></div>
      <div class="kpi"><div class="k">라이선스</div><div class="v">공공누리 1유형</div></div>
    </div>
    <div class="cta-row">
      <a class="btn" href="#calc">바로 계산하기</a>
      <a class="btn ghost" href="/ko/insurance/">세대별 보장 비교표</a>
    </div>
  </div>
</section>

<section class="section" id="calc">
  <div class="wrap">
    <div class="grid g2">
      <div>{calc_block(items, 'HE1010001')}</div>
      <div>
        <div class="card prose">
          <h2 style="font-size:17px">이 계산기가 다른 이유</h2>
          <ul style="font-size:13.5px">
            <li><b>5세대 특약1·2 분리 반영</b> — 중증(산정특례) 여부에 따라 입원 30%/50%, 통원 Max(30%,3만)/Max(50%,5만)이 갈립니다.</li>
            <li><b>5세대 보장 제외 표시</b> — 근골격계 물리치료·체외충격파·비급여 주사제는 <b>0원(보장 제외)</b>으로 명확히 표시합니다.</li>
            <li><b>도수치료 관리급여</b> — 2026.7.1부터 1회 43,850원·본인부담 95%를 급여 규칙으로 계산합니다.</li>
            <li><b>통원 회당 한도 반영</b> — 4세대·5세대의 회당 보장한도(20만원)에 걸리면 그 사실을 표시합니다.</li>
          </ul>
          <div class="notice" style="margin-top:10px">
            병원 <b>공개가</b>와 실손 <b>보장액</b>은 다른 값입니다. 위 표의 '환자 최종 부담'은
            공개가에서 예상 보장액을 뺀 금액입니다.
          </div>
        </div>
        <div class="card">
          <h3>실손에서 보장되지 않는 항목</h3>
          <ul style="font-size:13px;padding-left:18px">
            {''.join(f'<li><b>{esc(n)}</b> — {esc(d)}</li>' for n, d, _ in EXCLUDED5)}
          </ul>
          <p class="calc-foot">앞의 세 항목(시력교정술·예방접종·치과 비급여 보철)은 5세대뿐 아니라 이전 세대에서도 약관상 보장 제외입니다. '
            '산정특례 대상 질환 치료로서 의학적 인과관계가 인정되는 경우의 판단은 보험사 심사 영역입니다.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>병원급 공개가 vs 전국 의원급 통계</h2>
    <p class="section-lead">왼쪽 숫자는 심평원 오픈API에서 <b>전수 수집한 병원급 이상</b> 기관들의 평균이고,
      오른쪽은 <b>통계청 KOSIS(승인번호 354006)</b>의 <b>전국 의원·치과의원 규모</b> 통계입니다.
      동네 의원 개별 가격은 공개 대상이 아니어서 이 통계로만 참고합니다.</p>
    {compare_table_html(items)}
    <p class="calc-foot">병원급: {esc(DATA_PERIOD)} · 의원급: {esc(KOSIS_PERIOD)}. 두 값은 집계 모집단이 달라
      같은 항목이라도 직접 비교 대상이 아닙니다. 도수치료는 2026-07-01 관리급여 전환으로 1회 43,850원 정액입니다.</p>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>지역별로 비교하기</h2>
    <p class="section-lead">같은 항목이라도 지역과 기관 규모에 따라 신고 가격이 다릅니다. 17개 시·도를 골라 항목별 평균·중간값과
      시·군·구별 시세를 볼 수 있습니다.</p>
    {region_chips()}
    <p class="calc-foot" style="margin-top:10px">
      <a class="btn sm" href="/ko/regions/">17개 시·도 전체 표로 보기</a>
      <span style="margin-left:8px">서울·경기·인천·부산·대구·대전·광주·울산·세종·강원·충북·충남·전북·전남·경북·경남·제주</span>
    </p>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>핵심 비급여 {len(items)}개 항목</h2>
    <p class="section-lead">심평원 공식 코드로 묶은 항목입니다. 항목을 누르면 그 항목의 세대별 처리를 볼 수 있습니다.
      (비급여 공개 코드 943건 가운데 이번 단계에서 다루는 {len(items)}개입니다.)</p>
    <div class="item-grid">{cards}</div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>1~5세대 실손 한눈에</h2>
    <p class="section-lead">2026년 5월 6일 5세대 실손 출시와 2026년 7월 도수치료 관리급여 전환을 반영한 표입니다.</p>
    {gen_table_html()}
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>데이터 범위와 출처</h2>
    <div class="grid g2">
      <div class="card prose">
        <div class="scope-note">{SCOPE_LONG}</div>
        <h3 style="margin-top:14px">출처</h3>
        <ul style="font-size:13.5px">
          <li>건강보험심사평가원 <b>비급여진료비정보조회서비스</b> (공공데이터포털 15001700) — 이용허락범위 <b>공공누리 제1유형(출처표시)</b></li>
          <li>금융위원회 2026-05-06 보도자료 — 5세대 실손의료보험 출시</li>
          <li>보건복지부 2026-07-01 보도자료 · 심평원 고시 2026-134~137호 — 도수치료 관리급여 전환</li>
        </ul>
      </div>
      <div class="card">
        <h3>이 사이트가 하지 않는 것</h3>
        <ul style="font-size:13.5px">
          <li>특정 병원 추천·예약·상담 연결 (의료법 제27조 환자 유인·알선 금지)</li>
          <li>의원급 가격 표시 (공개 범위 외)</li>
          <li>확인되지 않은 가격의 추정·보간 표시</li>
        </ul>
        <a class="btn ghost sm" href="/ko/guide/">이용 안내 자세히</a>
      </div>
    </div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>자주 묻는 질문</h2>
    {faq_html(faqs)}
  </div>
</section>
"""
    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite",
         "name": SITE_NAME, "url": SITE_BASE + "/ko/",
         "inLanguage": "ko",
         "publisher": {"@type": "Organization", "name": OWNER}},
        breadcrumb_jsonld([("/ko/", "홈")]),
        faq_jsonld(faqs),
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": "핵심 비급여 항목",
         "numberOfItems": len(items),
         "itemListElement": [
             {"@type": "ListItem", "position": i, "name": it["name"],
              "url": SITE_BASE + f"/ko/items/{it['slug']}/"}
             for i, it in enumerate(items, start=1)]},
    ]
    return layout("/ko/", f"{SITE_NAME} · 1~5세대 실손 계산기와 병원급 이상 비급여 공개가",
                  "병원급 이상 심평원 비급여 공개가와 1~5세대 실손(2026년 5세대·도수치료 관리급여 포함) 보장액을 한 번에 비교하는 계산기.",
                  body, [("/ko/", "홈")], jsonld, current="/ko/")


def page_calc(items: list[dict]) -> str:
    faqs = [
        ("5세대에서 비급여가 0원으로 나오는 이유는?",
         "근골격계 물리치료(도수치료 등)·체외충격파치료·비급여 주사제·미등재 신의료기술·D등급 치료는 "
         "5세대 비중증 비급여(특약2) 보장 대상에서 제외됩니다. 다만 산정특례 대상 질환 치료로서 특약1에 해당하면 보장될 수 있습니다."),
        ("4세대 통원에서 보장액이 20만원으로 잘리는 이유는?",
         "4세대 비급여는 통원 회당 보장한도 20만원이 있습니다. 진료비가 커도 회당 보장액은 20만원까지입니다."),
        ("도수치료를 선택하면 왜 금액이 43,850원으로 바뀌나요?",
         "2026년 7월 1일부터 관리급여로 전환되어 종별 구분 없이 1회 43,850원의 수가가 적용됩니다. "
         "횟수를 늘리면 총액이 자동으로 계산됩니다."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>1~5세대 실손 보장액 계산기</h1>
      <p class="section-lead">같은 비급여 진료비라도 가입 세대에 따라 돌려받는 금액이 크게 다릅니다.
        조건을 고르면 5개 세대를 한 번에 비교합니다.</p>
      <div class="meta">
        <span class="pill teal">2026.5.6 5세대 반영</span>
        <span class="pill blue">도수치료 관리급여 95%</span>
        <span class="pill line">병원급 이상 공개가 기준</span>
      </div>
    </div>
    <div class="calc-page">
      {calc_block(items, 'HE1010001', heading="조건 입력",
                  sub="항목을 고르고 금액·입원/통원·종별을 지정하면 세대별 보장액이 바로 갱신됩니다.")}
      <div class="sim-teaser" style="margin-top:14px">
        <div class="tx">
          <b>5세대 전환 손익 시뮬레이터</b>
          <p>내 세대와 월 보험료, 연간 이용 패턴을 넣으면 5세대로 전환했을 때 연간 절약·손해와
            손익분기점을 한 번에 계산합니다. 결과는 카드로 저장해 공유할 수 있습니다.</p>
        </div>
        <a class="btn sm" href="/ko/switch-gen5/">전환 손익 계산하기</a>
      </div>
    </div>
    <div class="card prose" style="margin-top:18px">
      <h2 style="font-size:17px">자주 묻는 질문</h2>
      {faq_html(faqs)}
    </div>
  </div>
</section>
"""
    jsonld = [breadcrumb_jsonld([("/ko/", "홈"), ("/ko/calc/", "실손 계산기")]), faq_jsonld(faqs)]
    return layout("/ko/calc/", f"실손 1~5세대 보장액 계산기 · {SITE_NAME}",
                  "비급여 진료비를 입력하면 1세대부터 5세대까지 실손 예상 보장액과 환자 최종 부담을 한 번에 비교합니다.",
                  body, [("/ko/", "홈"), ("/ko/calc/", "실손 계산기")], jsonld, current="/ko/calc/")


def _sim_amount_field(key: str, label: str, hint: str = "", maxv: int = 20000000,
                      fid: str = "") -> str:
    """시뮬레이터 금액 입력 — 직접 입력 + 슬라이더 병행."""
    fid = fid or key.replace("_", "-")
    hint_html = f' <span class="hint">{hint}</span>' if hint else ""
    return f"""
      <div class="field">
        <label for="{fid}">{label}{hint_html}</label>
        <div class="amount-row">
          <input type="number" id="{fid}" data-k="{key}" inputmode="numeric" min="0" step="10000"
                 max="{maxv}" placeholder="0" value="0">
          <span class="unit">원</span>
        </div>
        <input type="range" data-range="{key}" min="0" max="{maxv}" step="100000" value="0"
               aria-label="{label} 금액 슬라이더">
      </div>"""


def page_switch_gen5() -> str:
    path = "/ko/switch-gen5/"
    og_image = SITE_BASE + "/assets/og-switch-gen5.png"
    rate_rows = [
        ("1세대", "2009.9 이전", "계약별 상이(생보 20%·손보 0% 등)", "계약별 상이",
         "계약별 상이", "계약별 상이 — 약관의 자기부담률을 직접 입력"),
        ("2세대", "2009.10~2017.3", "표준형 20% · 선택형Ⅰ 10%", "같음", "20%", "20%"),
        ("3세대", "2017.4~2021.6", "표준형 10% · 선택형Ⅱ 20%", "같음", "20%",
         "20%(3대 비급여 특약 30%)"),
        ("4세대", "2021.7~2026.4", "20%", "Max(20%, 1·2만 원)", "30%",
         "30% · 연 5,000만 원 한도"),
        ("5세대", "2026.5.6 이후", "20%", "Max(건보 본인부담률, 20%, 1·2만 원)",
         "30% · 연 5,000만 원 · 상급·종합병원 입원 연 자기부담 상한 500만 원",
         "50% · 연 1,000만 원 · 통원 Max[50%, 5만 원] · 일당 20만 원 · 병·의원 입원 회당 300만 원"),
    ]
    rate_html = "".join(
        f"<tr><th scope=\"row\">{esc(g)}<br><span style=\"font-weight:500;color:var(--muted)\">{esc(p)}</span></th>"
        f"<td data-label=\"급여 입원\">{esc(i)}</td><td data-label=\"급여 통원\">{esc(o)}</td>"
        f"<td data-label=\"비급여 중증\">{esc(s)}</td><td data-label=\"비급여 비중증\">{esc(m)}</td></tr>"
        for g, p, i, o, s, m in rate_rows)
    faqs = [
        ("이 시뮬레이터는 무엇을 계산하나요?",
         "내 실손 세대와 월 보험료, 연간 급여·비급여 이용 금액을 넣으면 5세대로 전환했을 때의 연간 총비용"
         "(보험료 + 자기부담금)을 지금 세대와 비교해 절약·손해 금액과 손익분기점을 보여 줍니다. "
         "전환을 권하는 도구가 아니라 판단 근거를 정리해 주는 중립 계산기입니다."),
        ("결과가 실제 보험료·보험금과 다른 이유는 무엇인가요?",
         "공개된 표준 자기부담률과 입력값으로 계산한 참고용 추정치이기 때문입니다. 실제 보장과 보험료는 "
         "가입한 상품의 약관·상품설명서에 따르고 보험사·상품마다 다릅니다. 비급여 이용량에 따른 보험료 할증,"
         " 관리급여(도수치료 95%), 계약전환 할인·선택형 할인 특약은 1차 계산에 넣지 않고 안내로만 표시합니다."),
        ("5세대 보험료를 모르면 어떻게 하나요?",
         "기준 세대별 인하율로 자동 추정합니다. 4세대는 약 30% 인하(기본계약과 특약1만 가입하면 약 50% 수준), "
         "1·2세대는 50% 이상 인하, 3세대는 30~50% 범위로 보고되어 보수적으로 30%를 기본값으로 두었습니다. "
         "인하율은 직접 조절할 수 있고, 추정으로 계산한 값은 결과에 추정치로 표시됩니다."),
        ("1세대인데 계산이 되지 않는 이유는 무엇인가요?",
         "1세대는 계약별 자기부담이 달라(생명보험 20%·손해보험 0% 등) 단일 기준을 둘 수 없습니다. "
         "보험증권·약관의 자기부담률을 직접 입력하면 같은 방식으로 계산합니다."),
        ("비급여 보험료 할증(차등제)은 왜 반영하지 않았나요?",
         "할증률이 보험사·상품별로 달라(예: 3~5단계 +100/+200/+300%, 회사에 따라 +200/+300/+400%) 단일 값으로 "
         "계산할 수 없습니다. 5세대 특약2 차등제의 첫 적용은 2028년 5월 이후 갱신분부터이므로, "
         "이용량에 따라 차기 갱신 시 할증될 수 있다는 점을 안내로만 표시합니다."),
        ("관리급여(도수치료 95%)는 어떻게 처리하나요?",
         "관리급여는 급여로 편입되어 실손 급여 담보로 보상됩니다. 5세대 자기부담률은 입원 20%·외래 95%이고, "
         "선택형 할인 특약의 면책 옵션을 고르면 보장에서 제외될 수 있습니다. 도수치료 단가와 횟수는 "
         "관리급여 계산기에서 따로 확인하고, 이 시뮬레이터의 금액 계산에는 넣지 않았습니다."),
        ("입력한 정보는 어디로 저장되나요?",
         "어디에도 저장되지 않습니다. 계산은 방문자 브라우저 안에서 JavaScript로만 이루어지고 서버로 전송하지 "
         "않습니다. 이름·주민번호·보험증권번호·질병 이력·보험사명은 입력받지 않으며, 공유 링크에도 입력값을 담지 않습니다."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>실손 5세대 전환 손익 시뮬레이터</h1>
      <p class="section-lead">내 세대와 월 보험료, 연간 의료 이용 패턴을 넣으면 5세대로 전환했을 때
        <b>연간 절약·손해 금액</b>과 <b>손익분기점</b>을 계산합니다. 결과는 한 장 카드로 저장해 공유할 수 있습니다.</p>
      <div class="meta">
        <span class="pill teal">참고용 추정치</span>
        <span class="pill blue">입력값 서버 저장 없음</span>
        <span class="pill line">금융감독원 상담센터 1332</span>
      </div>
    </div>

    <form class="calc sim-calc" data-sim data-base="{esc(SITE_BASE)}" novalidate>
      <div class="calc-head">
        <h2>내 조건 입력</h2>
        <p>보험료와 이용 금액은 브라우저 안에서만 계산합니다. 입력값은 전송·저장되지 않습니다.</p>
      </div>
      <div class="calc-body">
        <div class="sim-step">
          <h3><span class="n">1</span> 현재 실손 세대</h3>
          <div class="seg five" id="gen-group" role="group" aria-label="현재 실손 세대">
            <button type="button" data-seg="gen" data-v="1" aria-pressed="false">1세대</button>
            <button type="button" data-seg="gen" data-v="2" aria-pressed="false">2세대</button>
            <button type="button" data-seg="gen" data-v="3" aria-pressed="false">3세대</button>
            <button type="button" data-seg="gen" data-v="4" aria-pressed="true">4세대</button>
            <button type="button" data-seg="gen" data-v="5" aria-pressed="false">5세대</button>
          </div>
          <div class="row-note" id="gen-period">2021년 7월~2026년 4월 가입</div>
          <div class="field" id="gen1-row" hidden>
            <label for="gen1-rate">약관상 자기부담률 <span class="hint">(%)</span></label>
            <div class="amount-row">
              <input type="number" id="gen1-rate" data-k="gen1_rate" inputmode="decimal"
                     min="0" max="100" step="1" placeholder="예: 20">
              <span class="unit">%</span>
            </div>
            <div class="row-note">1세대는 계약별 자기부담이 달라(생명보험 20%·손해보험 0% 등) 단일 기준이 없습니다.
              보험증권·약관의 자기부담률을 입력해야 계산합니다.</div>
          </div>
          <div class="field" id="gen2-row" hidden>
            <label for="gen2-type">2세대 가입유형</label>
            <select id="gen2-type" data-k="gen2_type">
              <option value="standard">표준형 (급여 자기부담 20%)</option>
              <option value="select1">선택형Ⅰ·Ⅱ (급여 자기부담 10%)</option>
            </select>
          </div>
          <div class="field" id="gen3-row" hidden>
            <label for="gen3-type">3세대 가입유형</label>
            <select id="gen3-type" data-k="gen3_type">
              <option value="standard">표준형 (급여 자기부담 10%)</option>
              <option value="select2">선택형Ⅱ (급여 자기부담 20%, 3대 비급여 특약 30%)</option>
            </select>
          </div>
        </div>

        <div class="sim-step">
          <h3><span class="n">2</span> 보험료</h3>
          <div class="field">
            <label for="pcur">현재 월 보험료 <span class="hint">(지금 납입 중인 월 보험료)</span></label>
            <div class="amount-row">
              <input type="number" id="pcur" data-k="pcur" inputmode="numeric" min="0" step="100"
                     placeholder="예: 24000">
              <span class="unit">원</span>
              <button type="button" class="chip-btn" id="pcur-unknown" aria-pressed="false">모름</button>
            </div>
            <div class="row-note">보험사 앱·보험증권·보험료 납입 내역에서 확인할 수 있습니다. 모르면 계산을 보류하고
              범위만 안내합니다.</div>
          </div>
          <div class="field">
            <span class="label" id="p5-label">5세대 월 보험료</span>
            <div class="seg two" role="group" aria-labelledby="p5-label">
              <button type="button" data-seg="p5_mode" data-v="auto" aria-pressed="true">모르면 자동 추정</button>
              <button type="button" data-seg="p5_mode" data-v="manual" aria-pressed="false">알면 직접 입력</button>
            </div>
            <input type="hidden" data-k="p5_mode" value="auto">
            <div id="p5-auto-row" style="margin-top:10px">
              <label for="discount">인하율 <span class="hint" id="discount-val">30%</span></label>
              <input type="range" id="discount" data-k="discount" min="10" max="70" step="1" value="30">
              <div class="row-note">4세대 대비 약 30% 인하(기본계약과 특약1만 가입하면 약 50% 수준), 1·2세대 대비
                50% 이상 인하, 3세대는 30~50% 범위로 보고되어 보수적으로 30%를 기본값으로 둡니다.
                자동 추정값은 결과에 <b>추정치</b>로 표시됩니다.</div>
            </div>
            <div id="p5-manual-row" hidden style="margin-top:10px">
              <div class="amount-row">
                <input type="number" id="p5" data-k="p5" inputmode="numeric" min="0" step="100"
                       placeholder="예: 17000">
                <span class="unit">원</span>
              </div>
              <div class="row-note">보험사가 제시한 5세대 전환 보험료를 입력하면 추정 없이 그 값으로 계산합니다.</div>
            </div>
          </div>
        </div>

        <div class="sim-step">
          <h3><span class="n">3</span> 연간 의료 이용 패턴</h3>
          <p class="row-note" style="margin-top:-4px">지난 1년(또는 앞으로 1년 예상) 이용 금액을 넣습니다. 이용이 없으면 0으로 두세요.</p>
          {_sim_amount_field('in_cov', '급여 입원', '(건강보험이 적용되는 입원 진료비)')}
          <div class="field">
            <label for="out-cov">급여 통원 <span class="hint">(건강보험이 적용되는 외래 진료비)</span></label>
            <div class="amount-row">
              <input type="number" id="out-cov" data-k="out_cov" inputmode="numeric" min="0"
                     step="10000" max="20000000" placeholder="0" value="0">
              <span class="unit">원</span>
            </div>
            <input type="range" data-range="out_cov" min="0" max="20000000" step="100000" value="0"
                   aria-label="급여 통원 금액 슬라이더">
            <div class="visit-row">
              <label for="out-visits">통원 횟수 <span class="hint">(선택)</span></label>
              <input type="number" id="out-visits" data-k="out_visits" inputmode="numeric"
                     min="0" max="365" step="1" placeholder="0">
              <span class="unit">회</span>
            </div>
            <div class="row-note">횟수를 넣으면 5세대 급여 통원의 최소 자기부담금(병·의원·약국 1만 원,
              종합·상급종합병원 2만 원)을 회차별로 반영합니다.</div>
          </div>
          {_sim_amount_field('severe', '비급여 중증', '(암·뇌·심장·산정특례 질환 치료)')}
          <div class="field">
            <label for="mild">비급여 비중증 <span class="hint">(도수치료·체외충격파·비급여 주사제 등)</span></label>
            <div class="amount-row">
              <input type="number" id="mild" data-k="mild" inputmode="numeric" min="0"
                     step="10000" max="20000000" placeholder="0" value="0">
              <span class="unit">원</span>
            </div>
            <input type="range" data-range="mild" min="0" max="20000000" step="100000" value="0"
                   aria-label="비급여 비중증 금액 슬라이더">
            <div class="visit-row">
              <label for="mild-visits">비중증 통원 횟수 <span class="hint">(선택)</span></label>
              <input type="number" id="mild-visits" data-k="mild_visits" inputmode="numeric"
                     min="0" max="365" step="1" placeholder="0">
              <span class="unit">회</span>
            </div>
            <div class="row-note">5세대 비중증 비급여는 50%에 통원 최소 자기부담 5만 원이 적용됩니다.
              횟수를 넣으면 회차별 최소 자기부담을 반영합니다.</div>
          </div>
          <div class="field">
            <label for="inst">주로 이용하는 의료기관 규모</label>
            <select id="inst" data-k="inst">
              <option value="clinic">의원·약국 (통원 최소공제 1만 원)</option>
              <option value="hospital">병원 (1만 5천 원)</option>
              <option value="general">종합병원 (2만 원)</option>
              <option value="tertiary">상급종합병원 (2만 원)</option>
            </select>
            <div class="row-note">통원 최소 자기부담금 계산에만 쓰입니다. 기관 이름은 받지 않습니다.</div>
          </div>
          <div class="field">
            <label class="check-row" for="managed">
              <input type="checkbox" id="managed" data-k="managed">
              <span>관리급여(도수치료 등 2026년 7월 편입)를 이용하고 있습니다</span>
            </label>
            <div class="row-note">체크하면 관리급여 보상 방식과 선택형 할인 특약 면책 안내를 결과에 함께 표시합니다.
              금액 계산에는 넣지 않습니다.</div>
          </div>
        </div>
      </div>
    </form>

    <div class="result sim-result" id="sim-result">
      <div class="result-head">
        <h3>전환 손익 결과</h3>
        <span class="sub">입력값은 브라우저에서만 계산됩니다</span>
      </div>
      <div id="sim-out" aria-live="polite">
        <div class="sim-hold"><b>현재 월 보험료를 입력하면 결과가 나옵니다.</b> 세대와 이용 금액을 넣고 보험료를 입력해 주세요.</div>
      </div>
      <div class="sim-share">
        <button type="button" class="btn sm" data-share="card" disabled>카드 저장(PNG)</button>
        <button type="button" class="btn sm ghost" data-share="kakao" disabled>카톡으로 공유</button>
        <button type="button" class="btn sm ghost" data-share="image" disabled>이미지로 공유</button>
        <button type="button" class="btn sm ghost" data-share="copy" disabled>결과 링크 복사</button>
      </div>
      <p class="sim-share-msg" id="sim-share-msg" role="status" aria-live="polite"></p>
      <input type="text" id="sim-link" readonly hidden aria-label="복사할 결과 주소">
      <p class="calc-foot">공유 카드에는 이름·월 보험료·세부 이용 내역을 넣지 않습니다. 카드와 링크에는
        medical-finder-kr.pages.dev 주소와 참고용 추정치 고지가 함께 표시됩니다.</p>
    </div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2>세대별 자기부담률 기준</h2>
    <p class="section-lead">이 시뮬레이터가 쓰는 표준 자기부담률입니다. 개별 계약은 약관이 우선합니다.</p>
    <div class="table-wrap">
      <table class="plain stack">
        <thead><tr><th scope="col">세대</th><th scope="col">급여 입원</th><th scope="col">급여 통원</th>
          <th scope="col">비급여 중증</th><th scope="col">비급여 비중증</th></tr></thead>
        <tbody>{rate_html}</tbody>
      </table>
    </div>
    <p class="calc-foot">표의 %는 모두 <b>자기부담률</b>(환자가 부담하는 비중)입니다. <b>Max(A, B)</b>는
      '비율로 계산한 금액'과 '최소 공제액' 중 큰 금액을 환자 부담으로 본다는 뜻입니다.
      1세대는 계약별 차이가 커 직접 입력을 받고, 2·3세대는 대표 유형(표준형·선택형)만 반영합니다.</p>

    <div class="grid g2" style="margin-top:14px">
      <div class="card prose">
        <h2 style="font-size:17px">계산 방법</h2>
        <p style="font-size:13.5px">연간 총비용 = <b>월 보험료 × 12 + 연간 자기부담금</b>입니다.
          같은 이용 패턴을 현재 세대와 5세대 규칙에 각각 적용해 두 총비용의 차이를 냅니다.</p>
        <ul style="font-size:13.5px">
          <li>Δ = 현재 세대 연간 총비용 − 5세대 연간 총비용</li>
          <li>Δ가 양수면 전환 시 그만큼 <b>절약</b>, 음수면 그만큼 <b>손해</b>입니다.</li>
          <li>연 |Δ| 가 5만 원 이하면 이용 패턴이 조금만 달라져도 결과가 뒤집히므로 <b>판단 보류</b>로 표시합니다.</li>
          <li>손익분기 그래프는 비중증 비급여 이용액만 0부터 늘리며 Δ가 0이 되는 지점을 찾습니다.</li>
          <li>5세대 특약1·특약2의 연간 보장한도(5,000만 원·1,000만 원)는 보험사 지급 상한으로 적용합니다.</li>
        </ul>
        <h3>계산에 넣지 않은 항목</h3>
        <ul style="font-size:13.5px">
          <li>비급여 보험료 차등제 할증 — 할증률이 보험사·상품별로 달라 단일 값이 없습니다. 첫 적용은 2028년 5월 이후 갱신분부터입니다.</li>
          <li>관리급여(도수치료 95%) 금액 — 급여 규칙으로 따로 계산해야 합니다.</li>
          <li>계약전환 할인(3년간 50%, 6개월 한시)·선택형 할인 특약 — 대상이 2013년 3월 이전 초기 실손으로 한정됩니다.</li>
          <li>회차별 보장한도(5세대 통원 일당 20만 원, 병·의원 입원 회당 300만 원, 4세대 통원 회당 20만 원)</li>
          <li>5세대 중증 입원 연간 자기부담 상한 500만 원 — 입원 여부·기관에 따라 달라 넣지 않았습니다.</li>
        </ul>
        <h3>고정 고지</h3>
        <ul style="font-size:13px;color:var(--ink-2)">
          <li>비급여 이용량에 따라 차기 갱신 시 할증될 수 있습니다(할증률은 보험사·상품별로 다릅니다).
            5세대 특약2 차등제의 첫 적용은 2028년 5월 이후 갱신분부터입니다. 할증 반영 계산은 준비 중입니다.</li>
          <li>4·5세대는 5년마다 재가입하며, 재가입 시점의 약관이 적용됩니다.</li>
          <li>전환 후 3개월 이내에는 조건 없이, 3~6개월은 보험금 미수령 시에만 철회할 수 있고 6개월이 지나면 철회할 수 없습니다.</li>
          <li>모든 금액은 참고용 추정치입니다. 전환 전 약관을 확인하고, 궁금한 점은 금융감독원 상담센터(국번 없이 1332)에 문의하세요.</li>
        </ul>
      </div>
      <div>
        <div class="card prose">
          <h2 style="font-size:17px">결과를 읽는 순서</h2>
          <ol style="font-size:13.5px">
            <li><b>큰 숫자</b> — 연간 절약·손해 금액과 판단 방향(전환 유리·유지 유리·판단 보류)입니다.</li>
            <li><b>판단 근거 3줄</b> — 보험료 절감액, 자기부담 증가액, 손익분기점입니다.</li>
            <li><b>손익분기 그래프</b> — 비중증 비급여를 얼마나 쓰면 결과가 뒤집히는지 보여 줍니다.</li>
            <li><b>고지 문항</b> — 할증·관리급여·재가입·철회 기한은 계산에 넣지 않고 안내로 표시합니다.</li>
          </ol>
        </div>
        <div class="card prose">
          <h2 style="font-size:17px">공유 카드</h2>
          <p style="font-size:13.5px">결과를 카드 이미지(PNG)로 저장하거나 카카오톡·링크로 공유할 수 있습니다.
            카드에는 연간 절약·손해 금액과 판단 근거 1줄, 사이트 주소만 담기고 이름·보험료·이용 내역은 담기지 않습니다.</p>
          <p style="font-size:13px;color:var(--muted)">공유 링크에는 utm_source(카카오톡·이미지 공유·링크 복사),
            utm_medium, utm_campaign과 결과 구분(절약·손해·보류)만 붙습니다. 입력값은 담지 않습니다.</p>
        </div>
      </div>
    </div>

    <h2 style="margin-top:30px">자주 묻는 질문</h2>
    {faq_html(faqs)}

    <div class="card prose" style="margin-top:22px">
      <h2 style="font-size:16px;margin-top:0">1차 출처</h2>
      <ul style="font-size:13px">
        <li>금융위원회·금융감독원 2026-05-06 보도자료 및 5세대 실손보험 출시 Q&A — 급여 20%, 통원 최소 자기부담금 1만·2만 원,
          특약1(중증) 30%·연 5,000만 원, 특약2(비중증) 50%·연 1,000만 원·통원 Max[50%, 5만 원].</li>
        <li>금융위원회 고시 제2026-16호 부칙 제3조(특례)① — 5세대 특약2 비급여 차등제 첫 적용 2028년 5월 6일 이후 갱신분.</li>
        <li>삼성화재·DB손해보험 5세대 상품공시 — 재가입(갱신) 주기 5년, 회사별 할증률 상이.</li>
        <li>보건복지부 2026-07-01 보도자료 · 심평원 고시 — 도수치료 관리급여 전환(1회 43,850원·본인부담 95%).</li>
        <li>보험업계 공시(2026-11) — 계약전환 할인(3년간 50%)·선택형 할인 특약 시행.</li>
      </ul>
      <p class="calc-foot">이 계산기는 투자·보험 권유 도구가 아닙니다. 특정 보험사·상품을 추천하지 않으며
        보험 제휴·설계사 알선을 하지 않습니다. 전환 전 약관을 확인하고, 궁금한 점은 금융감독원 상담센터
        (국번 없이 1332)에 문의하세요. <a href="/ko/medical-disclaimer/">의료 면책 고지</a> ·
        <a href="/ko/privacy/">개인정보처리방침</a></p>
    </div>

    <h2 style="margin-top:30px">함께 보면 좋은 가이드</h2>
    <p class="section-lead">세대별 구조와 청구·관리급여 기준을 정리한 해설입니다.</p>
    {guide_cards(heading="가이드")}
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), (path, "실손 5세대 전환 손익 시뮬레이터")]),
        faq_jsonld(faqs),
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": "실손 5세대 전환 손익 시뮬레이터",
            "url": SITE_BASE + path,
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Any",
            "inLanguage": "ko",
            "description": ("내 실손 세대와 월 보험료, 연간 의료 이용 금액을 입력하면 5세대 전환 시 "
                            "연간 절약·손해와 손익분기점을 계산하는 참고용 추정 도구입니다."),
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "KRW"},
            "publisher": {"@type": "Organization", "name": BRAND},
        },
    ]
    return layout(path, f"실손 5세대 전환 손익 시뮬레이터 · {SITE_NAME}",
                  "내 실손 세대와 월 보험료, 연간 급여·비급여 이용 금액을 넣으면 5세대 전환 시 연간 절약·손해와 "
                  "손익분기점을 계산합니다. 결과를 카드로 저장해 공유할 수 있는 참고용 추정 도구입니다.",
                  body, [("/ko/", "홈"), (path, "실손 5세대 전환 손익 시뮬레이터")], jsonld,
                  og_image=og_image, extra_js='<script src="/assets/switch-gen5.js" defer></script>')


def page_items(items: list[dict]) -> str:
    cards = "".join(f"""
      <a class="item-card" href="/ko/items/{esc(it['slug'])}/">
        <div class="top"><span class="nm">{esc(it['name'])}</span>
          {'<span class="pill red">전 세대 제외</span>' if len(it.get('excluded_gens') or []) >= 5
           else ('<span class="pill amber">일부 세대 제외</span>' if it.get('excluded_gens')
           else ('<span class="pill red">5세대 제외</span>' if it['excluded5'] and it['payment'] == '비급여'
                 else ('<span class="pill blue">관리급여 95%</span>' if it['payment'] == '관리급여'
                       else ('<span class="pill violet">3세대 특약</span>' if it['special3'] else '<span class="pill">기본</span>'))))}</div>
        <div class="cd">{esc(code_disp(it))}</div>
        <div class="sm">{esc(it['summary'])}</div>
      </a>""" for it in items)
    rows = "".join(
        f"<tr><th scope=\"row\"><a href=\"/ko/items/{esc(it['slug'])}/\">{esc(it['name'])}</a></th>"
        f"<td data-label=\"코드\">{'<code>' + esc(it['code']) + '</code>' if not not_listed(it) else '심평원 공개 코드 없음'}</td>"
        f"<td data-label=\"심평원 분류\">{esc(it['official_mid'])} &gt; {esc(it['official_sub'])}</td>"
        f"<td data-label=\"보장\">{coverage_label(it)}</td></tr>"
        for it in items)
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>비급여 항목 {len(items)}개</h1>
      <p class="section-lead">심평원 공식 분류 코드 기준입니다. 항목별로 세대별 계산 방식과 보장 제외 여부가 다릅니다.</p>
    </div>
    <div class="item-grid">{cards}</div>
    <h2 style="margin-top:28px">항목 코드 표</h2>
    <div class="table-wrap">
      <table class="plain stack">
        <thead><tr><th scope="col">항목</th><th scope="col">코드</th><th scope="col">심평원 분류</th><th scope="col">실손 보장</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <p class="calc-foot">수면내시경은 시술 자체가 급여라 비급여 공개 대상이 아니며, 공개 항목은
      <b>진정내시경 환자관리료</b>입니다. 지르코니아 임플란트는 치과병원만 공개 대상입니다.</p>
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/items/", "비급여 항목")]),
        {"@context": "https://schema.org", "@type": "ItemList", "name": "비급여 항목",
         "numberOfItems": len(items),
         "itemListElement": [{"@type": "ListItem", "position": i, "name": it["name"],
                              "url": SITE_BASE + f"/ko/items/{it['slug']}/"} for i, it in enumerate(items, 1)]},
    ]
    return layout("/ko/items/", f"비급여 항목 {len(items)}개 코드 정리 · {SITE_NAME}",
                  "뇌·척추·관절 MRI, 초음파, 진정내시경 Ⅰ~Ⅲ, 지르코니아 임플란트·크라운(PFM), 백내장 다초점 인공수정체, 라식, "
                  "대상포진 예방접종, 체외충격파, 증식치료, 도수치료, 신장분사치료의 심평원 코드와 세대별 실손 처리·보장 제외.",
                  body, [("/ko/", "홈"), ("/ko/items/", "비급여 항목")], jsonld, current="/ko/items/")


def page_item(it: dict, items: list[dict]) -> str:
    sib = [x for x in items if x["code"] != it["code"]][:4]
    sib_html = "".join(f'<a class="item-card" href="/ko/items/{esc(x["slug"])}/"><div class="top">'
                       f'<span class="nm">{esc(x["name"])}</span></div><div class="cd">{esc(code_disp(x))}</div>'
                       f'<div class="sm">{esc(x["summary"])}</div></a>' for x in sib)
    excl_gens = it.get("excluded_gens") or []
    if 5 in excl_gens:
        gen5_cell = (f'<b>5세대 비급여 특약 보장 제외</b> — 사유: {esc(it.get("exclude_reason") or "보장 대상 아님")} '
                     '특약1(중증)·특약2(비중증) 모두 같은 제외 문언이 적용됩니다.')
        pay_pill = '<span class="pill red">전 세대 제외</span>' if len(excl_gens) >= 5 else '<span class="pill amber">일부 세대 제외</span>'
    elif it["payment"] == "관리급여":
        gen5_cell = ('<b>비급여 특약 대상 아님</b> — 2026.7.1 관리급여 전환으로 급여 항목입니다. '
                     '5세대는 급여 통원 자기부담률을 건강보험 본인부담률(95%)에 연동해 실손 보장이 5% 수준입니다.')
        pay_pill = '<span class="pill blue">관리급여 95%</span>'
    elif it["excluded5"]:
        gen5_cell = (f'<b>비중증 비급여 보장 제외</b> — 사유: {esc(it["excluded5"])}. '
                     '특약2에서 보장하지 않아 예상 보장액이 0원입니다.')
        pay_pill = '<span class="pill red">5세대 제외</span>'
    else:
        gen5_cell = ('<b>비중증 비급여(특약2)로 보장</b> — 입원 50% · 통원 Max(50%, 5만원). '
                     '산정특례(중증) 질환 치료면 특약1(입원 30%·통원 Max(30%, 3만원))이 적용됩니다.')
        pay_pill = '<span class="pill">비중증 보장</span>'
    if 3 in excl_gens:
        special3 = ("보장 제외 — 3세대도 약관상 보장하지 않는 항목입니다(" + (it.get("exclude_reason") or "") + ")")
    else:
        special3 = ('해당 — 3세대는 비급여 기본 특약으로 분리되어 통원 시 Max(30%, 2만원) 공제'
                    if it["special3"] and it["payment"] != "관리급여" else
                    ('2026.7 이전 비급여 시절 특약 대상이었으나, 지금은 급여로 계산' if it["payment"] == "관리급여"
                     else "해당 없음 — 기본 비급여로 20% 공제"))
    # 세대별 보장 한 줄 요약(제외 세대가 있는 항목만)
    gen_cover_note = ""
    if excl_gens:
        covered = [g for g in (1, 2, 3, 4, 5) if g not in excl_gens]
        names = {1: "1세대", 2: "2세대", 3: "3세대", 4: "4세대", 5: "5세대"}
        excl_txt = "전 세대" if len(excl_gens) >= 5 else ", ".join(names[g] for g in excl_gens)
        cov_txt = "·".join(names[g] for g in covered) if covered else "없음"
        gen_cover_note = (
            '<h3>세대별 보장</h3>'
            f'<p style="font-size:13.5px">보장 제외: {excl_txt} · 계산에 반영되는 세대: {cov_txt}<br>'
            '<span class="muted">가입 시기와 상품 약관(재가입·전환 여부)에 따라 판단이 달라질 수 있습니다.</span></p>')
    top_notice = ""
    if it["payment"] == "관리급여":
        top_notice = (
            '<div class="notice amber" role="note" style="margin-bottom:16px" data-managed-notice>'
            '<b>2026년 7월 1일부터 도수치료는 관리급여(선별급여)입니다.</b> '
            '1회 <b>43,850원</b>(종별 가산 없이 동일) · 환자 본인부담률 <b>95%</b> → 1회 부담 41,658원, '
            '주 2회·연간 15회(수술·골절 등 예외 24회) 한도. '
            '<br><b>아래 병원급 공개가는 2026년 비급여 공개자료 기준</b>이라 7월 전환 이후 실제 청구액과 다릅니다. '
            '지금은 비급여 특약이 아니라 <b>급여 수가 43,850원</b>으로 계산하세요.</div>')
    calc_amt = default_amount(it)
    if not_listed(it):
        code_pill = '<span class="pill line">심평원 공개 코드 없음</span>'
        calc_link = f"/ko/calc/?item={esc(it['code'])}"
        calc_note = ('심평원 공개 가격이 없는 항목이라 금액이 자동으로 채워지지 않습니다. '
                     '실제 청구 금액을 직접 입력하세요.')
    else:
        code_pill = (f'<span class="pill line"><code>{esc(it["code"])}</code>'
                     f'{" 외 " + str(len(it["codes"]) - 1) + "개 코드" if it.get("codes") else ""}</span>')
        calc_link = f"/ko/calc/?item={esc(it['code'])}&amount={calc_amt}"
        calc_note = f'링크를 누르면 금액이 <b>{won(calc_amt)}</b>으로 채워집니다. 실제 청구 금액으로 바꿔 계산하세요.'
    if it.get("codes"):
        code_cell = codes_inline(it)
    elif not_listed(it):
        code_cell = f'없음 (심평원 공개 목록 미수록) · 카탈로그 코드 <code>{esc(it["code"])}</code>'
    else:
        code_cell = f'<code>{esc(it["code"])}</code>'
    linked_row = ""
    if it.get("linked_items"):
        linked_row = ('<tr><th scope="row">기존 항목으로 분리된 코드</th><td>' + " · ".join(
            f'<a href="/ko/items/{esc(li["slug"])}/">{esc(li["label"])} (<code>{esc(li["code"])}</code>)</a>'
            for li in it["linked_items"]) + '</td></tr>')

    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>{esc(it['name'])}</h1>
      <p class="section-lead">{esc(it['summary'])}</p>
      <div class="meta">
        {code_pill}
        {pay_pill}
        {'<span class="pill violet">3세대 특약</span>' if it['special3'] and it['payment'] != '관리급여' else ''}
      </div>
    </div>
    {top_notice}
    <div class="grid g2">
      <div>
        <div class="card prose">
          <h2 style="font-size:17px">무엇을 비교하는 항목인가</h2>
          <p>{esc(it['summary'])}</p>
          <h3>확인할 점</h3>
          <p style="font-size:13.5px">{esc(it['watch'])}</p>
          <h3>3세대(착한실손) 처리</h3>
          <p style="font-size:13.5px">{esc(special3)}</p>
          <h3>5세대 처리</h3>
          <p style="font-size:13.5px">{gen5_cell}</p>
          {gen_cover_note}
          <a class="btn sm" href="{calc_link}">이 항목으로 계산하기</a>
          <p class="calc-foot">{calc_note}</p>
        </div>
        <div class="card prose">
          <h2 style="font-size:17px">자주 묻는 질문</h2>
          {faq_html([(q, a) for q, a in it['faq']])}
        </div>
      </div>
      <div>
        {price_block(it)}
        {kosis_card(it)}
        {hospital_table(it)}
        <div class="card">
          <h3>심평원 공식 분류</h3>
          <table class="plain" style="font-size:12.5px">
            <tbody>
              <tr><th scope="row">중분류</th><td>{esc(it['official_mid'])}</td></tr>
              <tr><th scope="row">소분류</th><td>{esc(it['official_sub'])}</td></tr>
              <tr><th scope="row">상세분류</th><td>{esc(it['official_dtl'] or '—')}</td></tr>
              <tr><th scope="row">항목 코드</th><td>{code_cell}</td></tr>
              {linked_row}
            </tbody>
          </table>
          <p class="calc-foot">치료재료 포함 여부·판독료 조건은 대부분 오픈API 상세설명(<code>cmmtTxt</code>)이 비어 있어
            화면에서 단정하지 않고, 방문 전 유선 확인을 안내합니다.</p>
        </div>
        <div class="card">
          <h3>같이 보는 항목</h3>
          <div class="grid" style="gap:8px">{sib_html}</div>
        </div>
      </div>
    </div>
  </div>
</section>
"""
    proc_ld = {"@context": "https://schema.org", "@type": "MedicalProcedure",
               "name": it["name"], "description": it["summary"]}
    if not not_listed(it):
        proc_ld["code"] = {"@type": "MedicalCode", "code": it["code"],
                           "codingSystem": "건강보험심사평가원 비급여 항목코드"}
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/items/", "비급여 항목"), (f"/ko/items/{it['slug']}/", it["name"])]),
        faq_jsonld([(q, a) for q, a in it["faq"]]),
        proc_ld,
    ]
    return layout(f"/ko/items/{it['slug']}/",
                  (f"{it['name']} 비급여 가격·실손 보장 · {SITE_NAME}" if not_listed(it)
                   else f"{it['name']} ({it['code']}) 비급여 가격·실손 보장 · {SITE_NAME}"),
                  f"{it['name']}의 심평원 공식 분류와 코드, 병원급 공개가·전국 의원급 통계, 실손 세대별 처리({coverage_label(it)})를 정리했습니다.",
                  body, [("/ko/", "홈"), ("/ko/items/", "비급여 항목"), (f"/ko/items/{it['slug']}/", it["name"])],
                  jsonld, current="/ko/items/")


def page_insurance() -> str:
    five = [
        ("특약1 · 중증 비급여", "산정특례 대상 질환(암·뇌혈관·심장·희귀난치) 치료",
         "입원 30% (상급·종합병원 입원 연 자기부담 상한 500만원)", "Max(30%, 3만원)",
         "연 5천만원 · 통원 회당 20만원"),
        ("특약2 · 비중증 비급여", "그 외 비급여 치료",
         "입원 50% (병·의원 회당 300만원 한도)", "Max(50%, 5만원)",
         "연 1천만원 · 통원 일당 20만원 · 이용량 할인·할증"),
    ]
    five_rows = "".join(
        f"<tr><th scope=\"row\">{esc(a)}<br><span style=\"font-weight:500;color:var(--muted)\">{esc(b)}</span></th>"
        f"<td data-label=\"입원\">{esc(c)}</td><td data-label=\"통원\">{esc(d)}</td>"
        f"<td data-label=\"한도\">{esc(e)}</td></tr>" for a, b, c, d, e in five)
    faqs = [
        ("5세대 실손에 갈아타면 무조건 유리한가요?",
         "아닙니다. 5세대는 보험료가 4세대 대비 약 30% 낮지만 비중증 비급여 자기부담률이 50%로 높아지고 "
         "근골격계 물리치료·체외충격파·비급여 주사제는 보장에서 빠집니다. 비급여 이용이 잦다면 불리할 수 있습니다."),
        ("1·2세대 가입자는 어떻게 되나요?",
         "2026년 11월부터 초기 실손(2013년 3월 이전 약관변경 조건이 없는 계약) 가입자를 위한 선택형 할인 특약과 "
         "계약전환 할인 제도가 시행됩니다. 기존 계약을 유지한 채 불필요한 보장을 빼고 보험료를 낮추거나, "
         "5세대로 전환하며 일정 기간 할인을 받을 수 있습니다."),
        ("도수치료는 세대별로 얼마나 돌려받나요?",
         "2026.7.1부터 관리급여(1회 43,850원, 본인부담 95%)로 급여 항목이 되었습니다. 급여 보장률이 높은 1·2세대는 "
         "보장 폭이 크지만, 5세대는 급여 통원 자기부담률을 건강보험 본인부담률(95%)에 연동해 실손 보장이 5% 수준입니다."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>1~5세대 실손보험 정리 (2026년 기준)</h1>
      <p class="section-lead">같은 병원비라도 가입 세대에 따라 환자 부담이 크게 달라집니다. 계산기와 함께 보세요.</p>
    </div>
    {gen_table_html()}

    <h2 style="margin-top:30px">5세대 실손의 두 특약 (2026.5.6 출시)</h2>
    <div class="table-wrap">
      <table class="plain stack">
        <thead><tr><th scope="col">구분</th><th scope="col">입원</th><th scope="col">통원</th><th scope="col">한도</th></tr></thead>
        <tbody>{five_rows}</tbody>
      </table>
    </div>
    <div class="notice" style="margin-top:12px">
      5세대 비중증 비급여에서 <b>보장하지 않는 항목</b>: 미용·성형 등 + 미등재 신의료기술 + 근골격계 물리치료·체외충격파치료·비급여 주사제.
      한국보건의료연구원 재평가 <b>D등급</b> 치료는 특약1·2 모두에서 제외됩니다.
    </div>

    <h2 style="margin-top:30px">도수치료 관리급여 (2026.7.1 시행)</h2>
    <div class="card prose">
      <ul style="font-size:13.5px">
        <li>1회 <b>43,850원</b> 단일 수가 — 요양기관 종별 가산 없음(모든 기관 동일)</li>
        <li>본인부담률 <b>95%</b> → 1회 환자 부담 <b>41,658원</b></li>
        <li>주 2회, 연간 총 <b>15회</b> / 수술·골절 등 뚜렷한 관절 구축·강직 소견 시 최대 <b>24회</b></li>
        <li>질환 치료 목적이 아닌 피로 회복·체형교정 목적은 비급여이며 실손 보장 대상이 아님</li>
      </ul>
      <a class="btn sm" href="/ko/calc/?item=MX1220000&visit=out&inst=hospital">도수치료로 계산해 보기</a>
    </div>

    <h2 style="margin-top:30px">자주 묻는 질문</h2>
    {faq_html(faqs)}
  </div>
</section>
"""
    jsonld = [breadcrumb_jsonld([("/ko/", "홈"), ("/ko/insurance/", "1~5세대 실손")]), faq_jsonld(faqs)]
    return layout("/ko/insurance/", f"1~5세대 실손보험 보장 비교 (2026년 5세대·도수치료 관리급여) · {SITE_NAME}",
                  "1세대부터 5세대까지 실손보험의 급여·비급여 자기부담률과 한도를 표로 정리했습니다. 5세대 특약1·2와 도수치료 관리급여 포함.",
                  body, [("/ko/", "홈"), ("/ko/insurance/", "1~5세대 실손")], jsonld, current="/ko/insurance/")


GUIDE_BY_SLUG = {g["slug"]: g for g in GUIDE_ARTICLES}
GUIDE_UPDATED = "2026-11-18"


def guide_url(slug: str) -> str:
    return f"/ko/guide/{slug}/"


def guide_cards(exclude: str = "", heading: str = "가이드 8편") -> str:
    """가이드 목록 카드 — 다른 가이드 교차링크에 공통으로 쓴다."""
    cards = []
    for g in GUIDE_ARTICLES:
        if g["slug"] == exclude:
            continue
        url = guide_url(g["slug"])
        cards.append(
            f'<a class="item-card" href="{url}">'
            f'<div class="top"><span class="nm">{esc(g["h1"])}</span>'
            f'<span class="pill teal">{g["no"]:02d}</span></div>'
            f'<div class="sm">{esc(g["desc"][:84])}…</div></a>')
    return '<div class="item-grid" data-guide-list>' + "".join(cards) + "</div>"


def guide_side_list(exclude: str) -> str:
    """본문 옆 목록용 — 자기 자신만 빠진 8편 목록."""
    out = []
    for o in GUIDE_ARTICLES:
        if o["slug"] == exclude:
            continue
        out.append(f'<li><a href="{guide_url(o["slug"])}">{esc(o["h1"])}</a></li>')
    return "".join(out)


def page_guide_article(g: dict) -> str:
    path = guide_url(g["slug"])
    toc = []
    body = []
    for i, (h2, html_body) in enumerate(g["sections"], start=1):
        sid = f"s{i}"
        toc.append(f'<li><a href="#{sid}">{esc(h2)}</a></li>')
        body.append(f'<h2 id="{sid}">{esc(h2)}</h2>\n{html_body}')
    site_links = "".join(
        f'<li><a href="{esc(href)}">{esc(label)}</a></li>' for href, label in g["site_links"])
    sources = "".join(f"<li>{esc(s)}</li>" for s in g["sources"])
    body_html = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <div class="pills" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
        <span class="pill teal">가이드 {g['no']:02d}</span>
        <span class="pill line">갱신 {esc(GUIDE_UPDATED)}</span>
        <span class="pill line">1차 출처 기준</span>
      </div>
      <h1>{esc(g['h1'])}</h1>
      <p class="section-lead">{esc(g['lead'])}</p>
    </div>
    <div class="grid g2" style="align-items:start">
      <article class="card prose">
        {''.join(body)}
      </article>
      <aside>
        <div class="card">
          <h3 style="font-size:15px">이 글의 목차</h3>
          <ol style="font-size:13px;margin:8px 0 0;padding-left:18px">{''.join(toc)}</ol>
        </div>
        <div class="card">
          <h3 style="font-size:15px">관련 페이지</h3>
          <ul style="font-size:13px;margin:8px 0 0;padding-left:18px">{site_links}</ul>
        </div>
        <div class="card">
          <h3 style="font-size:15px">다른 가이드</h3>
          <ul style="font-size:13px;margin:8px 0 0;padding-left:18px">{guide_side_list(g['slug'])}</ul>
        </div>
      </aside>
    </div>
    <h2 style="margin-top:30px">자주 묻는 질문</h2>
    {faq_html(g['faqs'])}
    <div class="card prose" style="margin-top:22px">
      <h2 style="font-size:16px;margin-top:0">1차 출처</h2>
      <ul style="font-size:13px">{sources}</ul>
      <p class="calc-foot">이 가이드는 공개된 법령·고시·보도자료와 본 사이트가 수집한 공개 데이터를 근거로
        작성한 해설입니다. 진료비와 보장 여부의 최종 판단은 진료 현장과 가입한 보험사의 약관·심사에 따르며,
        본 사이트는 특정 의료기관의 추천·예약·상담 알선을 하지 않습니다.
        <a href="/ko/guide/">가이드 전체 목록</a> · <a href="/ko/medical-disclaimer/">의료 면책 고지</a></p>
    </div>
    <h2 style="margin-top:30px">가이드 더 보기</h2>
    <p class="section-lead">실손·비급여 해설 가이드 {len(GUIDE_ARTICLES)}편을 주제별로 정리했습니다.</p>
    {guide_cards(exclude=g['slug'])}
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/guide/", "가이드"), (path, g["h1"])]),
        faq_jsonld(g["faqs"]),
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": g["h1"],
            "description": g["desc"],
            "inLanguage": "ko",
            "datePublished": GUIDE_UPDATED,
            "dateModified": GUIDE_UPDATED,
            "author": {"@type": "Organization", "name": f"{SITE_NAME} 편집팀"},
            "publisher": {"@type": "Organization", "name": BRAND},
            "mainEntityOfPage": SITE_BASE + path,
        },
    ]
    return layout(path, f"{g['meta_title']} · {SITE_NAME}", g["desc"], body_html,
                  [("/ko/", "홈"), ("/ko/guide/", "가이드"), ("", g["h1"])], jsonld, current="/ko/guide/")


def page_guide() -> str:
    faqs = [
        ("가격은 언제 갱신되나요?",
         "심평원 비급여 공개 자료는 연 1회(매년 9월) 전면 갱신되고, 기관 변경 보고분이 수시 반영됩니다. "
         "이 사이트는 수집 파이프라인을 주기적으로 실행해 갱신하며, 화면에 오픈API 조회일과 자료 기준을 함께 표시합니다."),
        ("왜 의원 가격은 없나요?",
         "공공데이터포털 15001700(비급여진료비정보조회서비스)은 의료법에 따라 <b>병원급 이상</b> 기관의 비급여만 제공합니다. "
         "의원·치과의원·한의원의 <b>개별 기관 가격</b>은 공개 API 대상이 아니어서 표시하지 않습니다. "
         "대신 전국 의원급 <b>평균·중간값</b>만 통계청 KOSIS(승인번호 354006) 공개 통계표에서 받아 참고로 보여 줍니다."),
        ("치료재료·판독료가 포함된 가격인가요?",
         "오픈API의 상세설명(<code>cmmtTxt</code>)은 943개 코드 중 1건만 값이 있어 포함 여부를 단정할 수 없습니다. "
         "그래서 화면에는 '치료재료·장비(1.5T/3.0T)·판독료 포함 여부는 병원마다 달라 방문 전 유선 확인 필요'로 안내합니다."),
        ("계산 결과를 보험금 청구에 그대로 쓸 수 있나요?",
         "아니요. 제도 기준 추정치이며, 실제 지급액은 가입 약관과 청구 이력에 따라 달라집니다. "
         "정확한 금액은 보험사에 문의하세요."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>가이드 · 이용 안내</h1>
      <p class="section-lead">실손·비급여 해설 가이드 {len(GUIDE_ARTICLES)}편과, 이 사이트가 무엇을 근거로 어디까지
        다루는지 정리했습니다.</p>
    </div>
    <h2 style="margin-top:6px">실손·비급여 해설 가이드 {len(GUIDE_ARTICLES)}편</h2>
    <p class="section-lead">계산기·시세표·지역 페이지의 숫자를 읽고 비교하는 방법을 주제별로 정리했습니다.</p>
    {guide_cards()}
    <p class="calc-foot" style="margin-top:10px">각 가이드는 법령·고시·보도자료와 심평원·통계청 공개 데이터를
      1차 출처로 삼았습니다. 가이드의 숫자는 진료비를 확정하지 않으며, 최종 비용과 보장은 진료 현장과 가입
      약관에서 확인해야 합니다. <a href="/ko/calc/">실손 보장액 계산기</a> ·
      <a href="/ko/items/">비급여 항목 {ITEM_COUNT}개</a> · <a href="/ko/regions/">지역별 시세</a>와 함께 보세요.</p>
    <h2 style="margin-top:30px">데이터 출처와 이용 안내</h2>
    <div class="grid g2">
      <div class="card prose">
        <h2 style="font-size:17px">데이터 출처와 라이선스</h2>
        <ul style="font-size:13.5px">
          <li><b>건강보험심사평가원 비급여진료비정보조회서비스</b> — 공공데이터포털 15001700,
            이용허락범위 <b>공공누리 제1유형(출처표시)</b>. 상업적 이용과 변경이 허용됩니다.</li>
          <li><b>통계청 국가통계포털 KOSIS 승인번호 354006</b>(작성기관 건강보험심사평가원) —
            의원·치과의원 비급여 진료비용 2026년 통계표에서 평균·중간값을 직접 수집(출처 표시).</li>
          <li><b>금융위원회 2026-05-06 보도자료</b> — 5세대 실손의료보험 출시 내용(특약1·2, 한도, 제외 항목).</li>
          <li><b>보건복지부 2026-07-01 보도자료 · 심평원 고시 2026-134~137호</b> — 도수치료 관리급여 전환.</li>
        </ul>
        <h3>수집 구조</h3>
        <ol style="font-size:13.5px">
          <li>항목 코드 목록 — <code>getNonPaymentItemCodeList2</code> (치료재료·부가조건 문구 <code>cmmtTxt</code> 포함)</li>
          <li>항목별 병원 목록 — <code>getNonPaymentItemHospList2</code> (기관별 <code>minPrc</code>·<code>maxPrc</code>)</li>
          <li>기관 상세 — <code>getNonPaymentItemHospDtlList</code> (<code>ykiho</code> 필요)</li>
          <li>종별·지역 통계 — <code>getNonPaymentItemClcdList</code> · <code>getNonPaymentItemSidoCdList</code></li>
        </ol>
        <p style="font-size:13.5px">수집한 원본은 <code>data/raw/</code> 에 그대로 보관하고, 정제 단계에서
          의원급 행과 0원·공란 행을 버린 뒤 평균·중간·최빈을 계산합니다.</p>
        <h3>수집 상태 (2026-11-17 실행)</h3>
        <div class="table-wrap">
          <table class="plain stack" style="font-size:12.5px">
            <thead><tr><th scope="col">오퍼레이션</th><th scope="col">응답</th><th scope="col">수집 결과</th></tr></thead>
            <tbody>
              <tr><th scope="row"><code>getNonPaymentItemCodeList2</code></th>
                <td data-label="응답"><span class="pill teal">전수</span></td>
                <td data-label="수집 결과">비급여 항목 코드 <b>943/943건</b></td></tr>
              <tr><th scope="row"><code>getNonPaymentItemHospList2</code></th>
                <td data-label="응답"><span class="pill teal">전수</span></td>
                <td data-label="수집 결과">핵심 {ITEM_COUNT}개 항목 중 {COLLECTED_ITEMS}개 수집 완료 · <b>{HOSP_ROWS:,}곳</b>(항목별 100% 응답) · 나머지 {ITEM_COUNT - COLLECTED_ITEMS}개 항목은 코드 확정 후 수집 예정</td></tr>
              <tr><th scope="row"><code>getNonPaymentItemClcdList</code></th>
                <td data-label="응답"><span class="pill amber">지연 504</span></td>
                <td data-label="수집 결과">응답 35~44초·재호출 504로 실패 → 같은 날 수집한 714건 스냅샷 사용</td></tr>
              <tr><th scope="row"><code>getNonPaymentItemSidoCdList</code></th>
                <td data-label="응답"><span class="pill amber">2페이지 504</span></td>
                <td data-label="수집 결과">사용하지 않고 기관 행의 시도명으로 직접 집계</td></tr>
              <tr><th scope="row">KOSIS 354006 (의원·치과의원)</th>
                <td data-label="응답"><span class="pill teal">전수</span></td>
                <td data-label="수집 결과">2026년 통계표에서 {ITEM_COUNT}개 항목 평균·중간·최저·최고 수집(로그인·API키 불필요)</td></tr>
            </tbody>
          </table>
        </div>
        <p class="calc-foot">위 상태는 2026-11-17 확인 시점의 값이며, 제공기관 사정으로 달라질 수 있습니다.
          통계 오퍼레이션이 응답하지 않아도 기관별 응답만으로 평균·중간·최빈을 계산합니다.</p>

        <h3>지역(시·도) 화면 집계 방법</h3>
        <p style="font-size:13.5px">17개 시·도 페이지는 기관 행의 <code>sidoCdNm</code>·<code>sgguCdNm</code>을 그대로 써서 집계합니다.
          심평원 오픈API는 전남·광주를 <b>‘전남광주’</b> 한 라벨로, 세종은 <b>‘세종시’</b>로 내려 주므로,
          전남·광주는 <b>기관의 시·군·구명이 ‘광주’로 시작하면 광주광역시, 그 외는 전라남도</b>로 나누었습니다(추정·보간 없음).
          지역 금액은 기관별 (최저가+최고가)/2 의 평균·중간값이며, 시·군·구 표는 응답 3곳 미만일 때 ¹ 표시로 참고값임을 밝힙니다.
          지역별 기관 수 차이 때문에 지역 간 순위가 우열을 뜻하지 않습니다.</p>

        <h3>가격을 표시하지 않는 경우</h3>
        <p style="font-size:13.5px">수집되지 않았거나, 공개 범위 밖(의원급)이거나, 금액이 비어 있는 경우에는
          추정값을 만들지 않고 비워 둡니다.</p>
      </div>
      <div>
        <div class="card prose">
          <h2 style="font-size:17px">범위 고지</h2>
          <div class="scope-note">{SCOPE_LONG}</div>
          <h3 style="margin-top:14px">계산의 가정</h3>
          <ul style="font-size:13px">
            <li>입력한 금액은 병원이 공개한 <b>비급여 진료비</b>(또는 관리급여 수가)입니다.</li>
            <li>급여 본인부담금이 입력값에 섞여 있으면 결과가 실제와 달라집니다.</li>
            <li>연간 한도는 누적 청구 이력이 필요해 계산에 넣지 않고 안내로 표시합니다.</li>
            <li>상품별 약관 차이(1세대 표준형/특약, 2세대 선택형 등)는 대표 유형만 반영합니다.</li>
          </ul>
        </div>
        <div class="card">
          <h3>법적 안전선</h3>
          <ul style="font-size:13px">
            <li>의료법 제27조에 따라 특정 의료기관의 <b>환자 유인·알선·광고</b>를 하지 않습니다.</li>
            <li>병원 추천, 예약 대행, 상담 연결 기능을 두지 않습니다.</li>
            <li>제휴·광고로 순위를 바꾸지 않습니다.</li>
          </ul>
        </div>
      </div>
    </div>
    <h2 style="margin-top:30px">자주 묻는 질문</h2>
    {faq_html(faqs)}
  </div>
</section>
"""
    jsonld = [breadcrumb_jsonld([("/ko/", "홈"), ("/ko/guide/", "가이드")]), faq_jsonld(faqs)]
    return layout("/ko/guide/", f"실손·비급여 해설 가이드 {len(GUIDE_ARTICLES)}편 · 이용 안내 · {SITE_NAME}",
                  "실손 세대 비교부터 비급여 시세 읽기·관리급여 95%·지역별 차이·납부와 청구·MRI·치과·도수치료까지 "
                  "해설 가이드 8편과 데이터 출처·공개 범위·계산의 가정을 함께 안내합니다.",
                  body, [("/ko/", "홈"), ("/ko/guide/", "가이드")], jsonld, current="/ko/guide/")


def page_privacy() -> str:
    faqs = [
        ("계산기에 입력한 금액이 서버로 전송되나요?",
         "아니요. 계산은 방문자 브라우저에서 JavaScript로만 이루어지며 입력값은 전송·저장되지 않습니다. "
         "주소창의 조건 값도 화면을 새로고짐하지 않고 공유할 수 있게 붙이는 용도입니다."),
        ("쿠키나 추적 도구를 쓰나요?",
         "방문 통계를 위해 Google Analytics 4(GA4)만 사용합니다. GA4는 페이지 경로, 유입 경로, 기기·브라우저 종류, "
         "대략적인 지역, 방문 시각 같은 이용 통계를 수집하며 이름·전화번호·이메일 같은 개인 식별 정보는 수집하지 않습니다. "
         "계산기에 입력한 금액은 GA4로도 전송하지 않습니다. 쿠키를 원하지 않으면 브라우저 설정에서 쿠키를 차단하거나 "
         "Google Analytics 차단 브라우저 확장을 쓰면 됩니다(계산 기능은 그대로 동작합니다). "
         "정적 호스팅 사업자(Cloudflare Pages)의 접속 기록은 해당 사업자 정책에 따라 처리됩니다."),
        ("데이터를 상업적으로 쓸 수 있는 라이선스인가요?",
         "심평원 비급여 자료는 공공누리 제1유형(출처표시)으로 상업적 이용과 변경이 허용됩니다. "
         "KOSIS 통계는 출처를 표시해 이용합니다. 두 출처 모두 화면과 이 페이지에 명시했습니다."),
    ]
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap">
    <div class="page-head">
      <h1>개인정보처리방침 · 면책 고지</h1>
      <p class="section-lead">이 사이트가 어떤 정보를 다루고, 어떤 데이터를 어떤 근거로 보여 주는지 정리했습니다.
        시행일 {esc(DATA_DATE)}.</p>
    </div>
    <div class="grid g2">
      <div class="card prose">
        <h2 style="font-size:17px">1. 개인정보 처리</h2>
        <ul style="font-size:13.5px">
          <li><b>수집하는 개인정보: 없음.</b> 회원가입·로그인·결제·상담 신청 기능을 두지 않으며,
            이름·전화번호·이메일·주민번호 등을 입력받지 않습니다.</li>
          <li><b>계산기 입력값</b>은 방문자 브라우저 안에서만 처리되고 전송·저장되지 않습니다(서버 없음).
            입력 금액은 방문 통계로도 보내지 않습니다.</li>
          <li><b>진료기록·처방·보험증권 정보</b>를 요구하지 않습니다. 진단·치료 목적의 의료 서비스가 아닙니다.</li>
          <li><b>방문 통계(Google Analytics 4)</b>만 수집합니다. 페이지 경로·기기·브라우저·대략적 지역·방문 시각 수준이며
            개인을 식별하는 정보는 다루지 않습니다(아래 4항 참고).</li>
          <li>문의가 필요한 경우에도 별도 개인정보를 수집하지 않는 창구만 둡니다.</li>
        </ul>
        <h3>2. 데이터 출처와 라이선스</h3>
        <ul style="font-size:13.5px">
          <li><b>건강보험심사평가원 비급여진료비정보조회서비스</b> (공공데이터포털 15001700) —
            이용허락범위 <b>공공누리 제1유형(출처표시)</b>. 병원급 이상 기관의 비급여 공개가.</li>
          <li><b>통계청 국가통계포털 KOSIS 승인번호 {esc(KOSIS_APPROVAL)}</b>(작성기관 건강보험심사평가원) —
            의원·치과의원 비급여 진료비용 통계표({esc(KOSIS_PERIOD)}). 의원급은 이 <b>전국 통계</b>만 참고로 표시합니다.</li>
          <li>5세대 실손·관리급여 제도 근거: 금융위원회 2026-05-06 보도자료, 보건복지부 2026-07-01 보도자료.
            계산 규칙은 공개된 제도 기준을 코드로 옮긴 것입니다.</li>
        </ul>
        <h3>3. 데이터 이용 원칙</h3>
        <ul style="font-size:13.5px">
          <li>수집하지 못한 값·확인되지 않은 가격은 <b>추정·보간하지 않고 비워 둡니다.</b></li>
          <li>가격 표시는 기관이 신고한 <b>비급여 최저·최고가</b>이며, 실제 청구액·할인·보험 적용과 다를 수 있습니다.</li>
          <li>공공누리 제4유형으로 배포되는 엑셀 파일은 제품 데이터로 쓰지 않으며, 병원급 가격은 오픈API,
            의원급 규모 값은 KOSIS 공개 통계표에서만 수집합니다.</li>
        </ul>
        <h3>4. 쿠키 · 방문 통계 (Google Analytics 4)</h3>
        <ul style="font-size:13.5px">
          <li>이 사이트는 Google Analytics 4(측정 ID <b>{GA4_ID}</b>)로 방문 통계를 수집합니다.
            수집 항목은 페이지 경로, 유입 경로(검색·참조), 기기·브라우저·화면 크기, 대략적인 지역(IP는 저장 전 잘라냅니다),
            방문 시각, 계산기 사용 같은 버튼·화면 조작 기록입니다.</li>
          <li>이름·전화번호·이메일 같은 <b>개인 식별 정보는 수집하지 않으며</b>, 광고 목적의 개인 맞춤·재마케팅에 쓰지 않습니다
            (광고 제품 미사용 · IP 익명화 설정).</li>
          <li>계산기에 입력한 금액·보험 세대 같은 값은 통계로 전송하지 않습니다.</li>
          <li>GA4는 <code>_ga</code> 등 쿠키를 사용합니다. 브라우저에서 쿠키를 차단하거나 Google Analytics 차단 확장을 쓰면
            수집되지 않으며, 계산 기능은 그대로 동작합니다.</li>
          <li>처리는 Google LLC(미국)가 운영하는 Google Analytics 정책을 따릅니다.</li>
        </ul>
      </div>
      <div class="card prose">
        <h2 style="font-size:17px">5. 면책 고지</h2>
        <ul style="font-size:13.5px">
          <li>이 사이트는 <b>정보 제공 사이트</b>이며 의료기관이 아니고, 진단·치료·처방을 하지 않습니다.
            증상이 있으면 의료기관을 방문하세요. 자세한 경계는 <a href="/ko/medical-disclaimer/">의료 면책 고지</a>에 정리했습니다.</li>
          <li>실손보험 계산 결과는 입력값과 공개된 제도 기준으로 산출한 <b>추정치</b>입니다.
            실제 보험금 지급액은 가입 상품·약관·자기부담금 누적·청구 이력에 따라 달라집니다.</li>
          <li>의료기관 가격은 인력·시설·장비·판독 조건에 따라 달라지며, 변경 보고의 행정 처리 기간 때문에
            실시간으로 반영되지 않습니다.</li>
          <li><b>의료법 제27조</b>에 따라 특정 의료기관의 환자 유인·알선·광고를 하지 않습니다.
            기관 목록은 공개가 순 나열이며 추천·순위가 아닙니다. 예약·상담 연결 기능도 두지 않습니다.</li>
          <li>본 사이트의 정보 이용으로 발생한 결정과 결과에 대한 책임은 이용자에게 있습니다.</li>
        </ul>
        <h3>6. 위치정보</h3>
        <p style="font-size:13.5px">지도·좌표 기반 기능을 제공하지 않으며, 병원정보서비스의 좌표값도 화면에 쓰지 않습니다
          (위치기반서비스사업 신고 전 노출 보류). 주소·종별·전화번호 수준의 텍스트 정보만 사용합니다.</p>
        <h3>7. 문의</h3>
        <p style="font-size:13.5px">데이터 오류·정정 요청은 <a href="/ko/contact/">문의 및 오류 제보</a> 폼으로 접수합니다.
          개인정보를 받지 않으므로 접수 시 개인정보를 보내지 마세요.<br>
          <span class="muted">{esc(OWNER)} · {esc(SITE_BASE)}</span></p>
        <p style="font-size:13.5px" class="muted">사이트의 목적과 데이터 출처는 <a href="/ko/about/">사이트 소개</a>,
          가격 수집·표시 원칙은 <a href="/ko/editorial-policy/">편집·데이터 정책</a>,
          진단·치료와의 경계는 <a href="/ko/medical-disclaimer/">의료 면책 고지</a>에서 확인할 수 있습니다.</p>
      </div>
    </div>
    <h2 style="margin-top:30px">자주 묻는 질문</h2>
    {faq_html(faqs)}
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld([("/ko/", "홈"), ("/ko/privacy/", "개인정보처리방침")]),
        {"@context": "https://schema.org", "@type": "WebPage", "name": "개인정보처리방침 · 면책 고지",
         "inLanguage": "ko", "url": SITE_BASE + "/ko/privacy/",
         "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_BASE + "/ko/"}},
        faq_jsonld(faqs),
    ]
    return layout("/ko/privacy/", f"개인정보처리방침 · 면책 고지 · {SITE_NAME}",
                  "계산 입력값은 전송하지 않고 GA4 방문 통계만 쓰는 처리방침과 면책 고지, 심평원 공공누리 제1유형·통계청 KOSIS 데이터 출처를 밝힙니다.",
                  body, [("/ko/", "홈"), ("/ko/privacy/", "개인정보처리방침")], jsonld)


# ------------------------------------------------------------------ 신뢰 페이지 (애드센스 기반)
DOC_SECTIONS = {
    "about": {
        "title": "사이트 소개",
        "desc": ("병원급 이상 비급여 공개가와 1~5세대 실손 보장액을 비교하는 중립 정보 사이트의 목적, "
                 "데이터 출처, 하지 않는 일과 운영 방식을 밝힙니다."),
        "lead": ("병원급 이상 의료기관의 비급여 공개가와 1~5세대 실손 보장액을 한 화면에서 비교하는 "
                 "중립 정보 사이트입니다. 특정 병원을 추천하거나 예약을 연결하지 않습니다."),
        "body": [
            ("무엇을 하는 사이트인가", [
                "건강보험심사평가원이 공공데이터포털로 공개하는 <b>병원급 이상</b> 의료기관의 비급여 진료비를 "
                "항목별로 모아 평균·중앙값·최저·최고가로 보여 주고, 같은 화면에서 2026년 5세대 실손과 "
                "7월 도수치료 관리급여 전환까지 반영한 예상 환자 부담을 계산합니다.",
                "가격과 보장액은 다른 값입니다. 화면의 '환자 최종 부담'은 공개가에서 예상 보장액을 뺀 "
                "금액이며, 실제 청구액과 보험금은 가입 상품과 약관에 따라 달라집니다.",
            ]),
            ("숫자의 출처", [
                "<b>건강보험심사평가원 비급여진료비정보조회서비스</b>(공공데이터포털 15001700) — "
                "이용허락범위 공공누리 제1유형(출처표시). 병원급 이상 기관의 비급여 공개가.",
                "<b>통계청 KOSIS 승인번호 354006</b>(작성기관 건강보험심사평가원) — 의원·치과의원 규모의 "
                "전국 평균·중간값 참고값.",
                "<b>제도 기준</b> — 5세대 실손은 금융위원회 2026-05-06 보도자료, 관리급여 전환은 "
                "보건복지부 2026-07-01 보도자료의 공개 기준을 계산 규칙으로 옮겼습니다.",
            ]),
            ("하지 않는 일", [
                "특정 의료기관의 <b>추천·순위·예약·상담 알선</b>을 하지 않습니다(의료법 제27조). "
                "기관 목록은 공개가 순 나열이며 추천이 아닙니다.",
                "진단·치료·처방에 대한 조언을 하지 않습니다. 증상이 있으면 의료기관을 방문하세요.",
                "동네 의원·치과의원·한의원의 <b>개별 기관 가격</b>은 공개 API 제공 범위가 아니어서 "
                "표시하지 않습니다. 전국 규모의 통계만 참고값으로 보여 줍니다.",
            ]),
            ("운영 주체와 운영비", [
                f"{OWNER} 운영팀이 만들고 관리합니다. 글로벌판 <b>K-MediCheck</b>"
                "(kmedicheck.com)와 같은 편집 원칙을 따르는 별도 사이트입니다.",
                "사이트는 무료이며, 운영비는 광고(Google AdSense) 수익으로 충당할 수 있습니다. "
                "광고는 라벨로 구분되고, 광고 수익은 공개가 데이터·계산 결과·항목 순서에 영향을 주지 "
                "않습니다. 현재 제휴(어필리에이트) 링크는 두지 않았습니다.",
            ]),
            ("정정과 갱신", [
                "가격은 기관이 신고한 시점의 금액이라 실제 청구액과 다를 수 있고, 변경 보고의 행정 처리 "
                "기간 때문에 실시간 반영되지 않습니다. 오류를 발견하면 "
                "<a href='/ko/contact/'>문의 및 오류 제보</a>로 알려 주세요. 영업일 기준 5일 이내 "
                "1차 답변을 목표로 합니다.",
            ]),
        ],
    },
    "editorial-policy": {
        "title": "편집·데이터 정책",
        "desc": ("비급여 가격을 어떤 원칙으로 수집·표시하고, 어떤 값은 비워 두는지, 정정 요청과 광고·"
                 "상업적 관계를 어떻게 분리하는지 정리했습니다."),
        "lead": "가격을 어떻게 모으고, 어떻게 표시하며, 무엇과 섞지 않는지 정리했습니다.",
        "body": [
            ("1. 공개된 가격만", [
                "병원급 가격은 심평원 비급여진료비정보조회서비스(공공데이터포털 15001700) 공개 자료만 "
                "사용합니다. 의원급 규모 값은 통계청 KOSIS 공개 통계표(승인번호 354006)만 참고합니다.",
                "확인되지 않은 가격, 비공개 견적, 커뮤니티에 돌는 금액은 제품 데이터로 쓰지 않습니다.",
            ]),
            ("2. 표시 규칙", [
                "가격은 기관이 신고한 <b>비급여 최저·최고가</b>를 그대로 쓰고, 평균·중앙값은 그 범위에서 "
                "산출합니다. 표본 수를 함께 표시합니다.",
                "수집하지 못한 값은 <b>추정·보간하지 않고 비워 둡니다.</b> 화면에 '-'로 표시되는 항목은 "
                "공개 자료에 값이 없거나 표시 기준을 충족하지 못한 경우입니다.",
                "계산 결과는 입력값이 아니라 공개된 제도 기준의 <b>추정치</b>이며, 계산이 이루어진 기준과 "
                "가정을 화면에 함께 표시합니다.",
            ]),
            ("3. 의원급을 표시하지 않는 이유", [
                "심평원 비급여 공개 API는 병원급 이상 기관을 대상으로 합니다. 동네 의원·치과의원·한의원의 "
                "개별 가격을 이 데이터로 추정하면 사실과 다른 가격이 되기 때문에 표시하지 않고, "
                "방문 전 유선 확인을 안내합니다.",
            ]),
            ("4. 라이선스", [
                "심평원 자료는 공공누리 제1유형(출처표시)으로 상업적 이용과 변경이 허용됩니다. "
                "<b>공공누리 제4유형으로 배포되는 엑셀 파일은 사용하지 않습니다.</b>",
                "KOSIS 통계는 출처를 표시해 이용하며, 화면과 개인정보처리방침에 출처를 명시합니다.",
            ]),
            ("5. 정정 절차", [
                "가격이 다르거나, 화면과 계산이 맞지 않는다는 제보는 "
                "<a href='/ko/contact/'>문의 및 오류 제보</a>로 받습니다. 원 공개 자료를 다시 확인하고, "
                "차이가 확인되면 데이터·화면을 함께 고칩니다.",
                "영업일 기준 5일 이내 1차 답변을 목표로 하며, 단순 문의보다 근거(기관명·항목·금액·"
                "확인 경로)가 있는 제보를 먼저 처리합니다.",
            ]),
            ("6. 광고와 데이터의 분리", [
                "광고는 라벨로 구분해 표시하고, 계산 버튼·입력창·결과 카드에 붙여 배치하지 않습니다.",
                "광고주·제휴 파트너가 공개 전에 가격 데이터를 보거나, 항목의 노출 순서나 계산 결과에 "
                "영향을 줄 수 없습니다. 특정 의료기관의 광고·제휴는 받지 않습니다.",
            ]),
        ],
    },
    "medical-disclaimer": {
        "title": "의료 면책 고지",
        "desc": ("이 사이트가 의료 서비스가 아니라는 점, 가격과 계산 결과의 한계, 실제 청구액·보험금과 "
                 "다를 수 있는 이유, 응급 상황 안내를 밝힙니다."),
        "lead": ("이 사이트는 공개된 가격과 제도 기준을 정리한 정보 사이트이며, 진단·치료·보험금 청구를 "
                 "대신하지 않습니다."),
        "body": [
            ("의료 서비스가 아닙니다", [
                "진단·치료·처방을 하지 않고, 특정 시술이나 검사가 필요한지 판단해 드리지 않습니다. "
                "모든 의료적 판단은 환자를 진찰한 의료인이 합니다.",
                "이 사이트는 의료기관이 아니며, 의료법 제27조에 따라 특정 의료기관의 환자 유인·알선·"
                "광고를 하지 않습니다.",
            ]),
            ("가격은 변동됩니다", [
                "표시된 가격은 기관이 신고한 시점의 금액입니다. 인력·시설·장비·재료비 변동과 변경 "
                "보고의 행정 처리 기간 때문에 실제 청구액과 다를 수 있습니다.",
                "비급여 항목은 기관이 자율적으로 정하는 가격이므로 같은 항목이라도 기관마다 다릅니다. "
                "방문 전에 기관에 직접 확인하세요.",
            ]),
            ("실손 계산은 추정치입니다", [
                "계산 결과는 입력값과 공개된 제도 기준으로 산출한 참고값입니다. 실제 보험금은 가입 시기·"
                "상품(표준형·선택형)·약관의 한도·자기부담금 누적·청구 이력에 따라 달라집니다.",
                "계약 내용과 보장 여부에 대한 최종 판단은 보험회사와 약관이 기준입니다.",
            ]),
            ("응급 상황", [
                "응급 증상이 있으면 119에 연락하거나 가까운 응급의료기관을 방문하세요. 이 사이트의 "
                "정보를 이유로 진료를 미루지 마세요.",
            ]),
            ("개인정보", [
                "이 사이트는 회원가입·로그인·결제가 없고, 계산기에 입력한 금액은 브라우저 안에서만 "
                "처리됩니다. 자세한 내용은 <a href='/ko/privacy/'>개인정보처리방침</a>을 참고하세요.",
            ]),
        ],
    },
    "contact": {
        "title": "문의 및 오류 제보",
        "desc": ("가격 오류·데이터 출처·화면 문제를 접수하는 구글 폼입니다. 예약·진료 상담은 받지 "
                 "않으며, 영업일 기준 5일 이내 답변을 목표로 합니다."),
        "lead": ("가격이 다르거나 화면이 이상하면 알려 주세요. 예약·진료 상담과 의료 질문에는 "
                 "답변하지 않습니다."),
        "body": [],
    },
}


def _doc_sections(sections: list[tuple[str, list[str]]]) -> str:
    out = []
    for head, paras in sections:
        ps = "".join(f"\n        <p>{p}</p>" for p in paras)
        out.append(f"      <section class=\"doc-sec\">\n        <h2>{head}</h2>{ps}\n      </section>")
    return "\n".join(out)


CONTACT_PANEL = f"""      <section class="doc-sec contact-sec">
        <h2>빠른 답변을 위해 필요한 것</h2>
        <ul class="doc-list">
          <li>문제가 보인 페이지 주소 (예: /ko/items/mri-brain/)</li>
          <li>어떤 값이 어떻게 보여야 하는지</li>
          <li>가격 정정 요청이라면 기관이 공개한 가격과 확인한 곳</li>
        </ul>
        <p class="muted" style="font-size:13.5px">영업일 기준 5일 이내 1차 답변을 목표로 합니다.
          폼은 이메일 주소를 자동으로 수집하지 않으며, 회신이 필요할 때만 폼 안에 회신처를 적어 주세요.
          예약·진료 상담, 개인 진료기록에 대한 질문은 받지 않습니다.</p>
        <p><a class="btn" href="{GOOGLE_FORM_KO}" target="_blank" rel="noopener">문의 폼 열기 ↗</a></p>
        <p class="muted" style="font-size:13px">폼은 Google Forms로 제공되며 새 탭에서 열립니다.</p>
        <div class="form-embed">
          <iframe src="{GOOGLE_FORM_KO}?embedded=true" title="메디컬 비급여 시세 파인더 문의 폼"
                  loading="lazy" width="100%" height="980" frameborder="0" marginheight="0"
                  marginwidth="0"><a href="{GOOGLE_FORM_KO}" target="_blank" rel="noopener">문의 폼 열기</a></iframe>
        </div>
      </section>"""


def page_trust(slug: str) -> str:
    """ /ko/about · editorial-policy · medical-disclaimer · contact """
    meta = DOC_SECTIONS[slug]
    path = f"/ko/{slug}/"
    crumbs = [("/ko/", "홈"), (path, meta["title"])]
    body_sections = CONTACT_PANEL if slug == "contact" else _doc_sections(meta["body"])
    body = f"""
<section class="section" style="padding-top:10px">
  <div class="wrap doc">
    <div class="page-head">
      <h1>{esc(meta['title'])}</h1>
      <p class="section-lead">{esc(meta['lead'])}</p>
      <p class="muted" style="font-size:12.5px">최종 수정 {esc(DATA_DATE)} · {esc(BRAND)} 패밀리</p>
    </div>
{body_sections}
  </div>
</section>
"""
    jsonld = [
        breadcrumb_jsonld(crumbs),
        {"@context": "https://schema.org", "@type": "WebPage", "name": meta["title"],
         "description": meta["desc"], "inLanguage": "ko", "url": SITE_BASE + path,
         "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_BASE + "/ko/"}},
    ]
    return layout(path, f"{meta['title']} · {SITE_NAME}", meta["desc"], body,
                  crumbs, jsonld)


# ------------------------------------------------------------------ 빌드
def write(path: str, text: str) -> None:
    target = DIST / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- 캐시 버스팅
# Cloudflare가 style.css 등을 최대 4시간 캐시해, 내용을 바꿔 배포해도 방문자
# 브라우저가 이전 스타일시트를 물고 있으면 모바일 헤더가 예전 모양으로 깨진다.
# 파일 내용의 SHA-256 앞 8자리를 ?v=<hash8> 로 붙여, 내용이 바뀔 때만 새 URL이 되게 한다.
BUST_ASSETS = ("style.css", "calc.js", "app.js", "switch-gen5.js")


def asset_versions(dist: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in BUST_ASSETS:
        p = dist / "assets" / name
        if p.exists():
            out[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:8]
    return out


def apply_cache_busting(dist: Path) -> dict[str, str]:
    """dist 안 모든 HTML의 assets/style.css·calc.js·app.js URL에 ?v=<hash8> 부착."""
    versions = asset_versions(dist)
    if not versions:
        return versions
    names = "|".join(re.escape(n) for n in BUST_ASSETS)
    pat = re.compile(r'((?:href|src)=")((?:[^"]*?/)?assets/(' + names + r'))(?:\?v=[0-9a-f]+)?(")')

    def repl(m: "re.Match[str]") -> str:
        v = versions.get(m.group(3))
        if not v:
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}?v={v}{m.group(4)}"

    for p in dist.rglob("*.html"):
        text = p.read_text(encoding="utf-8")
        new = pat.sub(repl, text)
        if new != text:
            p.write_text(new, encoding="utf-8")

    # 폰트 서브셋 CSS 도 같은 방식으로 ?v=<hash8> 부착 (주차장 폰트 표준화와 동일 규율)
    fonts_css = dist / "assets" / "fonts" / "pretendardvariable-dynamic-subset.css"
    if fonts_css.exists():
        fv = hashlib.sha256(fonts_css.read_bytes()).hexdigest()[:8]
        fpat = re.compile(r'(href=")/assets/fonts/pretendardvariable-dynamic-subset\.css(?:\?v=[0-9a-f]+)?(")')
        for p in dist.rglob("*.html"):
            text = p.read_text(encoding="utf-8")
            new = fpat.sub(rf"\g<1>/assets/fonts/pretendardvariable-dynamic-subset.css?v={fv}\g<2>", text)
            if new != text:
                p.write_text(new, encoding="utf-8")
        versions["pretendardvariable-dynamic-subset.css"] = fv
    return versions


def build(out: Path, base: str, live: bool) -> dict:
    global DIST, SITE_BASE, PREVIEW, DATASET, ITEM_COUNT, HOSP_ROWS, COLLECTED_ITEMS
    DIST = out
    SITE_BASE = base.rstrip("/")
    PREVIEW = not live

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    items = json.loads((DATA / "catalog_items.json").read_text(encoding="utf-8"))["items"]
    ITEM_COUNT = len(items)
    ds_path = DATA / "hira_dataset.json"
    DATASET = json.loads(ds_path.read_text(encoding="utf-8")) if ds_path.exists() else None
    hs_path = DATA / "hospitals.json"
    globals()["HOSPITALS"] = json.loads(hs_path.read_text(encoding="utf-8")) if hs_path.exists() else None
    HOSP_ROWS = sum((i.get("stats") or {}).get("n", 0) for i in (DATASET or {}).get("items", []))
    COLLECTED_ITEMS = sum(1 for i in (DATASET or {}).get("items", []) if (i.get("stats") or {}).get("n", 0) > 0)

    pages = {
        "ko/index.html": page_landing(items),
        "ko/calc/index.html": page_calc(items),
        "ko/switch-gen5/index.html": page_switch_gen5(),
        "ko/items/index.html": page_items(items),
        "ko/regions/index.html": page_regions(items),
        "ko/insurance/index.html": page_insurance(),
        "ko/guide/index.html": page_guide(),
        "ko/privacy/index.html": page_privacy(),
    }
    for slug in ("about", "editorial-policy", "medical-disclaimer", "contact"):
        pages[f"ko/{slug}/index.html"] = page_trust(slug)
    for g in GUIDE_ARTICLES:
        pages[f"ko/guide/{g['slug']}/index.html"] = page_guide_article(g)
    for it in items:
        pages[f"ko/items/{it['slug']}/index.html"] = page_item(it, items)
    for slug, _name, _full, _labels in REGIONS:
        pages[f"ko/regions/{slug}/index.html"] = page_region(slug, items)

    for path, text in pages.items():
        write(path, text)

    # 자산
    (DIST / "assets").mkdir(parents=True, exist_ok=True)
    for name in ("style.css", "calc.js", "app.js", "switch-gen5.js", "favicon.svg", "favicon.ico"):
        shutil.copyfile(ASSETS / name, DIST / "assets" / name)
    # 폰트 표준화(2026-11-21): Pretendard 자체 호스팅 — assets/fonts/ 를 dist 로 통째로 복사.
    fonts_src = ASSETS / "fonts"
    if fonts_src.exists():
        shutil.copytree(fonts_src, DIST / "assets" / "fonts")
    og_png = ASSETS / "og-switch-gen5.png"
    if og_png.exists():
        shutil.copyfile(og_png, DIST / "assets" / "og-switch-gen5.png")
    if (DATA / "hospitals.json").exists():
        shutil.copyfile(DATA / "hospitals.json", DIST / "assets" / "hospitals.json")
    med_items = []
    for it in items:
        ds = ds_item(it["code"]) or {}
        st = ds.get("stats") or {}
        entry = dict(it)
        entry.update({
            "amount_default": default_amount(it),
            "has_data": bool(ds.get("has_data")),
            "n": st.get("n"),
            "avg": (st.get("price") or {}).get("avg"),
            "median": (st.get("price") or {}).get("median"),
        })
        med_items.append(entry)
    med_data = {"preview": PREVIEW, "items": med_items,
                "generated": BUILD_TS, "data_date": DATA_DATE,
                "data_period": DATA_PERIOD}
    write("assets/med-data.js",
          "window.MED_CATALOG=" + json.dumps(med_data, ensure_ascii=False) + ";\n"
          "window.MED_PREVIEW=" + ("true" if PREVIEW else "false") + ";\n")

    # 루트 → /ko/ (HTTP 301)
    # 2026-11-17 M-01: 크롤러가 빈 meta-refresh 페이지를 받지 않도록 Cloudflare Pages
    # _redirects 로 301을 건다. Pages는 자산보다 redirect를 먼저 적용하므로 dist/index.html
    # (직접 요청·no-JS 대비)이 남아 있어도 '/' 요청은 301로 처리된다.
    write("index.html", f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>{esc(SITE_NAME)}</title><link rel="canonical" href="{esc(SITE_BASE)}/ko/">
<meta name="robots" content="{'noindex' if PREVIEW else 'index,follow'}">
<meta http-equiv="refresh" content="0; url=/ko/">
<meta name="naver-site-verification" content="{esc(NAVER_VERIFY)}">
<script>location.replace('/ko/');</script></head>
<body><p><a href="/ko/">국내 비급여·실손 파인더로 이동</a></p></body></html>""")
    if not PREVIEW:
        write("_redirects", "/ /ko/ 301\n")

    # 네이버 서치어드바이저 소유확인 파일(사이트 루트)
    write(NAVER_VERIFY_FILE, f"naver-site-verification: {NAVER_VERIFY_FILE}")

    write("404.html", f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>페이지를 찾을 수 없습니다 · {esc(SITE_NAME)}</title>
<meta name="color-scheme" content="light dark">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f6f8f7">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#101613">
<link rel="preload" href="/assets/fonts/PretendardVariable.subset.91.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/fonts/pretendardvariable-dynamic-subset.css">
<link rel="stylesheet" href="/assets/style.css"><meta name="robots" content="noindex"></head>
<body><main class="section"><div class="wrap"><h1>404 — 페이지를 찾을 수 없습니다</h1>
<p class="section-lead">주소가 바뀌었거나 아직 준비되지 않은 페이지입니다.</p>
<a class="btn" href="/ko/">홈으로</a> <a class="btn ghost" href="/ko/calc/">계산기로</a></div></main></body></html>""")

    # robots / sitemap / ads.txt
    write("ads.txt", ADS_TXT)
    if PREVIEW:
        write("robots.txt", "User-agent: *\nDisallow: /\n# 테스트 픽스처 프리뷰 빌드 (--live 로 색인 허용)\n")
    else:
        write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n")
    urls = [("/ko/", "1.0")]
    for p in pages:
        if p == "ko/index.html":
            continue
        path = p.replace("ko/", "/ko/").replace("/index.html", "/")
        if path.startswith("/ko/regions/"):
            prio = "0.8"
        elif path == "/ko/switch-gen5/":
            prio = "0.9"
        elif path in ("/ko/about/", "/ko/contact/"):
            prio = "0.6"
        elif path in ("/ko/editorial-policy/", "/ko/medical-disclaimer/"):
            prio = "0.4"
        else:
            prio = "0.9"
        urls.append((path, prio))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, prio in urls:
        sm.append(f"<url><loc>{SITE_BASE}{path}</loc><lastmod>{DATA_DATE}</lastmod>"
                  f"<changefreq>weekly</changefreq><priority>{prio}</priority></url>")
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm))

    versions = apply_cache_busting(DIST)

    return {"pages": len(pages) + 2, "items": len(items), "preview": PREVIEW,
            "out": str(DIST), "urls": [u[0] for u in urls],
            "asset_versions": versions}


def main() -> None:
    ap = argparse.ArgumentParser(description="메디컬 파인더 정적 사이트 빌드")
    ap.add_argument("--out", default=str(DIST))
    ap.add_argument("--base", default=SITE_BASE)
    ap.add_argument("--live", action="store_true", help="프리뷰 배너·noindex 를 끄고 배포용으로 빌드")
    args = ap.parse_args()
    info = build(Path(args.out), args.base, args.live)
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
