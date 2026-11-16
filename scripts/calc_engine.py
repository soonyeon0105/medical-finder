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
"""
from __future__ import annotations

import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CATALOG_FILE = BASE / "data" / "catalog_items.json"

# ------------------------------------------------------------------ 상수
DEDUCT_GEN23 = {          # 2·3세대 통원 외래 공제액(원) — 의원 1만 / 병원 1.5만 / 종합·상급 2만
    "tertiary": 20000,
    "general": 20000,
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
        "gen2_type": "select2" if req.get("gen2_type") == "select2" else "standard",
        "severe_cum": max(0, int(req.get("severe_cum", 0) or 0)),
        "rounds": max(1, int(req.get("rounds", 1) or 1)),
    }


def _limits_for(gen: int, ctx: dict, item: dict) -> list[str]:
    """계산에는 반영하지 않고 화면에 안내하는 한도 문구."""
    notes: list[str] = []
    managed = item["payment"] == "관리급여"
    if gen == 1:
        notes.append("세대 표준형 기준 · 상품별 약관(한도·자기부담) 차이 있음")
    elif gen == 2:
        notes.append("통원 회당 보장한도·연간 한도는 상품별 약관 확인 필요")
        if ctx["gen2_type"] == "select2":
            notes.append("선택형Ⅱ: 급여 90% · 비급여 80%")
    elif gen == 3:
        notes.append("비급여 연간 한도·갱신 조건은 약관 확인 필요")
    elif gen == 4:
        if not managed:
            notes.append("통원 회당 보장 20만원 한도 적용")
        notes.append("연간 보장한도 5천만원 · 비급여 이용량 차등할증 대상")
    elif gen == 5:
        if managed:
            notes.append(f"관리급여 본인부담 95% · 1회 {won(MANAGED_UNIT_PRICE)}(종별 동일)")
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


def _rate_label(gen: int, ctx: dict, item: dict) -> str:
    visit = ctx["visit"]
    managed = item["payment"] == "관리급여"
    if gen == 1:
        return "입원 100%" if visit == "in" else "5천원 공제 후 100%"
    if gen == 2:
        if managed and ctx["gen2_type"] == "select2":
            return "급여 90%" if visit == "in" else "Max(10%, 외래공제)"
        return "80%" if visit == "in" else "Max(20%, 외래공제)"
    if gen == 3:
        if item["special3"] and not managed:
            return "20%" if visit == "in" else "Max(30%, 2만원)"
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


def _gen_row(gen: int, ctx: dict) -> dict:
    item = ctx["item"]
    visit = ctx["visit"]
    inst = ctx["institution"]
    managed = item["payment"] == "관리급여"
    meta = next(g for g in GENERATIONS if g["gen"] == gen)

    total = ctx["amount"]
    # 급여(관리급여) 항목은 '건강보험 본인부담금'이 실손 계산의 기준액이 된다.
    base = pct(total, 95) if managed else total
    ded23, ded45 = DEDUCT_GEN23[inst], DEDUCT_GEN45[inst]

    status = "covered"
    badges: list[str] = []
    covered_cap: int | None = None
    copay = 0
    cap_applied = False
    extra_note: list[str] = []

    if gen == 5 and not managed and item["excluded5"] and not ctx["severe"]:
        status = "excluded"
        copay = base
    elif gen == 1:
        copay = min(5000, base) if visit == "out" else 0
    elif gen == 2:
        cut = 10 if (managed and ctx["gen2_type"] == "select2") else 20
        raw = pct(base, cut)
        if visit == "out":
            raw = max(raw, min(ded23, base))
        copay = min(raw, base)
    elif gen == 3:
        if item["special3"] and not managed:
            badges.append("3세대 비급여 특약")
            if visit == "in":
                raw = pct(base, 20)
            else:
                raw = max(pct(base, 30), min(20000, base))
        else:
            raw = pct(base, 20)
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
    if status != "excluded" and covered_cap is not None and covered > covered_cap:
        covered = covered_cap
        copay = base - covered
        cap_applied = True

    if managed:
        badges.insert(0, "관리급여 95%")
    if gen == 5 and not managed and item["excluded5"]:
        badges.append("5세대 보장 제외")

    limits = _limits_for(gen, ctx, item)
    limits.extend(extra_note)
    rate_label = _rate_label(gen, ctx, item)
    if status == "excluded":
        rate_label = "보장 제외"
        limits = [f"5세대 특약2 보장 대상에서 제외(사유: {item['excluded5']})",
                  "산정특례 대상 질환 치료 등 특약1 해당 여부는 보험사 심사로 확인",
                  "4세대 이전 세대는 위 자기부담 기준으로 계산됩니다"]

    rule = {
        1: "입원 100% 보장 / 통원 5,000원 공제 후 100% (표준형 기준)",
        2: "비급여 80% 보장 · 통원은 20%와 외래공제(의원 1만·병원 1.5만·종합/상급 2만) 중 큰 금액 공제",
        3: ("3세대 비급여 특약(도수·체외충격파·증식·비급여 주사·MRI): 통원 Max(30%, 2만원) 공제"
            if (item["special3"] and not managed) else
            "기본 비급여 20% 공제 · 통원은 20%와 외래공제 중 큰 금액 공제"),
        4: ("4세대 비급여 특약: 입원 30% · 통원 Max(30%, 3만원), 통원 회당 20만원 한도"
            if not managed else "급여 항목: 입원 20% · 통원 Max(20%, 1·2만원)"),
        5: ("5세대 특약1(중증 비급여): 입원 30% · 통원 Max(30%, 3만원), 상급·종합 입원 연 자기부담 상한 500만원"
            if (ctx["severe"] and not managed) else
            ("5세대 특약2(비중증 비급여): 입원 50% · 통원 Max(50%, 5만원), 입원 회당 300만·통원 일당 20만 한도"
             if not managed else
             "5세대 급여: 통원 자기부담률을 건강보험 본인부담률(관리급여 95%)에 연동 → 실손 보장 5% 수준")),
    }[gen]

    if status == "excluded":
        rule = f"5세대 비중증 비급여 보장 제외 항목({item['excluded5']}) — 특약2에서 보장하지 않습니다."

    return {
        "gen": gen,
        "name": meta["name"],
        "period": meta["period"],
        "status": status,
        "base": base,
        "copay": copay,
        "covered": covered,
        "rate_label": rate_label,
        "rule": rule,
        "badges": badges,
        "limits": limits,
        "cap_applied": cap_applied,
    }


def compute(req: dict, items: list[dict] | None = None) -> dict:
    """한 건의 비급여(또는 관리급여) 진료에 대한 1~5세대 비교 결과를 만든다."""
    items = items if items is not None else load_catalog()
    ctx = _normalize(req, items)
    rows = [_gen_row(gen, ctx) for gen in (1, 2, 3, 4, 5)]

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
    ap.add_argument("--gen2", default="standard", choices=["standard", "select2"])
    args = ap.parse_args()
    res = compute({"item_code": args.item, "amount": args.amount, "visit": args.visit,
                   "institution": args.inst, "severe": args.severe, "gen2_type": args.gen2})
    print(json.dumps(res, ensure_ascii=False, indent=2))
