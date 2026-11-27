#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P0 파일럿 빌더 — 도수치료(manual-therapy) 상세 페이지에 계산 블록 내장 + 결과 재구성

병원비 기획안 v2 P0-2(항목 상세에 계산 블록 내장)·P0-3(결과 중심을 '내 최종 부담'으로)의
파일럿이다. 전체 34개 항목이 아니라 도수치료 1개 페이지만 대상으로 한다.

방식 (기존 파일 무수정):
  · 계산 블록 HTML 은 scripts/build_site.py 의 calc_block() 을 그대로 호출해 만든다.
  · 계산 로직은 기존 assets/calc.js + assets/app.js 를 그대로 쓴다(페이지 공통 로드).
  · '내 세대' 선택·큰 숫자 히어로·시세 위치 줄은 파일럿 전용
    assets/pilot-calc.js · assets/pilot-calc.css 가 표시만 얹는다.
  · 이미 빌드된 dist/ko/items/manual-therapy/index.html 에만 주입한다.
    원본은 /tmp/pilot-manual-therapy-backup.html 로 백업한다.
  · 프리셋은 기존 딥링크 규칙(?item=&amount=)을 인라인 스크립트로 재사용한다
    (app.js 가 init 시 location.search 를 읽는 동작을 그대로 활용).

사용법: python3 scripts/pilot_manual_therapy.py
  - dist 가 다시 빌드되면 파일럿은 사라지므로, 화면 확인 전에는 이 스크립트를 다시 실행한다.
  - 이미 주입된 페이지에는 다시 주입하지 않는다(마커 검사).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_site as bs  # noqa: E402

PILOT_CODE = "MX1220000"          # 도수치료
PILOT_SLUG = "manual-therapy"
PAGE = BASE / "dist" / "ko" / "items" / PILOT_SLUG / "index.html"
BACKUP = Path("/tmp/pilot-manual-therapy-backup.html")

GEN_FIELD = """
    <div class="field">
      <span class="label" id="pilot-gen-label">내 실손 세대 <span class="hint">(모르면 '모름' — 아래 표에서 세대별로 비교)</span></span>
      <div class="seg pilot-gen" id="pilot-gen-group" role="group" aria-labelledby="pilot-gen-label">
        <button type="button" data-mygen="0" aria-pressed="true">모름</button>
        <button type="button" data-mygen="1" aria-pressed="false">1세대</button>
        <button type="button" data-mygen="2" aria-pressed="false">2세대</button>
        <button type="button" data-mygen="3" aria-pressed="false">3세대</button>
        <button type="button" data-mygen="4" aria-pressed="false">4세대</button>
        <button type="button" data-mygen="5" aria-pressed="false">5세대</button>
      </div>
      <div class="row-note">세대를 고르면 결과 맨 위에 내 최종 부담이 크게 표시됩니다.</div>
    </div>
"""

HERO = """
    <div class="pilot-hero" id="pilot-hero">
      <div class="pilot-hero-lbl" id="pilot-hero-lbl">내 최종 부담</div>
      <div class="pilot-hero-num pilot-hero-num--guide" id="pilot-hero-num">세대를 고르면 크게 표시됩니다</div>
      <div class="pilot-hero-sub" id="pilot-hero-sub">내 실손 세대를 모르면 아래 비교표에서 세대별로 확인하세요.</div>
      <p class="pilot-hero-market" id="pilot-hero-market"></p>
    </div>
"""


COMPARE = """
    <details class="pilot-compare" id="pilot-compare">
      <summary>다른 세대와 비교</summary>
      <div class="pilot-compare-wrap">
        <table class="pilot-compare-table">
          <thead><tr><th scope="col">세대</th><th scope="col">예상 보장액</th><th scope="col">환자 최종 부담</th></tr></thead>
          <tbody id="pilot-compare-body">
            <tr><td colspan="3">계산 결과를 불러오는 중…</td></tr>
          </tbody>
        </table>
      </div>
    </details>
"""

