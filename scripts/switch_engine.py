#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
실손 5세대 전환 손익 시뮬레이터 계산 엔진 (Python 기준 구현)

이 파일이 계산 규칙의 '기준(canonical)'이고, assets/switch-gen5.js 의
Gen5Sim.compute() 가 같은 규칙을 바닐라 JS 로 옮긴 구현이다.
두 구현의 동일성은 scripts/crosscheck_switch.py 가 수천 건 조합으로 전수 검증한다.

근거 (T-M13 v4 / T-M01-D 1차 출처 대조표)
  · 금융위원회·금융감독원 2026-05-06 보도자료 및 5세대 실손 Q&A
    — 5세대 실손의료보험 출시(급여 20%·통원 최소 자기부담금 1만/2만 원,
      특약1(중증) 30%·연 5,000만 원·상급/종합병원 입원 연 자기부담 상한 500만 원,
      특약2(비중증) 50%·연 1,000만 원·통원 Max[50%, 5만 원]·일당 20만 원·병·의원 입원 회당 300만 원)
  · 금융위 고시 제2026-16호 부칙 제3조(특례)① — 5세대 특약2 비급여 차등제 첫 적용은
    2028년 5월 이후 갱신분부터(2028-05-06 이후 전 보험사 공통)
  · 삼성화재·DB손해보험 5세대 상품공시 — 재가입(갱신) 주기 5년, 회사별 할증률 상이

계산 범위 원칙
  · 사용자가 직접 입력한 값만 쓰고 서버로 보내지 않는다(개인정보 수집 없음).
  · 1차 계산에서 반영하지 않는 항목은 화면 안내 문구로만 처리한다:
    비급여 차등제 할증(회사별 상이), 관리급여 95% 세부 계산, 계약전환 할인·선택형 할인 특약,
    5년 재가입, 철회 기한, 5세대 중증 입원 자기부담 상한 500만 원.
  · 금액은 모두 원 단위 정수. 퍼센트 연산은 정수 연산(pct)만 써서 파이썬과 JS 의
    부동소수 오차가 생기지 않게 한다.
