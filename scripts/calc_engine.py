#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1~5세대 실손의료보험 + 도수치료 관리급여(본인부담 95%) 계산 엔진 (Python 기준 구현)

이 파일이 계산 규칙의 '기준(canonical)'이고, assets/calc.js 가 같은 규칙을
바닐라 JS 로 옮긴 구현이다. 두 구현이 같은 값을 내는지는
scripts/crosscheck_calc.py 가 수천 건 조합으로 전수 검증한다.

근거
  · 금융위원회 2026-05-06 보도자료 — 5세대 실손의료보험 출시(중증 비급여 특약1 / 비중증 비급여 특약2)
  · 금융위원회 2026-01-15 보도자료 — 5세대 상품설계기준(4세대 대비 신구조 비교표)
  · 보건복지부 2026-07-01 보도자료 · 심평원 고시 2026-134~137호 — 도수치료 관리급여 전환
    (1회 43,850원, 종별가산 없음, 본인부담률 95%, 주 2회·연 15회 / 예외 24회)

표준형·선택형 등 상품별 약관 차이는 계산에 반영하지 않고 '안내'로만 표시한다.
(예: 2세대 통원 회당 한도, 3세대 비급여 연간 한도, 5세대 연간 보장한도)

2세대는 가입 시기·상품으로 유형을 나눠 계산한다(결과 표는 전기·후기 두 행).
근거: 금융위 2012-12-21 보도자료(표준형 20% 단독상품 2013.1.1 출시 · 90% 보장형 병존 ·
특약상품 2013.4.1 제도 변경 · 외래 25만원/처방조제 5만원 한도), 시기별 상세표
(2009.10~2012.12 / 2013.1~2015.8 / 2015.9~2017.3 — 2차 확인, 1차 약관 원문 미확보).
  · early  전기 (2009.10~2013.3 가입): 급여·비급여 10% · 통원 정액만 · 재가입 없음
          (단, 2013.1~3 표준형 가입자는 15년마다 재가입 — 예외 한 줄 별도 표기)
  · late10 선택형(10%형, 2013.4~2015.8 판매): 급여·비급여 10% · 통원 정액만 · 15년마다 재가입
  · late20 표준형 (2013.1~2017.3): 급여·비급여 20% · 통원 Max(20%, 정액) · 관리급여 20% · 15년마다 재가입
  · sel2   선택형Ⅱ (2015.9~2017.3): 급여 10% · 비급여 20% · 통원 Max(형별 %, 정액) · 15년마다 재가입
  · unknown 모르겠어요(기본값): 후기 3유형의 범위로 표시
입력 gen2_type 은 early/late10/late20/sel2/unknown 중 하나이다.
레거시 값 standard는 표준형(late20), select2는 선택형Ⅱ(sel2)로 읽는다.
통원 보상한도(외래 1일 25만원)는 비급여 통원에만 적용한다 — 관리급여는 회수 합산액이라
1회 한도와 직접 비교할 수 없다. 한도는 안내가 아니라 보장액에 직접 반영한다
(4·5세대 회당 한도와 같은 방식).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CATALOG_FILE = BASE / "data" / "catalog_items.json"

# ------------------------------------------------------------------ 상수
DEDUCT_GEN23 = {          # 2·3세대 통원 외래 공제액(원) — 의원 1만 / 병원·종합병원 1.5만 / 상급종합 2만
    "tertiary": 20000,
    "general": 15000,
    "hospital": 15000,
    "clinic": 10000,
}
DEDUCT_GEN45 = {          # 4·5세대 급여 통원 최소공제 — 의원 1만 / 병원급 2만
    "tertiary": 20000,
    "general": 20000,
    "hospital": 20000,
    "clinic": 10000,
}
INSTITUTIONS = {
    "tertiary": {"label": "상급종합병원", "short": "상급종합", "api_scope": True},
    "general": {"label": "종합병원", "short": "종합병원", "api_scope": True},
    "hospital": {"label": "병원", "short": "병원", "api_scope": True},
    "clinic": {"label": "의원", "short": "의원", "api_scope": False},
}
VISITS = {"in": "입원", "out": "통원"}

GENERATIONS = [
    {"gen": 1, "name": "1세대", "period": "2009.9 이전", "short": "1세대"},
    {"gen": 2, "name": "2세대", "period": "2009.10~2017.3", "short": "2세대"},
    {"gen": 3, "name": "3세대(착한실손)", "period": "2017.4~2021.6", "short": "3세대"},
    {"gen": 4, "name": "4세대", "period": "2021.7~2026.4", "short": "4세대"},
    {"gen": 5, "name": "5세대", "period": "2026.5.6 출시", "short": "5세대"},
]