CLAIM = """
    <div class="pilot-claim" id="pilot-claim">
      <h3>청구할 때 준비할 것</h3>
      <ul>
        <li>기본 서류: 진료비 영수증·진료비 세부내역서. 입원·수술이 있으면 진단서도 준비하세요.</li>
        <li>청구 소멸시효: 진료일로부터 3년 안에 청구하세요. 3년이 지나면 못 받을 수 있어요.</li>
        <li>실제 지급액은 가입 약관·자기부담금 누적·청구 이력에 따라 달라집니다.</li>
      </ul>
    </div>
"""

ITEM_LINE = """
      <p class="pilot-item-line">항목: <b>도수치료</b> · 1회 43,850원 · 관리급여(선별급여, 2026.7.1부터) — 금액은 횟수로 바뀝니다.</p>
"""


def pilot_block(items: list[dict], stats: dict) -> str:
    """calc_block() 산출물에 파일럿 요소(세대 선택·히어로)를 끼워 넣는다."""
    block = bs.calc_block(
        items, PILOT_CODE,
        heading="도수치료 — 내 최종 부담 계산",
        sub="시세를 본 그 자리에서, 내 실손 세대의 최종 부담을 바로 계산합니다. 항목·금액은 바꿀 수 있습니다.")
    block = block.replace(
        '<section class="calc" data-calc aria-labelledby="calc-title">',
        '<section class="calc" data-calc data-pilot-calc id="pilot-calc" aria-labelledby="calc-title">', 1)
    # 항목이 프리셋이므로 항목 선택 드롭다운은 숨기고 한 줄 요약으로 대체한다
    # (밀크 #1164 ① 권고 — 블록 높이를 낮춘다. select 자체는 DOM에 남아 app.js가 쓴다).
    anchor0 = '<div class="calc-body">'
    assert block.count(anchor0) == 1, "calc-body 앵커를 찾지 못했습니다"
    block = block.replace(anchor0, anchor0 + ITEM_LINE, 1)
    anchor0b = '<div class="field">\n      <label for="item-select">'
    assert block.count(anchor0b) == 1, "항목 선택 필드 앵커를 찾지 못했습니다"
    block = block.replace(anchor0b, '<div class="field" id="pilot-item-field">\n      <label for="item-select">', 1)
    anchor = '<div class="field" id="rounds-row"'
    assert block.count(anchor) == 1, "rounds-row 앵커를 찾지 못했습니다"
    block = block.replace(anchor, GEN_FIELD + "    " + anchor, 1)
    anchor2 = '<div id="result-summary"></div>'
    assert block.count(anchor2) == 1, "result-summary 앵커를 찾지 못했습니다"
    block = block.replace(anchor2, HERO + "    " + COMPARE + "    " + anchor2, 1)
    # 청구 서류·기한 안내 (부이 #1150 배포 전 확인) — 계산 기준 details 뒤에 붙인다.
    anchor3 = "    </details>\n  </div>\n</section>"
    assert block.count(anchor3) == 1, "calc 블록 끝 앵커를 찾지 못했습니다"
    block = block.replace(anchor3, "    </details>" + CLAIM + "  </div>\n</section>", 1)
    return block