"""
from __future__ import annotations

# ------------------------------------------------------------------ 상수
DEPOSIT = 0.0  # (미사용)

GENS = [
    {"gen": 1, "name": "1세대", "period": "2009.9 이전"},
    {"gen": 2, "name": "2세대", "period": "2009.10~2017.3"},
    {"gen": 3, "name": "3세대", "period": "2017.4~2021.6"},
    {"gen": 4, "name": "4세대", "period": "2021.7~2026.4"},
    {"gen": 5, "name": "5세대", "period": "2026.5.6 이후"},
]

# 통원 1회 최소 공제액(원) — 급여·비급여 통원에서 '비율 금액'과 비교해 큰 금액을 환자 부담으로 본다.
DEDUCT = {
    2: {"tertiary": 20000, "general": 20000, "hospital": 15000, "clinic": 10000},
    3: {"tertiary": 20000, "general": 20000, "hospital": 20000, "clinic": 10000},
    4: {"tertiary": 20000, "general": 20000, "hospital": 20000, "clinic": 10000},
    5: {"tertiary": 20000, "general": 20000, "hospital": 20000, "clinic": 10000},
}
# 5세대 비중증 통원 1회 최소 자기부담금
MILD5_MIN_VISIT = 50000
# 연간 보장 한도(원) — 보험사가 지급하는 금액의 상한. 초과분은 환자 부담.
LIMITS = {
    4: {"severe": 50000000, "mild": 50000000},
    5: {"severe": 50000000, "mild": 10000000},
}

# 5세대 보험료 자동 추정 인하율(%) — 기준 세대별 분리
EST_DISCOUNT = {1: 50, 2: 50, 3: 30, 4: 30}
DISCOUNT_MIN, DISCOUNT_MAX = 10, 70

# 판단 보류 임계값(연 |Δ| ≤ 5만 원)
HOLD_THRESHOLD = 50000

# 손익분기 곡선 범위
BE_MIN_XMAX = 2000000
BE_STEP = 100000
BE_POINTS = 200


def pct(base: int, p: int) -> int:
    """base 의 p% (반올림, 음수 없음). 정수 연산만 사용."""
    b = int(base)
    if b <= 0:
        return 0
    return (b * int(p) + 50) // 100


def rates(gen: int, gen1_rate: float | None = None, gen2_type: str = "standard",
          gen3_type: str = "standard") -> dict | None:
    """세대별 자기부담률(%) — 급여 입원/통원, 비급여 중증/비중증.

    1세대는 계약별 자기부담이 달라 단일 기준이 없으므로 직접 입력값을 쓴다(없으면 None).
    """
    if gen == 1:
        if gen1_rate is None:
            return None
        r = int(round(float(gen1_rate)))
        if r < 0 or r > 100:
            return None
        return {"cov_in": r, "cov_out": r, "severe": r, "mild": r}
    if gen == 2:
        if gen2_type == "select1":
            return {"cov_in": 10, "cov_out": 10, "severe": 20, "mild": 20}
        return {"cov_in": 20, "cov_out": 20, "severe": 20, "mild": 20}
    if gen == 3:
        if gen3_type == "select2":
            return {"cov_in": 20, "cov_out": 20, "severe": 20, "mild": 20}
        return {"cov_in": 10, "cov_out": 10, "severe": 20, "mild": 20}
    if gen == 4:
        return {"cov_in": 20, "cov_out": 20, "severe": 30, "mild": 30}
    if gen == 5:
        return {"cov_in": 20, "cov_out": 20, "severe": 30, "mild": 50}
    return None


def _visit_oop(amount: int, visits: int, rate: int, min_visit: int | None) -> int:
    """통원 연간 금액을 횟수로 나눠 1회 부담(max[비율, 최소 공제])을 구한 뒤 합산."""
    amount = max(0, int(amount or 0))
    visits = int(visits or 0)
    if amount == 0:
        return 0
    if visits <= 0:
        return pct(amount, rate)
    per = (amount + visits // 2) // visits
    one = pct(per, rate)
    if min_visit:
        one = max(one, int(min_visit))
    return min(amount, one * visits)


def _limit_cap(amount: int, oop: int, limit: int | None) -> int:
    """연간 보장 한도 초과분은 환자 부담으로 돌린다."""
    if not limit:
        return oop
    paid = amount - oop
    if paid <= limit:
        return oop
    return amount - limit


def oop_parts(gen: int, r: dict, usage: dict) -> dict:
    """세대·이용 패턴으로 항목별 환자 자기부담금을 계산한다."""
    inst = usage.get("inst") or "clinic"
    min_visit = DEDUCT.get(gen, {}).get(inst)
    if gen == 1:
        min_visit = None          # 1세대는 약관별 정액 공제가 달라 비율만 적용한다.

    cov_in = max(0, int(usage.get("in_cov") or 0))
    cov_out = max(0, int(usage.get("out_cov") or 0))
    severe = max(0, int(usage.get("severe") or 0))
    mild = max(0, int(usage.get("mild") or 0))
    out_visits = int(usage.get("out_visits") or 0)
    mild_visits = int(usage.get("mild_visits") or 0)

    parts = {
        "cov_in": pct(cov_in, r["cov_in"]),
        "cov_out": _visit_oop(cov_out, out_visits, r["cov_out"], min_visit),
        "severe": _limit_cap(severe, pct(severe, r["severe"]), (LIMITS.get(gen) or {}).get("severe")),
        "mild": _visit_oop(mild, mild_visits, r["mild"],
                           MILD5_MIN_VISIT if gen == 5 else min_visit),
    }
    parts["mild"] = _limit_cap(mild, parts["mild"], (LIMITS.get(gen) or {}).get("mild"))
    parts["total"] = parts["cov_in"] + parts["cov_out"] + parts["severe"] + parts["mild"]
    return parts


def premium5(pcur: int, mode: str, p5: int | None, discount: int | None, gen: int) -> tuple[int, bool, int]:
    """5세대 월 보험료 — 직접 입력 우선, 모르면 세대별 인하율로 추정."""
    pcur = max(0, int(pcur or 0))
    if mode == "manual":
        return max(0, int(p5 or 0)), False, 0
    d = EST_DISCOUNT.get(gen, 30) if discount is None else int(discount)
    d = max(DISCOUNT_MIN, min(DISCOUNT_MAX, d))
    return pct(pcur, 100 - d), True, d


def _delta_at(mild_amount: int, base: dict, r_cur: dict, r_5: dict, gen: int,
              premium_saving: int) -> int:
    usage = dict(base)
    usage["mild"] = int(mild_amount)
    cur = oop_parts(gen, r_cur, usage)["total"]
    g5 = oop_parts(5, r_5, usage)["total"]
    return premium_saving + (cur - g5)


def break_even(base: dict, r_cur: dict, r_5: dict, gen: int, premium_saving: int,
               current_mild: int) -> dict:
    """비중증 비급여 연간 이용액을 0부터 늘려가며 Δ=0 이 되는 지점을 찾는다."""
    xmax = max(BE_MIN_XMAX, int(current_mild) * 2)
    xmax = (xmax + BE_STEP - 1) // BE_STEP * BE_STEP
    points = []
    prev_x, prev_d = 0, _delta_at(0, base, r_cur, r_5, gen, premium_saving)
    points.append((0, prev_d))
    be = None
    for i in range(1, BE_POINTS + 1):
        x = xmax * i // BE_POINTS
        d = _delta_at(x, base, r_cur, r_5, gen, premium_saving)
        points.append((x, d))
        if be is None and (prev_d > 0) != (d > 0):
            denom = d - prev_d
            be = prev_x + int((0 - prev_d) * (x - prev_x) / denom) if denom else x
        prev_x, prev_d = x, d
    dirn = None
    if be is not None:
        dirn = "down" if points[-1][1] < points[0][1] else "up"
    return {"xmax": xmax, "points": points, "break_even": be, "dir": dirn}


def compute(req: dict) -> dict:
    """시뮬레이터 1회 계산. 화면(JS)과 같은 입력 키를 쓴다."""
    gen = int(req.get("gen") or 0)
    pcur = max(0, int(req.get("pcur") or 0))
    usage = {
        "in_cov": max(0, int(req.get("in_cov") or 0)),
        "out_cov": max(0, int(req.get("out_cov") or 0)),
        "out_visits": max(0, int(req.get("out_visits") or 0)),
        "severe": max(0, int(req.get("severe") or 0)),
        "mild": max(0, int(req.get("mild") or 0)),
        "mild_visits": max(0, int(req.get("mild_visits") or 0)),
        "inst": req.get("inst") or "clinic",
    }
    base = {
        "ok": False, "hold": None, "gen": gen, "pcur": pcur,
        "p5": 0, "p5_estimated": True, "discount": EST_DISCOUNT.get(gen, 30),
        "oop_cur": 0, "oop5": 0, "premium_saving": 0, "oop_increase": 0, "delta": 0,
        "verdict": "hold", "break_even": None, "break_even_dir": None,
        "chart": {"xmax": BE_MIN_XMAX, "points": []},
        "parts": {}, "managed": bool(req.get("managed")),
    }
    if gen == 5:
        base["hold"] = "already_gen5"
        base["ok"] = True
        return base
    if gen not in (1, 2, 3, 4):
        base["hold"] = "gen_missing"
        return base
    if pcur <= 0:
        base["hold"] = "premium_unknown"
        return base
    r_cur = rates(gen, req.get("gen1_rate"), req.get("gen2_type") or "standard",
                  req.get("gen3_type") or "standard")
    if r_cur is None:
        base["hold"] = "gen1_rate"
        return base
    r_5 = rates(5)
    p5, estimated, d = premium5(pcur, "manual" if req.get("p5_mode") == "manual" else "auto",
                                req.get("p5"), req.get("discount"), gen)
    if p5 <= 0:
        base["hold"] = "p5_missing"
        return base

    cur_parts = oop_parts(gen, r_cur, usage)
    g5_parts = oop_parts(5, r_5, usage)
    premium_saving = (pcur - p5) * 12
    oop_increase = g5_parts["total"] - cur_parts["total"]
    delta = premium_saving - oop_increase

    verdict = "hold"
    if delta > HOLD_THRESHOLD:
        verdict = "save"
    elif delta < -HOLD_THRESHOLD:
        verdict = "loss"

    be = break_even(usage, r_cur, r_5, gen, premium_saving, usage["mild"])

    base.update({
        "ok": True, "p5": p5, "p5_estimated": estimated, "discount": d,
        "oop_cur": cur_parts["total"], "oop5": g5_parts["total"],
        "premium_saving": premium_saving, "oop_increase": oop_increase, "delta": delta,
        "verdict": verdict,
        "break_even": be["break_even"], "break_even_dir": be["dir"],
        "chart": {"xmax": be["xmax"], "points": be["points"]},
        "parts": {"cur": cur_parts, "gen5": g5_parts},
    })
    return base


def won(n) -> str:
    return f"{int(n):,}원"