# 2세대 전기·후기 — 결과 표에서 두 행으로 분리해 보여 준다.
GEN2_META = {
    "early": {"name": "2세대 전기", "period": "2009.10~2013.3", "short": "2세대 전기"},
    "late": {"name": "2세대 후기", "period": "2013.4~2017.3", "short": "2세대 후기"},
}
# 2세대 유형별 규칙 (인스팅트 #1247 반영 — 근거: 금융위 2012-12-21 보도자료 + 시기별 상세표, 2차 확인)
GEN2_SPEC = {
    # noncovered: 비급여 자기부담률(%) · managed: 관리급여(급여) 자기부담률(%) ·
    # out: 통원 공제 방식 — flat(정액만) / max(율과 정액 중 큰 금액)
    "early":  {"noncovered": 10, "managed": 10, "out": "flat"},
    "late10": {"noncovered": 10, "managed": 10, "out": "flat"},
    "late20": {"noncovered": 20, "managed": 20, "out": "max"},
    "sel2":   {"noncovered": 20, "managed": 10, "out": "max"},
}
GEN2_TYPES = ("early", "late10", "late20", "sel2", "unknown")
GEN2_LATE_LABEL = {"late10": "10%형", "late20": "표준형 20%", "sel2": "선택형Ⅱ",
                   "unknown": "10%형~20%형"}
OUTPATIENT_CAP_GEN2 = 250000  # 2세대 통원 외래 1일 보상한도 (표준약관 기준)


def _gen2_legacy(v) -> str:
    """2세대 유형 값 정규화 — 레거시 standard→표준형(late20), select2→선택형Ⅱ(sel2)."""
    if v in GEN2_TYPES:
        return v
    if v == "standard":
        return "late20"
    if v == "select2":
        return "sel2"
    return "unknown"


def _gen2_cut_copay(base: int, cut: int, mode: str, visit: str, ded23: int) -> int:
    """2세대 본인부담 1건 — flat은 통원 정액만, max는 율과 정액 중 큰 금액."""
    raw = pct(base, cut)
    if visit == "out":
        raw = min(ded23, base) if mode == "flat" else max(raw, min(ded23, base))
    return min(raw, base)


def gen2_copay(ctx: dict, sub: str, item: dict, base: int, ded23: int) -> tuple[int, int | None]:
    """2세대 행의 본인부담 (copay, copay_hi|None) — unknown은 후기 3유형의 최소~최대."""
    managed = item["payment"] == "관리급여"
    key = "managed" if managed else "noncovered"
    if sub == "early":
        spec = GEN2_SPEC["early"]
        return _gen2_cut_copay(base, spec[key], spec["out"], ctx["visit"], ded23), None
    t = ctx["gen2_type"]
    if t == "early":
        t = "late20"  # 전기를 고른 경우 후기 행은 표준형(기존 기본값)으로 표시한다
    if t in GEN2_SPEC:
        spec = GEN2_SPEC[t]
        return _gen2_cut_copay(base, spec[key], spec["out"], ctx["visit"], ded23), None
    vals = [_gen2_cut_copay(base, GEN2_SPEC[_t][key], GEN2_SPEC[_t]["out"],
                            ctx["visit"], ded23) for _t in ("late10", "late20", "sel2")]
    lo, hi = min(vals), max(vals)
    return lo, (hi if hi > lo else None)

# 관리급여(도수치료) 상수 — 보건복지부 2026-07-01 시행
MANAGED_UNIT_PRICE = 43850      # 1회 수가(종별 동일, 종별가산 없음)
MANAGED_COPAY_RATE = 0.95       # 선별급여 본인부담률 95%
MANAGED_ROUNDS_STD = 15         # 연간 15회
MANAGED_ROUNDS_MAX = 24         # 수술·골절 등 예외 24회

# 5세대 비급여 특약별 연간 한도(계산에는 반영하지 않고 안내로만 쓴다)
LIMIT5_SEVERE = 50_000_000      # 특약1 연 5천만원
LIMIT5_MILD = 10_000_000        # 특약2 연 1천만원
CAP5_SEVERE_INPATIENT_OOP = 5_000_000   # 특약1 상급·종합병원 입원 연간 자기부담 상한 500만원


