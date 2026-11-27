#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
빌드 산출물 정적 검사 (브라우저 없이 실행)

확인 항목
  A. 범위·표현 가드레일 — '병원급 이상' 명시, 의원급 오인 표현 금지, 프리뷰 배너
  B. 픽스처 데이터 격리 — 가짜 금액이 실제 공개가처럼 노출되지 않는지
  C. 구조 — JSON-LD 유효성, canonical, 내부 링크, h1 개수, 메타 설명
  D. 색인 — robots.txt / sitemap.xml 정합성
  E. 계산 규칙 골든 케이스(손으로 검산한 값)
  F. 파이프라인 — prepare_data(픽스처) 실행 결과 스키마와 synthetic 플래그

사용법: python3 scripts/qa_check.py [--dist dist]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
import calc_engine as E  # noqa: E402

fails: list[str] = []
warns: list[str] = []


def ok(name: str, cond: bool, detail="") -> bool:
    if not cond:
        fails.append(f"{name} · {detail}")
        print(f"FAIL {name}" + (f" · {detail}" if detail else ""))
    else:
        print(f"PASS {name}" + (f" · {detail}" if detail else ""))
    return bool(cond)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(BASE / "dist"))
    ap.add_argument("--live", action="store_true",
                    help="라이브 빌드 기준으로 검사(프리뷰 배너·noindex 가 없어야 통과)")
    ap.add_argument("--base", default="https://medical-finder-kr.pages.dev",
                    help="canonical·sitemap 기준 사이트 주소(빌드 --base 와 같게)")
    args = ap.parse_args()
    live = args.live
    dist = Path(args.dist)
    pages = sorted(dist.rglob("*.html"))
    site_base = args.base.rstrip("/")
    print(f"페이지 {len(pages)}개 검사" + (" · LIVE 모드" if live else " · 프리뷰 모드") + "\n")

    # ---------------------------------------------------------- A. 범위·표현 가드레일
    print("== A. 범위 고지 · 표현")
    main_pages = [p for p in pages if p.name == "index.html" and p.parent != dist]
    for p in main_pages:
        html = p.read_text(encoding="utf-8")
        rel = p.relative_to(dist)
        body = re.sub(r"<script.*?</script>", "", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)
        if rel.name == "404.html":
            continue
        ok(f"{rel}: '병원급 이상' 고지", "병원급 이상" in text, "")
        if live:
            ok(f"{rel}: 프리뷰 배너 없음", 'id="preview-banner"' not in html, "")
            ok(f"{rel}: noindex 없음", "noindex" not in html, "")
        else:
            ok(f"{rel}: 프리뷰 배너", 'id="preview-banner"' in html, "")
        ok(f"{rel}: 의원급 방문 전 확인 안내",
           ("유선 확인" in text) or ("공개 범위" in text), "")
        ok(f"{rel}: h1 1개", len(re.findall(r"<h1[\s>]", html)) == 1,
           f"h1={len(re.findall(r'<h1[ >]', html))}")

    # 금지 표현(의원급 포함 오인 / 과장)
    forbidden = [
        "전국 모든 의원", "의원급 포함", "모든 병의원 가격", "실시간 최저가 보장",
        "정부 공식 사이트", "심평원 공인", "보험금 청구 대행",
    ]
    for p in main_pages:
        text = p.read_text(encoding="utf-8")
        for f in forbidden:
            if f in text:
                fails.append(f"{p.relative_to(dist)}: 금지 표현 '{f}'")
    ok("금지 표현(의원급 포함·과장) 없음", not any("금지 표현" in f for f in fails))

    # 의료법 안전선 문구
    landing = (dist / "ko" / "index.html").read_text(encoding="utf-8")
    ok("랜딩: 의료법 제27조 안내", "제27조" in landing, "")
    ok("랜딩: 병원 추천·예약 안 함", "추천·예약" in landing or "추천" in landing, "")

    # ---------------------------------------------------------- B. 픽스처 데이터 격리
    print("\n== B. 픽스처 데이터 격리")
    ds_path = BASE / "data" / "hira_dataset.json"
    if ds_path.exists():
        ds = json.loads(ds_path.read_text(encoding="utf-8"))
        ok("데이터셋 synthetic 플래그 존재", "synthetic" in ds, str(ds.get("synthetic")))
        if ds.get("synthetic"):
            displayed = [i["code"] for i in ds["items"] if i.get("has_data")]
            ok("픽스처 모드: 표시 가능 항목 0건", displayed == [], str(displayed))
    for p in main_pages:
        text = p.read_text(encoding="utf-8")
        for token in ("TEST-YKIHO", "픽스처 상급종합병원", "픽스처 종합병원"):
            if token in text:
                fails.append(f"{p.relative_to(dist)}: 픽스처 기관명 노출 '{token}'")
        # 실제 기관명처럼 보이는 문자열(예시 금액 표기 없이 숫자+병원) 방지
    ok("픽스처 기관명 비노출", not any("픽스처 기관명 노출" in f for f in fails))
    if not live:
        ok("랜딩: 예시 금액 고지", "예시" in landing and "실제 심평원 공개 가격이 아닙니다" in landing, "")
    else:
        ok("랜딩: 프리뷰 배너·noindex 없음", 'id="preview-banner"' not in landing and "noindex" not in landing, "")
    # 화면에 숫자가 실데이터임을 알리는 문구
    ok("랜딩: 데이터 기준 표기", "2026년 비급여 공개 자료" in landing or "오픈API 조회" in landing, "")

    # ---------------------------------------------------------- C. 구조
    print("\n== C. 구조 · 메타")
    ld_types: dict[str, int] = {}
    for p in main_pages:
        html = p.read_text(encoding="utf-8")
        rel = p.relative_to(dist)
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        ok(f"{rel}: 메타 설명", bool(m) and 40 <= len(m.group(1)) <= 200,
           f"len={len(m.group(1)) if m else 0}")
        canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        ok(f"{rel}: canonical", bool(canon) and canon.group(1).startswith(site_base),
           canon.group(1) if canon else "없음")
        if canon and (".html" in canon.group(1) or "//" in canon.group(1)[8:]):
            fails.append(f"{rel}: canonical 형식 이상 {canon.group(1)}")
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        ok(f"{rel}: JSON-LD 존재", len(blocks) >= 1, f"{len(blocks)}개")
        for b in blocks:
            try:
                obj = json.loads(b)
            except Exception as exc:  # noqa: BLE001
                fails.append(f"{rel}: JSON-LD 파싱 실패 {exc}")
                continue
            t = obj.get("@type")
            ld_types[t] = ld_types.get(t, 0) + 1
            if t == "BreadcrumbList":
                pos = [it.get("position") for it in obj["itemListElement"]]
                ok(f"{rel}: Breadcrumb 순서", pos == sorted(pos) and all(pos), str(pos))
            if t == "FAQPage":
                ok(f"{rel}: FAQ 항목", len(obj["mainEntity"]) >= 1
                   and all(q["name"].strip() and q["acceptedAnswer"]["text"].strip()
                           for q in obj["mainEntity"]), f"{len(obj['mainEntity'])}문항")
            if t == "ItemList":
                ok(f"{rel}: ItemList 개수", obj["numberOfItems"] == len(obj["itemListElement"]),
                   f"{obj.get('numberOfItems')}")
            if t in ("MedicalProcedure", "WebSite", "Organization"):
                pass
    ok("JSON-LD 유형: FAQPage·BreadcrumbList·ItemList 포함",
       all(k in ld_types for k in ("FAQPage", "BreadcrumbList", "ItemList")), str(ld_types))

    # 내부 링크
    checked = 0
    broken = []
    for p in pages:
        html = p.read_text(encoding="utf-8")
        for href in re.findall(r'href="(/[^"#?]*)"', html):
            if href.startswith(("/assets", "/sitemap", "/robots")):
                continue
            target = dist / href.lstrip("/")
            if href.endswith("/"):
                target = target / "index.html"
            checked += 1
            if not target.exists():
                broken.append((str(p.relative_to(dist)), href))
    ok("내부 링크", not broken, f"검사 {checked}개 · 깨짐 {len(broken)} {broken[:3]}")

    # 항목 페이지 — 카탈로그 개수와 일치해야 한다
    item_pages = sorted((dist / "ko" / "items").glob("*/index.html"))
    catalog = E.load_catalog()
    ok("항목 상세 페이지 = 카탈로그 항목 수", len(item_pages) == len(catalog),
       f"{len(item_pages)}개 / 카탈로그 {len(catalog)}개")
    for it in catalog:
        p = dist / "ko" / "items" / it["slug"] / "index.html"
        if not p.exists():
            fails.append(f"항목 페이지 없음: {it['slug']}")
            continue
        t = p.read_text(encoding="utf-8")
        if it["code"] not in t:
            fails.append(f"{it['slug']}: 코드 {it['code']} 미표기")
        if "5세대" not in t:
            fails.append(f"{it['slug']}: 5세대 처리 설명 없음")
    ok("항목 페이지별 코드·5세대 설명", True, "")

    # ------------------------------------------------ 지역(17개 시·도) 페이지
    print("\n== C2. 지역 페이지 (17개 시·도)")
    region_pages = sorted((dist / "ko" / "regions").glob("*/index.html"))
    ok("지역 상세 페이지 17개", len(region_pages) == 17, f"{len(region_pages)}개")
    ok("지역 허브 페이지", (dist / "ko" / "regions" / "index.html").exists())
    bad_region = []
    for p in region_pages:
        t = p.read_text(encoding="utf-8")
        slug = p.parent.name
        need = ["병원급 이상", "유선 확인", "전국 대비", "시·군·구별 시세", "data-region", "data-hosp-item"]
        miss = [x for x in need if x not in t]
        if miss:
            bad_region.append((slug, miss))
        if "\u0000" in t or "{{{" in t or "None원" in t:
            bad_region.append((slug, ["렌더 오류 의심"]))
    ok("지역 페이지 필수 요소(범위·시군구·전국대비·필터)", not bad_region, str(bad_region[:3]))
    hub = (dist / "ko" / "regions" / "index.html").read_text(encoding="utf-8")
    ok("지역 허브: 17개 시·도 링크",
       sum(1 for s in ["seoul", "busan", "daegu", "incheon", "gwangju", "daejeon", "ulsan",
                       "sejong", "gyeonggi", "gangwon", "chungbuk", "chungnam", "jeonbuk",
                       "jeonnam", "gyeongbuk", "gyeongnam", "jeju"]
           if f'href="/ko/regions/{s}/"' in hub) == 17, "")
    home_nav = (dist / "ko" / "index.html").read_text(encoding="utf-8")
    ok("홈: 지역별 시세 진입 링크", '/ko/regions/' in home_nav and "지역별로 비교하기" in home_nav, "")
    brain_html = (dist / "ko" / "items" / "brain-mri" / "index.html").read_text(encoding="utf-8")
    ok("항목 페이지: 시도 → 지역 페이지 링크", '/ko/regions/seoul/' in brain_html, "")

    # 관리급여 항목 표기
    mt = (dist / "ko" / "items" / "manual-therapy" / "index.html").read_text(encoding="utf-8")
    ok("도수치료: 관리급여 95%·43,850 표기", "관리급여" in mt and "43,850" in mt, "")

    # ---------------------------------------------------------- D. 색인
    print("\n== D. 색인")
    robots = (dist / "robots.txt").read_text(encoding="utf-8")
    preview = 'id="preview-banner"' in landing
    if preview:
        ok("robots: 프리뷰 noindex", "Disallow: /" in robots, robots.strip()[:40])
        ok("랜딩: noindex 메타", "noindex" in landing, "")
    else:
        ok("robots: 색인 허용", "Allow: /" in robots, "")
    sm = ET.fromstring((dist / "sitemap.xml").read_bytes())
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [u.find("sm:loc", ns).text for u in sm.findall("sm:url", ns)]
    ok("sitemap URL 수", len(locs) >= 37, f"{len(locs)}개")
    missing = []
    for loc in locs:
        path = loc.replace(site_base, "").strip("/")
        target = dist / path / "index.html" if path else dist / "index.html"
        if not target.exists():
            missing.append(loc)
    ok("sitemap ↔ 실제 페이지", not missing, str(missing[:3]))
    ok("sitemap 절대 URL", all(l.startswith("https://") for l in locs), "")

    # M-01: 크롤러가 meta-refresh 대신 HTTP 301 을 받도록 Cloudflare Pages _redirects 를 dist 루트에 넣는다.
    if not preview:
        red = dist / "_redirects"
        ok("_redirects: 루트 → /ko/ 301", red.exists() and "/ /ko/ 301" in red.read_text(encoding="utf-8"),
           red.read_text(encoding="utf-8").strip() if red.exists() else "파일 없음")
        root_html = (dist / "index.html").read_text(encoding="utf-8")
        ok("루트 index.html: /ko/ canonical", f'{site_base}/ko/' in root_html, "")

    # M-02: '470,000원로' 는 틀린 조사 — '원' 받침 ㄴ 이므로 항상 '원으로'.
    typo_hits = []
    for p in pages:
        t = p.read_text(encoding="utf-8")
        for pat in ("원로", "원 로", "원</b>로"):
            if pat in t:
                typo_hits.append(f"{p.relative_to(dist)}: {pat}")
    ok("조사 '원으로' 표기(원로·원 로 0건)", not typo_hits, str(typo_hits[:3]))

    # ---------------------------------------------------------- E. 계산 규칙 골든 케이스
    print("\n== E. 계산 규칙 골든 케이스")
    items = catalog

    def g(req, gen):
        # gen 은 세대 번호 또는 (세대, 세부) 튜플 — 2세대는 전기/후기를 행으로 구분한다.
        gen_no, sub = gen if isinstance(gen, tuple) else (gen, None)
        for r in E.compute(req, items)["generations"]:
            if r["gen"] == gen_no and (sub is None or r["sub"] == sub):
                return r
        raise AssertionError(f"행 없음: gen={gen}")

    cases = [
        # (설명, 요청, 세대, 기대 covered, 기대 copay, 기대 status)
        ("뇌MRI 600,000 통원·상급종합(비중증) 1세대", dict(item_code="HE1010001", amount=600000,
                                                     visit="out", institution="tertiary"), 1, 595000, 5000, "covered"),
        # 2세대 통원 600,000원: 외래 1일 한도 25만원이 걸려 모든 유형이 보장 25만·부담 35만원
        ("뇌MRI 600,000 통원·상급 2세대 전기(정액만 + 외래 25만 한도)", dict(item_code="HE1010001", amount=600000,
                                          visit="out", institution="tertiary"), (2, "early"), 250000, 350000, "covered"),
        ("뇌MRI 600,000 통원·상급 2세대 후기 10%형(정액만 + 외래 25만 한도)", dict(item_code="HE1010001", amount=600000,
                                          visit="out", institution="tertiary", gen2_type="late10"),
         (2, "late"), 250000, 350000, "covered"),
        ("뇌MRI 600,000 통원·상급 2세대 표준형(외래 25만 한도)", dict(item_code="HE1010001", amount=600000,
                                          visit="out", institution="tertiary", gen2_type="late20"),
         (2, "late"), 250000, 350000, "covered"),
        # 2세대 통원 250,000원(한도 안): 유형별 공제 공식이 갈린다
        ("뇌MRI 250,000 통원·상급 2세대 전기(정액만)", dict(item_code="HE1010001", amount=250000,
                                          visit="out", institution="tertiary"), (2, "early"), 230000, 20000, "covered"),
        ("뇌MRI 250,000 통원·상급 2세대 후기 10%형(정액만)", dict(item_code="HE1010001", amount=250000,
                                          visit="out", institution="tertiary", gen2_type="late10"),
         (2, "late"), 230000, 20000, "covered"),
        ("뇌MRI 250,000 통원·상급 2세대 표준형(Max 20%)", dict(item_code="HE1010001", amount=250000,
                                          visit="out", institution="tertiary", gen2_type="late20"),
         (2, "late"), 200000, 50000, "covered"),
        ("뇌MRI 250,000 통원·상급 2세대 선택형Ⅱ(비급여 20%)", dict(item_code="HE1010001", amount=250000,
                                          visit="out", institution="tertiary", gen2_type="sel2"),
         (2, "late"), 200000, 50000, "covered"),
        ("뇌MRI 250,000 통원·상급 2세대 모름(하한=정액)", dict(item_code="HE1010001", amount=250000,
                                          visit="out", institution="tertiary", gen2_type="unknown"),
         (2, "late"), 230000, 20000, "covered"),
        # 2세대 입원 600,000원: 통원 한도가 없어 유형별 %가 그대로 갈린다
        ("뇌MRI 600,000 입원·상급 2세대 전기(10%)", dict(item_code="HE1010001", amount=600000,
                                          visit="in", institution="tertiary"), (2, "early"), 540000, 60000, "covered"),
        ("뇌MRI 600,000 입원·상급 2세대 표준형(20%)", dict(item_code="HE1010001", amount=600000,
                                          visit="in", institution="tertiary", gen2_type="late20"),
         (2, "late"), 480000, 120000, "covered"),
        ("뇌MRI 600,000 입원·상급 2세대 선택형Ⅱ(비급여 20%)", dict(item_code="HE1010001", amount=600000,
                                          visit="in", institution="tertiary", gen2_type="sel2"),
         (2, "late"), 480000, 120000, "covered"),
        ("뇌MRI 600,000 통원·상급 3세대(특약 30%)", dict(item_code="HE1010001", amount=600000,
                                                  visit="out", institution="tertiary"), 3, 420000, 180000, "covered"),
        ("뇌MRI 600,000 통원·상급 4세대(회당 20만 한도)", dict(item_code="HE1010001", amount=600000,
                                                    visit="out", institution="tertiary"), 4, 200000, 400000, "covered"),
        ("뇌MRI 600,000 통원·상급 5세대 비중증(50%)", dict(item_code="HE1010001", amount=600000,
                                                    visit="out", institution="tertiary"), 5, 200000, 400000, "covered"),
        ("뇌MRI 600,000 입원·상급 5세대 중증(30%)", dict(item_code="HE1010001", amount=600000,
                                                   visit="in", institution="tertiary", severe=True), 5, 420000, 180000, "covered"),
        ("체외충격파 120,000 통원 5세대 = 보장 제외", dict(item_code="SZ0840000", amount=120000,
                                                   visit="out", institution="hospital"), 5, 0, 120000, "excluded"),
        ("체외충격파 120,000 통원 4세대는 보장", dict(item_code="SZ0840000", amount=120000,
                                                visit="out", institution="hospital"), 4, 84000, 36000, "covered"),
        ("도수치료 1회 통원·상급 1세대", dict(item_code="MX1220000", amount=None, rounds=1,
                                       visit="out", institution="tertiary"), 1, 36658, 5000, "covered"),
        ("도수치료 1회 통원·상급 5세대(건보 95% 연동)", dict(item_code="MX1220000", amount=None, rounds=1,
                                                    visit="out", institution="tertiary"), 5, 2083, 39575, "covered"),
        ("도수치료 1회 통원·의원 2세대 전기(관리급여 정액만)", dict(item_code="MX1220000", amount=None, rounds=1,
                                                     visit="out", institution="clinic", gen2_type="early"),
         (2, "early"), 31658, 10000, "covered"),
        ("도수치료 1회 통원·의원 2세대 표준형(관리급여 20%·외래공제 하한)", dict(item_code="MX1220000", amount=None, rounds=1,
                                                     visit="out", institution="clinic", gen2_type="late20"),
         (2, "late"), 31658, 10000, "covered"),
        # 도수치료 10회 통원·의원: 공제가 방문 1회당이라 전 유형 100,000원(인스팅트 #1283 ①)
        ("도수치료 10회 통원·의원 2세대 전기(관리급여 정액만)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="out", institution="clinic", gen2_type="early"),
         (2, "early"), 316575, 100000, "covered"),
        ("도수치료 10회 통원·의원 2세대 표준형(관리급여 20%)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="out", institution="clinic", gen2_type="late20"),
         (2, "late"), 316575, 100000, "covered"),
        ("도수치료 10회 통원·의원 2세대 선택형Ⅱ(관리급여 10%)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="out", institution="clinic", gen2_type="sel2"),
         (2, "late"), 316575, 100000, "covered"),
        ("도수치료 10회 통원·의원 2세대 모름(하한=정액)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="out", institution="clinic", gen2_type="unknown"),
         (2, "late"), 316575, 100000, "covered"),
        ("도수치료 10회 입원·상급 2세대 전기(관리급여 10%)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="in", institution="tertiary", gen2_type="early"),
         (2, "early"), 374917, 41658, "covered"),
        ("도수치료 10회 입원·상급 2세대 표준형(관리급여 20%)", dict(item_code="MX1220000", amount=None, rounds=10,
                                                     visit="in", institution="tertiary", gen2_type="late20"),
         (2, "late"), 333260, 83315, "covered"),
        ("뇌MRI 1,000,000 입원 상급 5세대 중증·연 500만 상한 초과분", dict(
            item_code="HE1010001", amount=1000000, visit="in", institution="tertiary",
            severe=True, severe_cum=4900000), 5, 900000, 100000, "covered"),
        ("직접입력 0원", dict(item_code="direct", amount=0, visit="out", institution="tertiary"),
         4, 0, 0, "covered"),
        ("2세대 전기 통원 의원 공제 1만(금액 30,000 → 정액 1만만 적용)", dict(
            item_code="EB4410000", amount=30000, visit="out", institution="clinic"), (2, "early"),
         20000, 10000, "covered"),
        ("2세대 표준형 통원 의원 공제 1만(금액 30,000 → 20%=6천 < 1만)", dict(
            item_code="EB4410000", amount=30000, visit="out", institution="clinic", gen2_type="late20"),
         (2, "late"), 20000, 10000, "covered"),
        ("3세대 기본 비급여 통원 의원(20% vs 1만)", dict(item_code="EB4410000", amount=30000,
                                              visit="out", institution="clinic"), 3, 20000, 10000, "covered"),
    ]
    for name, req, gen, cov, cop, st in cases:
        r = g(req, gen)
        ok(name, r["covered"] == cov and r["copay"] == cop and r["status"] == st,
           f"covered {r['covered']}(기대 {cov}) copay {r['copay']}(기대 {cop}) status {r['status']}")
        if r["covered"] + r["copay"] != r["base"]:
            fails.append(f"{name}: 보장액+부담액 != 기준액")

    # 전 항목·전 조합 무결성(빠른 표본)
    bad = 0
    for it in items:
        for amount in (0, 1, 30000, 250000, 1000000):
            for visit in ("out", "in"):
                for inst in E.INSTITUTIONS:
                    for severe in (False, True):
                        res = E.compute({"item_code": it["code"], "amount": amount,
                                         "visit": visit, "institution": inst,
                                         "severe": severe}, items)
                        for r in res["generations"]:
                            if r["covered"] + r["copay"] != r["base"] or min(
                                    r["covered"], r["copay"]) < 0:
                                bad += 1
    ok("무결성: 보장액+부담액=기준액·음수 없음", bad == 0, f"위반 {bad}건")

    # ---------------------------------------------------------- F. 파이프라인
    print("\n== F. 데이터 파이프라인")
    import prepare_data  # noqa: E402
    dataset, quality, summary, hospitals = prepare_data.build(use_fixtures=True)
    ok("prepare_data: 픽스처 정제 실행", summary["counts"]["items_in_catalog"] == len(E.load_catalog()),
       json.dumps(summary["counts"], ensure_ascii=False))
    ok("prepare_data: synthetic 표시", dataset["synthetic"] is True, "")
    ok("prepare_data: 픽스처는 표시용 데이터 아님", all(not i["has_data"] for i in dataset["items"]), "")
    clinic_row = [{"ykiho": "X", "npayCd": "HE1010001", "clCd": "31", "clCdNm": "의원",
                   "sidoCd": "410000", "minPrc": "80000", "maxPrc": "120000"}]
    agg = prepare_data.aggregate(clinic_row, "HE1010001")
    ok("prepare_data: 의원급(clCd 31) 행 제외", agg["n"] == 0 and agg["dropped"]
       and "공개 범위 밖" in agg["dropped"][0]["reason"], str(agg["dropped"]))
    bone = prepare_data.aggregate([{"ykiho": "Y", "npayCd": "HE1010001", "clCd": "01",
                                    "minPrc": "0", "maxPrc": "0"}], "HE1010001")
    ok("prepare_data: 0원/공란 행 제외", bone["n"] == 0, str(bone["dropped"]))
    ok("prepare_data: cmmtTxt 안내 문구 생성",
       all((i["material"] or {}).get("note") for i in dataset["items"]), "")
    ok("prepare_data: cmmtTxt 없으면 '유선 확인' 안내",
       all("유선 확인" in i["material"]["note"] for i in dataset["items"]
           if not (i["material"] or {}).get("raw")), "")
    ok("prepare_data: cmmtTxt 있는 항목은 근거(cmmtTxt) 병기",
       any("cmmtTxt:" in ((i["material"] or {}).get("basis") or "") for i in dataset["items"])
       or not any((i["material"] or {}).get("raw") for i in dataset["items"]), "")
    ok("prepare_data: 종별 통계 정규화", any(i["clcd_stats"] for i in dataset["items"]), "")

    # ---------------------------------------------------------- G. 보안·데이터 경계
    print("\n== G. 보안 · 데이터 경계 (비밀값·제4유형·의원 개별명)")
    key = ""
    env = BASE / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATA_GO_KR_SERVICE_KEY_DEC="):
                key = line.split("=", 1)[1].strip()
    targets = [p for p in dist.rglob("*")
               if p.is_file() and p.suffix.lower() in (".html", ".js", ".css", ".json", ".txt", ".xml")]
    targets += [p for p in (BASE / "data").glob("*.json")]
    targets += [p for p in (BASE / "assets").glob("*") if p.is_file()]
    leak = []
    prefix = key[:4] if len(key) >= 8 else ""
    for p in targets:
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        if (key and key in t) or (prefix and prefix in t) or "serviceKey=" in t:
            leak.append(str(p.relative_to(BASE)))
    ok("인증키 원문·마스킹 접두사 미노출", not leak, str(leak[:3]))

    xlsx = [str(p.relative_to(BASE)) for p in targets
            if ".xlsx" in p.read_text(encoding="utf-8", errors="ignore")
            or "제증명수수료 통계(표)" in p.read_text(encoding="utf-8", errors="ignore")]
    ok("공공누리 제4유형 엑셀 데이터 미사용", not xlsx, str(xlsx[:3]))

    hs_path = BASE / "data" / "hospitals.json"
    if hs_path.exists():
        hs = json.loads(hs_path.read_text(encoding="utf-8"))
        kinds = set()
        bad = []
        for code, rows in hs.get("items", {}).items():
            for r in rows:
                kinds.add(r[1])
                if "의원" in str(r[1]):
                    bad.append((code, r[0], r[1]))
        ok("기관 목록: 의원·치과의원·한의원 개별 기관 0건", not bad, str(bad[:3]))
        ok("기관 목록: 병원급 종별만 포함", kinds <= {"상급종합", "종합병원", "병원",
                                                       "요양병원", "정신병원", "치과병원", "한방병원"},
           str(sorted(kinds)))
        ok("기관 목록: 전수 보유", sum(len(v) for v in hs.get("items", {}).values()) >= 13650,
           str(sum(len(v) for v in hs.get("items", {}).values())))
    else:
        ok("기관 목록 파일 존재", False, "data/hospitals.json 없음")

    ds_live = json.loads((BASE / "data" / "hira_dataset.json").read_text(encoding="utf-8"))
    if not ds_live.get("synthetic"):
        ok("라이브 데이터셋: synthetic=false", ds_live.get("synthetic") is False, "")
        ok("라이브 데이터셋: 전 항목 전수 수집(coverage 100%)",
           all((i.get("coverage") or {}).get("complete") for i in ds_live["items"]),
           str([(i["code"], i.get("coverage")) for i in ds_live["items"]
                if not (i.get("coverage") or {}).get("complete")][:2]))
        ok("라이브 데이터셋: KOSIS 의원급 값 전 항목",
           sum(1 for i in ds_live["items"] if i.get("kosis")) == len(ds_live["items"]),
           str(sum(1 for i in ds_live["items"] if i.get("kosis"))))
        brain = (dist / "ko" / "items" / "brain-mri" / "index.html").read_text(encoding="utf-8")
        ok("항목 페이지: KOSIS 출처·의원급 평균 표시",
           "KOSIS" in brain and "379,927" in brain and "354006" in brain, "")
        ok("항목 페이지: 전수 수집 표기", "전수 수집" in brain and "932/932" in brain, "")
        ok("항목 페이지: 기관별 필터 존재", "data-hosp" in brain and "hospitals.json" not in brain, "")
        mt_html = (dist / "ko" / "items" / "manual-therapy" / "index.html").read_text(encoding="utf-8")
        ok("도수치료: 관리급여 전환 고지 최상단", "2026년 7월 1일부터 도수치료는 관리급여" in mt_html, "")
        ok("도수치료: 43,850·95%·공개자료 시점 차이 고지",
           "43,850" in mt_html and "95%" in mt_html and "비급여 공개자료 기준" in mt_html, "")
        landed = (dist / "ko" / "index.html").read_text(encoding="utf-8")
        ok("홈: 병원급↔의원급 비교표", "data-compare-table" in landed and "379,927" in landed, "")
        ok("개인정보처리방침 페이지", (dist / "ko" / "privacy" / "index.html").exists()
           and "공공누리 제1유형" in (dist / "ko" / "privacy" / "index.html").read_text(encoding="utf-8"),
           "")
        ok("404 페이지", (dist / "404.html").exists(), "")

    # ---------------------------------------------------------- H. 브랜딩 · 애드센스 기반
    print("\n== H. 브랜딩 · 애드센스 기반")
    ads = dist / "ads.txt"
    ok("ads.txt 존재", ads.exists(), "")
    if ads.exists():
        ok("ads.txt 게시자 ID",
           ads.read_text(encoding="utf-8").strip()
           == "google.com, pub-9496998678693709, DIRECT, f08c47fec0942fa0",
           ads.read_text(encoding="utf-8").strip())
    for asset in ("favicon.svg", "favicon.ico"):
        ok(f"assets/{asset}", (dist / "assets" / asset).exists(), "")
    for slug, must in (("about", "사이트 소개"),
                       ("editorial-policy", "편집·데이터 정책"),
                       ("medical-disclaimer", "의료 면책 고지"),
                       ("contact", "문의 및 오류 제보")):
        f = dist / "ko" / slug / "index.html"
        ok(f"/ko/{slug}/ 페이지", f.exists(), "")
        if f.exists():
            t = f.read_text(encoding="utf-8")
            ok(f"/ko/{slug}/ 제목·내용", must in t, "")
            ok(f"/ko/{slug}/ canonical", f"medical-finder-kr.pages.dev/ko/{slug}/" in t
               if site_base.endswith("medical-finder-kr.pages.dev") else "/ko/" in t, "")
    contact = (dist / "ko" / "contact" / "index.html").read_text(encoding="utf-8")
    ok("contact: 구글 폼 연결", "docs.google.com/forms/d/e/1FAIpQLSe-mSKsokTH" in contact, "")
    ok("contact: 응답 기한 안내", "5일 이내" in contact, "")
    ok("contact: 예약·진료 상담 불가 안내", "예약·진료 상담" in contact or "예약" in contact, "")
    brand_pages = 0
    for p_ in pages:
        t = p_.read_text(encoding="utf-8")
        if p_.name != "index.html" or p_.parent == dist:
            continue
        if "K-MediCheck" in t:
            brand_pages += 1
        else:
            fails.append(f"{p_.relative_to(dist)}: K-MediCheck 브랜드 표기 없음")
    ok("브랜드 표기(K-MediCheck) 전 페이지", brand_pages >= len(main_pages) - 1, f"{brand_pages}페이지")
    iframes = [(p_.relative_to(dist).as_posix()) for p_ in pages
               if "<iframe" in p_.read_text(encoding="utf-8")]
    ok("iframe은 문의 페이지에만", all(x.startswith("ko/contact/") for x in iframes), str(iframes))

    # ---------------------------------------------------------- I. 정적 자산 캐시 버스팅
    print("\n== I. 정적 자산 캐시 버스팅 (?v=<hash8>)")
    import hashlib as _hashlib
    vers = {n: _hashlib.sha256((dist / "assets" / n).read_bytes()).hexdigest()[:8]
            for n in ("style.css", "calc.js", "app.js", "switch-gen5.js")}
    n_bust = 0
    stale = []
    no_v = []
    for p_ in pages:
        html = p_.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:href|src)="([^"]*?/assets/(style\.css|calc\.js|app\.js|switch-gen5\.js))'
                             r'(?:\?v=([0-9a-f]{8}))?"', html):
            name, got = m.group(2), m.group(3)
            if not got:
                no_v.append(f"{p_.relative_to(dist)}:{name}")
                continue
            n_bust += 1
            if got != vers[name]:
                stale.append(f"{p_.relative_to(dist)}:{name}?v={got} (실제 {vers[name]})")
    ok("모든 HTML의 CSS·JS에 ?v=<hash8> 부착", not no_v, f"부착 {n_bust}건 / 누락 {no_v[:3]}")
    ok("붙은 해시 = 배포 파일 실제 해시", not stale, str(stale[:3]))
    ok("404·루트 랜딩도 버전 쿼리 일관",
       all(f"style.css?v={vers['style.css']}" in (dist / n).read_text(encoding="utf-8")
           for n in ("404.html",)) and vers["style.css"] in (dist / "404.html").read_text(encoding="utf-8"),
       vers["style.css"])

    # ---------------------------------------------------------- J. 가이드 8편 (T-M12 5 + T-M12-B 3)
    print("\n== J. 가이드 8편 (T-M12 5편 + T-M12-B 3편)")
    try:
        import guides as G  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        ok("guides 모듈 로드", False, str(exc))
        G = None
    if G:
        hub_guide = (dist / "ko" / "guide" / "index.html").read_text(encoding="utf-8")
        slugs = [g["slug"] for g in G.GUIDES]
        ok("가이드 8편 정의", len(slugs) == 8, f"{len(slugs)}편")
        guide_pages = {s: dist / "ko" / "guide" / s / "index.html" for s in slugs}
        ok("가이드 상세 8페이지 생성", all(p.exists() for p in guide_pages.values()),
           str([s for s, p in guide_pages.items() if not p.exists()]))
        ok("가이드 허브: 8편 링크", all(f'href="/ko/guide/{s}/"' in hub_guide
                                   for s in slugs),
           "")
        draft_marks, bad_jsonld, missing_x, no_link = [], [], [], []
        for g, (slug, p) in zip(G.GUIDES, guide_pages.items()):
            t = p.read_text(encoding="utf-8")
            for mark in ("(추정", "추정)", "(확인 필요", "확인 필요)"):
                if mark in t:
                    draft_marks.append(f"{slug}: {mark}")
            blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S)
            types = set()
            for b in blocks:
                try:
                    types.add(json.loads(b).get("@type"))
                except Exception:  # noqa: BLE001
                    bad_jsonld.append(f"{slug}: 파싱 실패")
            if not {"Article", "FAQPage", "BreadcrumbList"} <= types:
                bad_jsonld.append(f"{slug}: JSON-LD {sorted(types)}")
            # 목차 앵커 대상 존재
            for anchor in re.findall(r'href="#(s\d+)"', t):
                if f'id="{anchor}"' not in t:
                    missing_x.append(f"{slug}: #{anchor}")
            # 상호 교차링크(다른 7편) + 기존 섹션 내부링크 2개 이상
            others = [o for o in slugs if o != slug]
            if not all(f'href="/ko/guide/{o}/"' in t for o in others):
                no_link.append(f"{slug}: 교차링크 누락")
            secs = sum(1 for x in ("/ko/calc/", "/ko/insurance/", "/ko/items/", "/ko/regions/")
                       if f'href="{x}' in t)
            if secs < 2:
                no_link.append(f"{slug}: 기존 섹션 내부링크 {secs}개")
            # 가드레일
            for bad in ("adsbygoogle", "ca-pub-", "9welfare.com", "예약 문의", "상담 신청"):
                if bad in t:
                    fails.append(f"{slug}: 금지 요소 '{bad}'")
            ext = set(re.findall(r'href="(https?://[^"]+)"', t))
            ext = {u for u in ext if "medical-finder-kr.pages.dev" not in u and "schema.org" not in u
                   and "kmedicheck.com" not in u}
            if ext:
                fails.append(f"{slug}: 외부 링크 {sorted(ext)[:3]}")
        ok("가이드: 초안 표시((추정)·확인 필요) 0건", not draft_marks, str(draft_marks[:4]))
        ok("가이드: JSON-LD Article·FAQPage·Breadcrumb", not bad_jsonld, str(bad_jsonld[:4]))
        ok("가이드: 목차 앵커 대상 존재", not missing_x, str(missing_x[:4]))
        ok("가이드: 상호 교차링크 7편 + 기존 섹션 2개 이상", not no_link, str(no_link[:4]))

        # 14차 검수 보정 문구 반영 확인
        def gtext(s: str) -> str:
            return guide_pages[s].read_text(encoding="utf-8")
        need = {
            "mri-ultrasound-covered-vs-noncovered": [
                "시행령 [별표 2]", "제2023-134호", "제2023-293호", "선별급여", "80%",
                "2018년 4월", "2019년 2월", "산정특례", "본인일부부담금 산정특례에 관한 기준"],
            "dental-implant-crown-silson": [
                "제2025-23호", "지르코니아 크라운", "부분무치악", "평생 2개", "본인부담상한제",
                "1,351,040", "405,100", "100원 미만", "40,500", "174,200", "190,400"],
            "managed-benefit-95-calculator-guide": [
                "43,850", "95%", "주 2회", "15회", "24회"],
            "shockwave-prolotherapy-gen5-exclusion": [
                "43,850", "95%", "주 2회", "24회", "특약2"],
        }
        for slug, needles in need.items():
            t = gtext(slug)
            miss = [n for n in needles if n not in t]
            ok(f"보정 문구 반영: {slug[:26]}", not miss, str(miss))
        # 산정특례 5%는 시행령 별표2가 아니라 고시·공단 안내로 표기
        mri_t = gtext("mri-ultrasound-covered-vs-noncovered")
        ok("산정특례 5% 근거 표기(고시·NHIS)",
           "산정특례에 관한 기준" in mri_t and "국민건강보험공단" in mri_t, "")
        # 임플란트 본인부담 절사는 '단계별 30% 산출 후 100원 미만 절사'
        den = gtext("dental-implant-crown-silson")
        ok("임플란트 본인부담 절사 기준(100원 미만)",
           "100원 미만" in den and "10원 미만" not in den, "")


    # ---------------------------------------------------------- K. T-M13 5세대 전환 손익 시뮬레이터
    print("\n== K. T-M13 5세대 전환 손익 시뮬레이터")
    sim_f = dist / "ko" / "switch-gen5" / "index.html"
    ok("/ko/switch-gen5/ 페이지", sim_f.exists(), "")
    if sim_f.exists():
        sim = sim_f.read_text(encoding="utf-8")
        calc_f = dist / "ko" / "calc" / "index.html"
        calc_h = calc_f.read_text(encoding="utf-8") if calc_f.exists() else ""
        ok("시뮬레이터 canonical", f'<link rel="canonical" href="{site_base}/ko/switch-gen5/">' in sim, "")
        # OG 이미지
        ok("OG 이미지 메타(1200×630·twitter)", all(x in sim for x in (
            f'property="og:image" content="{site_base}/assets/og-switch-gen5.png"',
            'property="og:image:width" content="1200"',
            'property="og:image:height" content="630"',
            'name="twitter:card" content="summary_large_image"')), "")
        png = dist / "assets" / "og-switch-gen5.png"
        ok("OG 이미지 파일", png.exists(), "")
        if png.exists():
            import struct as _struct
            head = png.read_bytes()[:24]
            w, h = _struct.unpack(">II", head[16:24])
            ok("OG 이미지 실제 크기 1200×630 PNG", head[:8] == b"\x89PNG\r\n\x1a\n" and (w, h) == (1200, 630),
               f"{w}×{h}")
            ok("OG 이미지 용량(200KB 이하)", png.stat().st_size < 200 * 1024, f"{png.stat().st_size:,}B")
        js = (dist / "assets" / "switch-gen5.js")
        ok("시뮬레이터 JS 로드", js.exists() and "/assets/switch-gen5.js" in sim, "")
        jst = js.read_text(encoding="utf-8") if js.exists() else ""
        # UTM 규격
        utm_need = ["utm_source=", "kakaotalk", "og_share", "link_copy", "utm_medium=share_card",
                    "utm_campaign=gen5-simulator", "result-save", "result-loss", "result-hold"]
        ok("UTM 규격(§7) 반영", all(n in jst for n in utm_need),
           str([n for n in utm_need if n not in jst]))
        # 공유 장치
        ok("공유 장치(카드 PNG·Web Share·링크 복사)",
           all(n in jst for n in ("toDataURL", "navigator.share", "clipboard", "drawCard")), "")
        ok("결과 카드에 개인정보 없음(보험료·이름 미포함)",
           all(x not in jst[jst.index("function drawCard"):jst.index("function wrapText")] for x in
               ("pcur", "p5", "'이름'", "생년")))
        ok("차트 SVG 렌더(손익분기 곡선)", "sim-chart-svg" in jst and "polyline" not in jst, "")
        # 입력·계산 화면 요소
        for needle, name in (('data-sim', "시뮬레이터 폼"),
                             ('data-seg="gen"', "세대 선택"),
                             ('id="pcur-unknown"', "'모름' 선택"),
                             ('id="gen1-row"', "1세대 자기부담률 입력"),
                             ('data-range="mild"', "비중증 슬라이더"),
                             ('id="managed"', "관리급여 체크"),
                             ('data-share="card"', "카드 저장 버튼"),
                             ('data-share="copy"', "링크 복사 버튼"),
                             ('id="sim-out"', "결과 영역")):
            ok(f"시뮬레이터 화면: {name}", needle in sim, "")
        # 필수 고지 문구
        must = ["참고용 추정치", "1332", "2028년 5월", "할증", "관리급여", "43,850",
                "철회", "5년마다 재가입", "판단 보류", "손익분기", "2026-16호",
                "2028년 5월 이후 갱신분부터", "준비 중입니다", "면책 옵션"]
        ok("고지 문구(1332·2028-05·할증·관리급여·철회)", all(m in sim for m in must),
           str([m for m in must if m not in sim]))
        ok("할증 고정 문구(JS 결과 고지까지 포함)",
           "할증률은 보험사·상품별로 다릅니다" in (sim + jst) and "최대 3배" not in sim + jst, "")
        # 금지·초안 표기
        bad_marks = [m for m in ("(추정", "추정)", "(확인 필요", "확인 필요)", "무조건 전환", "무조건 유지",
                                 "보장됩니다", "adsbygoogle", "ca-pub-", "pagead2") if m in sim]
        ok("금지·초안 표기 0건", not bad_marks, str(bad_marks))
        bad_js = [m for m in ("(추정", "추정)", "확인 필요", "무조건 전환", "무조건 유지",
                              "adsbygoogle", "ca-pub-", "pagead2") if m in jst]
        ok("JS 금지·초안 표기 0건", not bad_js, str(bad_js))
        # 개인정보 입력란 없음
        pii = [m for m in ("name", "jumin", "rrn", "birth", "gender", "job", "insurer", "phone",
                           "email", "주민번호", "생년월일", "보험사명")
               if re.search(r'<(?:input|select|textarea)[^>]*(?:id|name)="[^"]*' + m, sim)]
        ok("개인정보 입력란 없음(이름·주민번호·연령·직업·보험사)", not pii, str(pii))
        ok("텍스트 입력은 복사용 readonly 만", len(re.findall(r'<input[^>]*type="text"', sim)) == 1
           and 'id="sim-link"' in sim, "")
        # 내부링크
        ok("계산기 결과 하단 → 시뮬레이터 링크", 'href="/ko/switch-gen5/"' in calc_h, "")
        ok("시뮬레이터 → 계산기·가이드 링크",
           'href="/ko/calc/"' in sim and 'href="/ko/guide/' in sim, "")
        gdir = dist / "ko" / "guide"
        linked = [g for g in ("silson-1-5-generation-guide", "managed-benefit-95-calculator-guide",
                              "shockwave-prolotherapy-gen5-exclusion")
                  if (gdir / g / "index.html").exists()
                  and 'href="/ko/switch-gen5/"' in (gdir / g / "index.html").read_text(encoding="utf-8")]
        ok("관련 가이드 3편 → 시뮬레이터 내부링크", len(linked) == 3, str(linked))
        # sitemap
        sm = (dist / "sitemap.xml").read_text(encoding="utf-8")
        ok("sitemap: /ko/switch-gen5/ 포함", "<loc>" + site_base + "/ko/switch-gen5/</loc>" in sm, "")
        # JSON-LD
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', sim, re.S)
        types = set()
        for b in blocks:
            try:
                types.add(json.loads(b).get("@type"))
            except Exception:  # noqa: BLE001
                types.add("PARSE_FAIL")
        ok("시뮬레이터 JSON-LD(WebApplication·FAQPage·Breadcrumb)",
           {"WebApplication", "FAQPage", "BreadcrumbList"} <= types, str(sorted(types)))
        ok("JSON-LD 초안 표기 없음", "PARSE_FAIL" not in types and "(추정" not in sim, "")

    # 계산 엔진 골든 케이스(손으로 검산)
    print("\n== K-2. 시뮬레이터 계산 골든 케이스")
    try:
        import switch_engine as S  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        S = None
        ok("switch_engine 로드", False, str(exc))
    if S:
        g1 = S.compute({"gen": 4, "pcur": 32000, "mild": 1200000, "in_cov": 800000})
        ok("4세대·월 3.2만·비중증 120만 → 연 124,800원 손해",
           (g1["delta"], g1["verdict"], g1["p5"], g1["break_even"]) == (-124800, "loss", 22400, 576000),
           str({k: g1[k] for k in ("delta", "verdict", "p5", "break_even")}))
        g2 = S.compute({"gen": 2, "pcur": 24000, "out_cov": 300000, "out_visits": 6})
        ok("2세대 통원 6회 → 연 144,000원 절약(최소공제 동일)",
           (g2["delta"], g2["oop_cur"], g2["oop5"]) == (144000, 60000, 60000),
           str({k: g2[k] for k in ("delta", "oop_cur", "oop5")}))
        g2e = S.compute({"gen": 2, "pcur": 24000, "out_cov": 1200000, "out_visits": 6,
                         "gen2_type": "early"})
        ok("2세대 전기(10%) 통원 6회 → 부담 120,000원·Δ 24,000원(보류)",
           (g2e["oop_cur"], g2e["delta"], g2e["verdict"]) == (120000, 24000, "hold"),
           str({k: g2e[k] for k in ("delta", "oop_cur", "verdict")}))
        g2l = S.compute({"gen": 2, "pcur": 24000, "out_cov": 1200000, "out_visits": 6,
                         "gen2_type": "late20"})
        ok("2세대 후기 20%형 통원 6회 → 부담 240,000원·Δ 144,000원(절약)",
           (g2l["oop_cur"], g2l["delta"], g2l["verdict"]) == (240000, 144000, "save"),
           str({k: g2l[k] for k in ("delta", "oop_cur", "verdict")}))
        g2s = S.compute({"gen": 2, "pcur": 24000, "out_cov": 1200000, "out_visits": 6,
                         "gen2_type": "sel2"})
        ok("2세대 선택형Ⅱ 통원 6회 → 급여 10%라 전기와 같은 부담 120,000원·Δ 24,000원(보류)",
           (g2s["oop_cur"], g2s["delta"], g2s["verdict"]) == (120000, 24000, "hold"),
           str({k: g2s[k] for k in ("delta", "oop_cur", "verdict")}))
        ok("1세대 자기부담률 미입력 → 계산 보류", S.compute({"gen": 1, "pcur": 24000})["hold"] == "gen1_rate", "")
        g3 = S.compute({"gen": 1, "pcur": 24000, "gen1_rate": 20, "mild": 600000})
        ok("1세대 20%·비중증 60만 → 판단 보류(|Δ|≤5만)", (g3["delta"], g3["verdict"]) == (-36000, "hold"),
           str(g3["delta"]))
        ok("5세대 선택 → 이미 5세대 안내", S.compute({"gen": 5, "pcur": 32000})["hold"] == "already_gen5", "")
        ok("월 보험료 0/미입력 → 계산 보류",
           S.compute({"gen": 4, "pcur": 0})["hold"] == "premium_unknown", "")
        g4 = S.compute({"gen": 4, "pcur": 32000, "mild": 30000000})
        ok("5세대 비중증 연 1,000만원 보장한도 적용", g4["oop5"] == 20000000,
           f"oop5={g4['oop5']:,}")
        g5 = S.compute({"gen": 3, "pcur": 48000, "severe": 5000000, "out_cov": 400000,
                        "out_visits": 4, "inst": "tertiary"})
        ok("중증 5,000만·통원 4회(상급종합 2만 공제)",
           (g5["oop_cur"], g5["oop5"]) == (1080000, 1580000),
           f"{g5['oop_cur']:,}/{g5['oop5']:,}")
        ok("보험료 자동 추정 세대별 분리(4세대 30%·1세대 50%)",
           S.compute({"gen": 4, "pcur": 40000})["p5"] == 28000
           and S.compute({"gen": 1, "pcur": 40000, "gen1_rate": 20})["p5"] == 20000, "")
        ok("손익분기 곡선 200점 생성", len(g1["chart"]["points"]) == 201,
           str(len(g1["chart"]["points"])))

    # ---------------------------------------------------------- 결과
    print()
    if warns:
        print(f"경고 {len(warns)}건")
        for w in warns[:10]:
            print("  !", w)
    if fails:
        print(f"실패 {len(fails)}건")
        for f in fails[:20]:
            print("  -", f)
        return 1
    print("모두 통과: 범위 고지 · 픽스처 격리 · 구조 · 색인 · 계산 규칙 · 파이프라인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