def main() -> None:
    if not PAGE.exists():
        sys.exit(f"대상 페이지가 없습니다: {PAGE} (먼저 build_site.py 로 빌드하세요)")
    page = PAGE.read_text(encoding="utf-8")
    if "data-pilot-calc" in page:
        sys.exit("이미 파일럿이 주입된 페이지입니다. 다시 하려면 dist 를 재빌드한 뒤 실행하세요.")

    items = json.loads((BASE / "data" / "catalog_items.json").read_text(encoding="utf-8"))["items"]
    ds = json.loads((BASE / "data" / "hira_dataset.json").read_text(encoding="utf-8"))
    bs.DATASET = ds
    entry = next(i for i in ds["items"] if i["code"] == PILOT_CODE)
    price = entry["stats"]["price"]
    stats = {"code": PILOT_CODE, "n": entry["stats"]["n"],
             "avg": price["avg"], "median": price["median"],
             "min": price["min"], "max": price["max"], "mode": price["mode"],
             "managed": entry.get("payment") == "관리급여"}

    block = pilot_block(items, stats)

    # 1) 파일럿 CSS 링크
    assert page.count("</head>") == 1
    page = page.replace("</head>",
                        '<link rel="stylesheet" href="/assets/pilot-calc.css">\n</head>', 1)

    # 2) 기존 '계산하기' 링크 버튼 → 페이지 내 앵커로 (파일럿 페이지 한정)
    old_btn = (f'<a class="btn sm" href="/ko/calc/?item={PILOT_CODE}&amount=43850">'
               '이 항목으로 계산하기</a>')
    if old_btn in page:
        page = page.replace(old_btn,
                            '<a class="btn sm" href="#pilot-calc">이 페이지에서 바로 계산하기</a>', 1)
        page = page.replace(
            "링크를 누르면 금액이 <b>43,850원</b>으로 채워집니다. 실제 청구 금액으로 바꿔 계산하세요.",
            "아래 계산기에 금액이 <b>43,850원</b>으로 채워져 있습니다. 실제 청구 금액으로 바꿔 계산하세요.", 1)
    else:
        print("주의: 기존 계산 링크 버튼 문구를 찾지 못해 버튼 교체는 건너뜁니다", file=sys.stderr)

    # 3) 계산 블록을 가격 헤드라인 바로 아래(시세 카드 안)에 주입 — 부이 #1192 ①.
    #    헤드라인과 첫 표 사이에는 수집 범위 안내(.data-coverage, ~71px)와
    #    시세 KPI 요약(.kpi-row, ~160px)이 있어 291px이 벌어졌었다.
    #    계산 블록을 헤드라인 직후로 당기면 간격이 사라지고, KPI 요약은
    #    계산 블록 아래·첫 표 위에 그대로 남는다.
    h3 = '<h3>심평원 병원급 공개가 시세</h3>'
    h3_idx = page.find(h3)
    assert h3_idx >= 0, "시세 헤드라인을 찾지 못했습니다"
    h3_end = h3_idx + len(h3)
    page = page[:h3_end] + "\n  " + block + page[h3_end:]

    # 4) 프리셋 + 시세 통계 + 파일럿 JS 를 </body> 앞에
    preset = f"""
<script>
/* 파일럿 프리셋: 내장 계산기를 이 항목으로 맞춘다(기존 딥링크 규칙 재사용). */
(function () {{
  try {{
    var q = new URLSearchParams(location.search);
    if (!q.get('item')) {{
      q.set('item', '{PILOT_CODE}');
      q.set('amount', '43850');
      history.replaceState(null, '', location.pathname + '?' + q.toString() + location.hash);
    }}
  }} catch (e) {{ /* 무시 */ }}
}})();
</script>
<script>window.PILOT_STATS={json.dumps(stats, ensure_ascii=False)};</script>
<script src="/assets/pilot-calc.js" defer></script>
"""
    assert page.count("</body>") == 1
    page = page.replace("</body>", preset + "</body>", 1)

    # 5) 자산 복사 + 백업 + 기록
    for name in ("pilot-calc.css", "pilot-calc.js"):
        shutil.copyfile(BASE / "assets" / name, BASE / "dist" / "assets" / name)
    if not BACKUP.exists():
        shutil.copyfile(PAGE, BACKUP)
    PAGE.write_text(page, encoding="utf-8")
    print(f"파일럿 주입 완료: {PAGE}")
    print(f"  시세 통계: 중간값 {stats['median']:,}원 · 최저 {stats['min']:,}원 · 최고 {stats['max']:,}원 · n={stats['n']:,}")
    print(f"  원본 백업: {BACKUP}")


if __name__ == "__main__":
    main()