# ------------------------------------------------------------------ 유틸
def rwon(x: float) -> int:
    """원 단위 반올림(사사오입). JS Math.round 와 결과를 일치시킨다."""
    return int(math.floor(float(x) + 0.5))


def pct(base: int, p: int) -> int:
    """정수 퍼센트 계산(반올림). 부동소수 오차 없이 Python·JS 결과를 같게 만든다."""
    return (int(base) * int(p) + 50) // 100


def load_catalog(path: Path | None = None) -> list[dict]:
    data = json.loads((path or CATALOG_FILE).read_text(encoding="utf-8"))
    return data["items"]


def item_by_code(code: str, items: list[dict] | None = None) -> dict | None:
    for it in (items if items is not None else load_catalog()):
        if it["code"] == code:
            return it
    return None


def managed_total(rounds: int = 1) -> int:
    """관리급여 도수치료 총 진료비(수가)."""
    n = max(1, int(rounds))
    return MANAGED_UNIT_PRICE * n


def won(n: int) -> str:
    return f"{int(n):,}원"


# ------------------------------------------------------------------ 계산
def _normalize(req: dict, items: list[dict]) -> dict:
    visit = req.get("visit", "out")
    if visit not in VISITS:
        raise ValueError(f"visit 는 in/out 중 하나여야 합니다: {visit!r}")
    inst = req.get("institution", "tertiary")
    if inst not in INSTITUTIONS:
        raise ValueError(f"알 수 없는 의료기관 종별: {inst!r}")

    code = req.get("item_code") or "direct"
    if code == "direct":
        item = {"code": "direct", "name": "직접 입력 금액", "payment": "비급여",
                "special3": False, "excluded5": None, "slug": None}
    else:
        found = item_by_code(code, items)
        if not found:
            raise ValueError(f"카탈로그에 없는 항목 코드: {code!r}")
        item = found

    amount = req.get("amount")
    if amount is None:
        amount = managed_total(req.get("rounds", 1)) if item["payment"] == "관리급여" else 0
    amount = int(amount)
    if amount < 0:
        amount = 0

    return {
        "item": item,
        "code": code,
        "amount": amount,
        "visit": visit,
        "institution": inst,
        "severe": bool(req.get("severe", False)),
        # 2세대 유형: early(전기) · late10(후기 10%형) · late20(표준형) · sel2(선택형Ⅱ) ·
        # unknown(모르겠어요). 레거시 standard는 표준형(late20), select2는 선택형Ⅱ(sel2)로 읽는다.
        "gen2_type": _gen2_legacy(req.get("gen2_type")),
        "severe_cum": max(0, int(req.get("severe_cum", 0) or 0)),
        "rounds": max(1, int(req.get("rounds", 1) or 1)),
    }


def _limits_for(gen: int, ctx: dict, item: dict, sub: str | None = None) -> list[str]:
    """계산에는 반영하지 않고 화면에 안내하는 한도 문구."""
    notes: list[str] = []
    managed = item["payment"] == "관리급여"
    if gen == 1:
        notes.append("세대 표준형 기준 · 상품별 약관(한도·자기부담) 차이 있음")
    elif gen == 2:
        notes.append("통원 보상한도: 외래 1일 25만원 · 처방조제 1일 5만원 · 외래·처방조제 각각 연간 180회 (표준약관 기준)")
        notes.append("입원 보상한도: 상해·질병당 5,000만원 (표준약관 기준)")
        if managed:
            notes.append("관리급여 95%는 건강보험 본인부담률 — 실손은 그중 90% 보장(표준형은 80%)")
        if sub == "early":
            notes.append("2013년 3월 이전 가입(전기) — 재가입 절차가 없는 유형입니다(약관 기준)")
            notes.append("단, 2013년 1월~3월에 표준형으로 가입한 경우 15년마다 재가입합니다 — 증권에서 확인하세요")
        elif ctx["gen2_type"] == "unknown":
            notes.append("2013년 4월 이후 가입(후기) · 자기부담 10%형/20%형 — 유형을 모르면 세 유형의 범위로 표시합니다")
            notes.append("15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. "
                         "재가입 때 보험료와 조건은 보험사 안내를 확인하세요")
        elif ctx["gen2_type"] == "late10":
            notes.append("2013년 4월~2015년 8월 가입(후기 10%형·선택형) · 자기부담 10% · 15년마다 재가입합니다")
            notes.append("15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. "
                         "재가입 때 보험료와 조건은 보험사 안내를 확인하세요")
        elif ctx["gen2_type"] == "sel2":
            notes.append("2015년 9월~2017년 3월 가입(후기 선택형Ⅱ) · 급여 10% · 비급여 20% · 15년마다 재가입합니다")
            notes.append("15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. "
                         "재가입 때 보험료와 조건은 보험사 안내를 확인하세요")
        else:  # late20 표준형
            notes.append("표준형(20%형) · 급여·비급여 자기부담 20% · 15년마다 재가입합니다")
            notes.append("15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. "
                         "재가입 때 보험료와 조건은 보험사 안내를 확인하세요")
    elif gen == 3:
        notes.append("비급여 연간 한도·갱신 조건은 약관 확인 필요")
        if managed:
            notes.append("관리급여 95%는 건강보험 본인부담률 — 실손은 그중 90% 보장(통원 10% 공제)")
    elif gen == 4:
        if not managed:
            notes.append("통원 회당 보장 20만원 한도 적용")
        else:
            notes.append("관리급여 95%는 건강보험 본인부담률 — 실손은 그중 80% 보장(입원·통원 20% 공제)")
        notes.append("연간 보장한도 5천만원 · 비급여 이용량 차등할증 대상")
    elif gen == 5:
        if managed:
            notes.append(f"관리급여 본인부담 95% · 1회 {won(MANAGED_UNIT_PRICE)}(종별 동일)")
            notes.append("실손 보장 5% 수준 — 건강보험 본인부담금의 5%만 보장")
            notes.append(f"연간 {MANAGED_ROUNDS_STD}회(수술·골절 등 예외 {MANAGED_ROUNDS_MAX}회) 한도")
        elif ctx["severe"]:
            notes.append(f"중증 비급여(특약1) 연간 {won(LIMIT5_SEVERE)} 한도 · 통원 회당 20만원")
            if ctx["institution"] in ("tertiary", "general"):
                notes.append("상급·종합병원 입원 연간 자기부담 상한 500만원(초과분 보장)")
        else:
            notes.append(f"비중증 비급여(특약2) 연간 {won(LIMIT5_MILD)} 한도 · 통원 일당 20만원")
            if ctx["visit"] == "in":
                notes.append("입원 회당 300만원 한도")
            notes.append("특약2는 이용량에 따라 보험료 할인·할증 적용")
    return notes


def _rate_label(gen: int, ctx: dict, item: dict, sub: str | None = None) -> str:
    visit = ctx["visit"]
    managed = item["payment"] == "관리급여"
    if gen == 1:
        return "입원 100%" if visit == "in" else "5천원 공제 후 100%"
    if gen == 2:
        t = "early" if sub == "early" else ctx["gen2_type"]
        if sub != "early" and t == "early":
            t = "late20"  # 전기를 고른 경우 후기 행은 표준형(기존 기본값)으로 표시한다
        if t == "unknown":
            return "10%~20%" if visit == "in" else "Max(10%~20%, 외래공제)"
        spec = GEN2_SPEC[t]
        cut = spec["managed" if managed else "noncovered"]
        if visit == "in":
            return "급여 90%" if (managed and cut == 10) else f"{cut}%"
        if spec["out"] == "flat":
            return "정액만(외래공제)"
        return f"Max({cut}%, 외래공제)"
    if gen == 3:
        if item["special3"] and not managed:
            return "20%" if visit == "in" else "Max(30%, 2만원)"
        if managed:
            return "급여 90%" if visit == "in" else "Max(10%, 외래공제)"
        return "20%" if visit == "in" else "Max(20%, 외래공제)"
    if gen == 4:
        if managed:
            return "20%" if visit == "in" else "Max(20%, 1·2만원)"
        return "30%" if visit == "in" else "Max(30%, 3만원)"
    # gen 5
    if managed:
        return "20%" if visit == "in" else "Max(건보 95%, 1·2만원)"
    if ctx["severe"]:
        return "30%" if visit == "in" else "Max(30%, 3만원)"
    return "50%" if visit == "in" else "Max(50%, 5만원)"


def _gen_row(gen: int, ctx: dict, sub: str | None = None) -> dict:
    item = ctx["item"]
    visit = ctx["visit"]
    inst = ctx["institution"]
    managed = item["payment"] == "관리급여"
    if gen == 2 and sub in GEN2_META:
        meta = GEN2_META[sub]
    else:
        meta = next(g for g in GENERATIONS if g["gen"] == gen)

    total = ctx["amount"]
    # 급여(관리급여) 항목은 '건강보험 본인부담금'이 실손 계산의 기준액이 된다.
    base = pct(total, 95) if managed else total
    ded23, ded45 = DEDUCT_GEN23[inst], DEDUCT_GEN45[inst]

    status = "covered"
    badges: list[str] = []
    covered_cap: int | None = None
    copay = 0
    copay_hi: int | None = None  # 범위 상한(모르겠어요 후기 행) — None이면 단일값
    cap_applied = False
    cap_outpatient = False  # 부이 #1279 ③ — 2세대 통원 외래 1일 25만원 한도 적용 여부
    extra_note: list[str] = []

    # 인스팅트 #1283 ① — 관리급여 통원은 공제가 방문 1회당이므로, 횟수가 2회 이상이면
    # 1회분으로 계산해 횟수를 곱한다. 총액에 1회만 적용하면 과소 계산됨
    # (도수치료 10회 통원·의원: 전 유형 100,000원). 금액이 1회 수가 × 횟수와 다르면
    # (직접 입력 등) 기존 총액 계산을 유지한다.
    _n = ctx.get("rounds", 1)
    if managed and visit == "out" and _n > 1 and total == MANAGED_UNIT_PRICE * _n:
        unit = _gen_row(gen, dict(ctx, amount=MANAGED_UNIT_PRICE, rounds=1), sub)
        if unit["status"] == "excluded":
            unit["copay"] = base
            unit["copay_hi"] = None
            unit["covered"] = 0
            unit["covered_lo"] = None
        else:
            unit["copay"] = unit["copay"] * _n
            if unit["copay_hi"] is not None:
                unit["copay_hi"] = unit["copay_hi"] * _n
                if unit["copay_hi"] <= unit["copay"]:
                    unit["copay_hi"] = None
            if unit["copay"] > base:
                unit["copay"] = base
                unit["copay_hi"] = None
            unit["covered"] = base - unit["copay"]
            unit["covered_lo"] = (base - unit["copay_hi"]) if unit["copay_hi"] is not None else None
        unit["base"] = base
        # 부이 #1296 — 이 분기는 rounds=1로 재귀 호출하므로 per_visit을 여기서 직접 정한다.
        unit["per_visit"] = gen == 2
        return unit

    # 약관상 보장 제외 항목(시력교정술·예방접종·치과 비급여 보철 등)
    # 카탈로그의 excluded_gens 에 든 세대는 계산 없이 0원(전액 본인부담)으로 둔다.
    excluded_gens = item.get("excluded_gens") or []
    gen_excluded = gen in excluded_gens

    if gen_excluded:
        status = "excluded"
        copay = base
    elif gen == 5 and not managed and item["excluded5"] and not ctx["severe"]:
        status = "excluded"
        copay = base
    elif gen == 1:
        copay = min(5000, base) if visit == "out" else 0
    elif gen == 2:
        # 2세대 유형별 규칙(인스팅트 #1247): 전기·후기 10%형은 통원 정액만,
        # 표준형·선택형Ⅱ는 통원 Max(형별 %, 정액). 관리급여도 같은 급여/비급여 구분을 따른다.
        copay, copay_hi = gen2_copay(ctx, sub or "late", item, base, ded23)
        # 통원 외래 1일 보상한도 25만원 — 비급여 통원에만 적용(관리급여는 회수 합산액이라 제외).
        if visit == "out" and not managed:
            _floor = base - OUTPATIENT_CAP_GEN2
            if _floor > 0:
                if copay < _floor:
                    copay = _floor
                    cap_applied = True
                    cap_outpatient = True
                if copay_hi is not None and copay_hi < _floor:
                    copay_hi = _floor
                    cap_applied = True
                    cap_outpatient = True
                if copay_hi is not None and copay_hi <= copay:
                    copay_hi = None
    elif gen == 3:
        if item["special3"] and not managed:
            badges.append("3세대 비급여 특약")
            if visit == "in":
                raw = pct(base, 20)
            else:
                raw = max(pct(base, 30), min(20000, base))
        else:
            # 관리급여도 2세대와 같은 이유로 급여 90%(10% 공제) — 비급여 20%가 아니다.
            cut3 = 10 if managed else 20
            raw = pct(base, cut3)
            if visit == "out":
                raw = max(raw, min(ded23, base))
        copay = min(raw, base)
    elif gen == 4:
        if managed:
            raw = pct(base, 20)
            if visit == "out":
                raw = max(raw, min(ded45, base))
        else:
            if visit == "in":
                raw = pct(base, 30)
            else:
                raw = max(pct(base, 30), min(30000, base))
                covered_cap = 200000
        copay = min(raw, base)
    elif gen == 5:
        if managed:
            raw = pct(base, 20)
            if visit == "out":
                raw = max(raw, pct(base, 95), min(ded45, base))
            copay = min(raw, base)
        elif ctx["severe"]:
            badges.append("특약1 중증")
            if visit == "in":
                raw = pct(base, 30)
                if inst in ("tertiary", "general") and ctx["severe_cum"] > 0:
                    overflow = ctx["severe_cum"] + raw - CAP5_SEVERE_INPATIENT_OOP
                    if overflow > 0:
                        cut = min(overflow, raw)
                        raw -= cut
                        if cut:
                            extra_note.append(
                                f"연간 자기부담 상한 500만원 초과분 {won(cut)} 추가 보장 반영")
            else:
                raw = max(pct(base, 30), min(30000, base))
                covered_cap = 200000
            copay = min(raw, base)
        else:
            badges.append("특약2 비중증")
            if visit == "in":
                raw = pct(base, 50)
                covered_cap = 3_000_000
            else:
                raw = max(pct(base, 50), min(50000, base))
                covered_cap = 200000
            copay = min(raw, base)
    else:
        raise ValueError(f"알 수 없는 세대: {gen}")

    covered = 0 if status == "excluded" else base - copay
    covered_lo = (base - copay_hi) if (status != "excluded" and copay_hi is not None) else None
    if status != "excluded" and covered_cap is not None and covered > covered_cap:
        covered = covered_cap
        copay = base - covered
        cap_applied = True

    if managed:
        badges.insert(0, "관리급여 95%")
    if gen_excluded:
        badges.append("약관상 보장 제외")
    elif gen == 5 and not managed and item["excluded5"]:
        badges.append("5세대 보장 제외")

    limits = _limits_for(gen, ctx, item, sub)
    limits.extend(extra_note)
    rate_label = _rate_label(gen, ctx, item, sub)
    if status == "excluded" and gen_excluded:
        rate_label = "보장 제외"
        limits = [f"약관상 보장 제외(사유: {item.get('exclude_reason') or '보장 대상 아님'})",
                  "가입 시기·상품 약관에 따라 판단이 달라질 수 있어 보험사 확인이 필요합니다",
                  "같은 날 받은 급여 항목의 본인부담금은 별도로 청구할 수 있습니다"]
    elif status == "excluded":
        rate_label = "보장 제외"
        limits = [f"5세대 특약2 보장 대상에서 제외(사유: {item['excluded5']})",
                  "산정특례 대상 질환 치료 등 특약1 해당 여부는 보험사 심사로 확인",
                  "4세대 이전 세대는 위 자기부담 기준으로 계산됩니다"]

    if gen == 2:
        _t = "early" if sub == "early" else ctx["gen2_type"]
        if sub != "early" and _t == "early":
            _t = "late20"  # 전기를 고른 경우 후기 행은 표준형(기존 기본값)으로 표시한다
        _ded_txt = "외래공제(의원 1만·종합병원·병원 1.5만·상급종합 2만)"
        if _t == "unknown":
            if managed:
                rule2 = (f"관리급여(급여) 항목: 통원은 정액 공제만 또는 형별 %와 {_ded_txt} "
                         "중 큰 금액 — 유형별 범위 적용")
            else:
                rule2 = (f"비급여 본인부담 10%형~20%형 범위 · 통원은 형별 %와 {_ded_txt} "
                         "중 큰 금액 공제")
        else:
            _spec = GEN2_SPEC[_t]
            _cut = _spec["managed" if managed else "noncovered"]
            if managed:
                if _spec["out"] == "flat":
                    rule2 = f"관리급여(급여) 항목: {100 - _cut}% 보장 · 통원은 정액 공제만({_ded_txt})"
                else:
                    rule2 = (f"관리급여(급여) 항목: {100 - _cut}% 보장 · 통원은 {_cut}%와 "
                             f"{_ded_txt} 중 큰 금액 공제")
            elif _spec["out"] == "flat":
                rule2 = f"비급여 본인부담 {_cut}% · 통원은 정액 공제만({_ded_txt})"
            else:
                rule2 = (f"비급여 본인부담 {_cut}% · 통원은 {_cut}%와 {_ded_txt} "
                         "중 큰 금액 공제")
    else:
        rule2 = ""
    rule = {
        1: "입원 100% 보장 / 통원 5,000원 공제 후 100% (표준형 기준)",
        2: rule2,
        3: ("관리급여(급여) 항목: 90% 보장 · 통원은 10%와 외래공제 중 큰 금액 공제"
            if managed else
            ("3세대 비급여 특약(도수·체외충격파·증식·비급여 주사·MRI): 통원 Max(30%, 2만원) 공제"
             if (item["special3"] and not managed) else
             "기본 비급여 20% 공제 · 통원은 20%와 외래공제 중 큰 금액 공제")),
        4: ("4세대 비급여 특약: 입원 30% · 통원 Max(30%, 3만원), 통원 회당 20만원 한도"
            if not managed else "급여 항목: 입원 20% · 통원 Max(20%, 1·2만원)"),
        5: ("5세대 특약1(중증 비급여): 입원 30% · 통원 Max(30%, 3만원), 상급·종합 입원 연 자기부담 상한 500만원"
            if (ctx["severe"] and not managed) else
            ("5세대 특약2(비중증 비급여): 입원 50% · 통원 Max(50%, 5만원), 입원 회당 300만·통원 일당 20만 한도"
             if not managed else
             "5세대 급여: 통원 자기부담률을 건강보험 본인부담률(관리급여 95%)에 연동 → 실손 보장 5% 수준")),
    }[gen]

    if status == "excluded" and gen_excluded:
        rule = ("약관상 보장 제외 — " + (item.get("exclude_reason") or "보장 대상이 아닙니다."))
    elif status == "excluded":
        rule = f"5세대 비중증 비급여 보장 제외 항목({item['excluded5']}) — 특약2에서 보장하지 않습니다."

    period = meta["period"]
    if gen == 2 and sub == "late":
        period = f"{period} · {GEN2_LATE_LABEL.get(ctx['gen2_type'], '10%형~20%형')} 기준"
    return {
        "gen": gen,
        "sub": sub or "",
        "key": {1: "g1", 3: "g3", 4: "g4", 5: "g5"}.get(gen) or f"g2{sub[0]}",
        "name": meta["name"],
        "period": period,
        "status": status,
        "base": base,
        "copay": copay,
        "copay_hi": copay_hi,
        "covered": covered,
        "covered_lo": covered_lo,
        "same_amount": False,
        "rate_label": rate_label,
        "rule": rule,
        "badges": badges,
        "limits": limits,
        "cap_applied": cap_applied,
        "cap_outpatient": cap_outpatient,
        # 부이 #1296 — 관리급여 통원 2회 이상: 공제가 방문 1회마다 따로 적용됨을 표에 한 줄로 푼다.
        "per_visit": gen == 2 and managed and visit == "out" and ctx["rounds"] > 1,
    }


def compute(req: dict, items: list[dict] | None = None) -> dict:
    """한 건의 비급여(또는 관리급여) 진료에 대한 1~5세대 비교 결과를 만든다."""
    items = items if items is not None else load_catalog()
    ctx = _normalize(req, items)
    rows = [_gen_row(1, ctx), _gen_row(2, ctx, "early"), _gen_row(2, ctx, "late"),
            _gen_row(3, ctx), _gen_row(4, ctx), _gen_row(5, ctx)]

    # 부이 #1245 ⑤·⑧ — 후기 행 보충 안내 (전기 행과 후기 10%형 기준 대조)
    _early, _late = rows[1], rows[2]
    _ctx10 = dict(ctx, gen2_type="late10")
    _late10 = _gen_row(2, _ctx10, "late")
    _same = (_early["copay"] == _late10["copay"] and _early["covered"] == _late10["covered"]
             and _early["status"] == _late10["status"])
    _late["same_amount"] = _same
    if _same and ctx["gen2_type"] in ("late10", "unknown"):
        _late["limits"].append("전기(2013년 3월 이전 가입)와 후기 10%형은 같은 금액입니다")
    _late_max_copay = _late["copay_hi"] if _late["copay_hi"] is not None else _late["copay"]
    if _late_max_copay > _early["copay"]:
        if ctx["gen2_type"] == "unknown":
            _late["limits"].append("후기 20%형·선택형Ⅱ는 전기·후기 10%형보다 본인부담이 큽니다")
        else:
            _lbl = GEN2_LATE_LABEL.get(ctx["gen2_type"], "표준형 20%")
            _late["limits"].append(
                f"후기 {_lbl}는 전기·후기 10%형보다 본인부담이 큽니다")
    if ctx["item"]["payment"] == "관리급여" and _late["copay_hi"] is not None:
        # 범위인 경우는 '모르겠어요'뿐이다 — 표준형(20%형)은 83,315원 단일값으로 확정됨(#1247 (b))
        _late["limits"].append(
            f"후기 관리급여는 유형·약관에 따라 {won(_late['copay'])}~{won(_late['copay_hi'])}입니다 "
            "— 금액 옆 범위를 확인하세요")

    covered_rows = [r for r in rows if r["status"] != "excluded"]
    best = max(covered_rows, key=lambda r: (r["covered"], -r["gen"])) if covered_rows else None

    warnings: list[str] = []
    if ctx["item"]["payment"] == "관리급여":
        warnings.append(
            "도수치료는 2026.7.1부터 관리급여(선별급여)입니다. 비급여 특약이 아니라 "
            f"급여 항목으로 계산하며, 1회 {won(MANAGED_UNIT_PRICE)}(종별 동일) · 본인부담률 95% 기준입니다."
        )
    if not INSTITUTIONS[ctx["institution"]]["api_scope"]:
        warnings.append(
            "의원은 심평원 비급여 공개 API 대상이 아닙니다(병원급 이상만 제공). "
            "종별 공제액 계산을 위한 참고 선택이며, 의원 가격은 방문 전 유선 확인이 필요합니다."
        )
    if ctx["item"].get("excluded_gens"):
        warnings.append(
            "이 항목은 표준 실손약관상 보장 제외 대상입니다 — " + (ctx["item"].get("exclude_reason") or "") +
            " 세대별 표시를 확인하고, 실제 지급 여부는 가입 약관과 보험사 심사로 확인하세요."
        )
    if ctx["severe"]:
        warnings.append(
            "중증(산정특례) 여부는 5세대 특약1·2 구분에만 영향을 줍니다. "
            "1~4세대는 해당 질환도 비급여 자기부담률이 같습니다(단, 4세대 비급여 차등할증에서 중증은 제외)."
        )
    if any(r["cap_applied"] for r in rows):
        warnings.append("일부 세대는 회당 보장한도가 적용되어 계산된 보장액이 한도에 걸렸습니다(표시 참조).")

    return {
        "input": {
            "item_code": ctx["code"],
            "item_name": ctx["item"]["name"],
            "payment": ctx["item"]["payment"],
            "amount": ctx["amount"],
            "visit": ctx["visit"],
            "visit_label": VISITS[ctx["visit"]],
            "institution": ctx["institution"],
            "institution_label": INSTITUTIONS[ctx["institution"]]["label"],
            "severe": ctx["severe"],
            "gen2_type": ctx["gen2_type"],
            "severe_cum": ctx["severe_cum"],
            "rounds": ctx["rounds"],
        },
        "generations": rows,
        "summary": {
            "best_gen": best["gen"] if best else None,
            "best_key": best["key"] if best else None,
            "best_covered": best["covered"] if best else 0,
            "excluded_gens": [r["gen"] for r in rows if r["status"] == "excluded"],
        },
        "warnings": warnings,
    }


if __name__ == "__main__":  # 간단한 CLI 확인용
    import argparse

    ap = argparse.ArgumentParser(description="실손 1~5세대 계산 엔진 단건 실행")
    ap.add_argument("--item", default="HE1010001")
    ap.add_argument("--amount", type=int, default=600000)
    ap.add_argument("--visit", default="out", choices=["in", "out"])
    ap.add_argument("--inst", default="tertiary",
                    choices=list(INSTITUTIONS))
    ap.add_argument("--severe", action="store_true")
    ap.add_argument("--gen2", default="unknown",
                    choices=["early", "late10", "late20", "sel2", "unknown"])
    args = ap.parse_args()
    res = compute({"item_code": args.item, "amount": args.amount, "visit": args.visit,
                   "institution": args.inst, "severe": args.severe, "gen2_type": args.gen2})
    print(json.dumps(res, ensure_ascii=False, indent=2))
