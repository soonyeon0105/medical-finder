#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수집한 심평원 XML(+KOSIS 통계표)을 정제해 사이트용 데이터셋을 만든다.

입력
  1) data/raw/{op}/*.xml          — fetch_hira.py 가 실제로 내려받은 원본
  2) data/raw/snapshots/*.json    — 같은 API 응답을 JSON으로 보관한 스냅샷
                                    (getNonPaymentItemClcdList 는 504 로 자주 실패해 스냅샷 사용)
  3) data/kosis_2026.json         — 통계청 KOSIS(승인번호 354006) 의원·치과의원 통계표에서 직접 수집
  4) --fixtures                   — data/fixtures/xml/*.xml (키 없이 파이프라인 검증)

출력
  data/hira_dataset.json    항목별 가격 통계 + 종별/시도 집계 + KOSIS 의원급 참고값
  data/hospitals.json       항목별 병원급 가격 목록(시도/종별 필터용 경량 JSON)
  data/data_quality.json    검증 결과(이상치·누락)
  data/summary.json         사람이 읽는 요약

원칙
  · 없는 값을 추정·보간하지 않는다. 금액이 비어 있으면 비운 채로 둔다.
  · 픽스처 모드 산출물은 synthetic=true 로 표시되어 사이트에 실제 가격으로 표시되지 않는다.
  · 공개 범위는 병원급 이상뿐이다. 의원급(의원·치과의원·한의원) 행이 응답에 있어도 버린다.
  · 공공누리 제4유형 엑셀은 절대 읽지 않는다. 의원급 규모 값은 KOSIS 공개 통계표만 쓴다.

사용법
  python3 scripts/prepare_data.py            # data/raw 사용
  python3 scripts/prepare_data.py --fixtures  # 픽스처로 파이프라인 검증
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
RAW = DATA / "raw"
SNAPSHOTS = RAW / "snapshots"
FIXTURES = DATA / "fixtures" / "xml"
KST = timezone(timedelta(hours=9))

# 종별 코드 → 이름. 실응답의 clCdNm 을 우선 쓰고, 없을 때만 이 표를 쓴다.
CLCD = {
    "01": "상급종합", "11": "종합병원", "21": "병원", "28": "요양병원",
    "29": "정신병원", "41": "치과병원", "92": "한방병원",
    "31": "의원", "32": "치과의원", "33": "한의원", "99": "기타",
}
# 의원급(공개 범위 밖) 판정 — 이름에 '의원' 이 들어가면 제외한다(병원·치과병원·한방병원과 구분).
OUT_OF_SCOPE_NAMES = ("의원", "한의원", "치과의원")
CLCD_OUT_OF_SCOPE = {"31", "32", "33", "99"}

# 시도 코드 → 이름. 실응답의 sidoCdNm 을 우선 쓰고, 없을 때만 이 표를 쓴다.
# (2026년 공개분 기준: 경기 310000, 전남광주 360000, 세종시 410000)
SIDO = {
    "110000": "서울", "210000": "부산", "220000": "인천", "230000": "대구",
    "250000": "대전", "260000": "울산", "310000": "경기", "320000": "강원",
    "330000": "충북", "340000": "충남", "350000": "전북", "360000": "전남광주",
    "370000": "경북", "380000": "경남", "390000": "제주", "410000": "세종시",
}


def num(x) -> int | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if not s or s in ("-", "null", "None"):
        return None
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def parse_xml(path: Path) -> list[dict]:
    """fetch_hira.parse_response 를 재사용해 item 목록만 얻는다."""
    import sys
    sys.path.insert(0, str(BASE / "scripts"))
    from fetch_hira import parse_response  # noqa: E402
    return parse_response(path.read_bytes())["items"]


def snapshot_files(op: str) -> list[Path]:
    """data/raw/snapshots/snapshot_meta.json 이 가리키는 op 별 JSON 스냅샷."""
    meta_path = SNAPSHOTS / "snapshot_meta.json"
    if not meta_path.exists():
        return []
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for f in meta.get("files", []):
        if f.get("op") == op:
            p = SNAPSHOTS / f["file"]
            if p.exists():
                out.append(p)
    return out


def _op_paths(op: str, use_fixtures: bool, files: dict | None = None) -> list[Path]:
    if use_fixtures:
        out: list[Path] = []
        for pat in (files or {}).get(op, []):
            out.extend(sorted(FIXTURES.glob(pat)))
        return out
    d = RAW / op
    return sorted(d.glob("*.xml")) if d.is_dir() else []


def load_op(op: str, use_fixtures: bool, files: dict | None = None,
            with_snapshots: bool = True) -> list[dict]:
    rows: list[dict] = []
    for p in _op_paths(op, use_fixtures, files):
        rows.extend(parse_xml(p))
    if with_snapshots and not use_fixtures:
        for p in snapshot_files(op):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, list):
                rows.extend([{k: ("" if v is None else str(v)) for k, v in r.items()}
                             for r in data if isinstance(r, dict)])
    return rows


def dedupe_rows(rows: list[dict], keys: tuple[str, ...]) -> tuple[list[dict], int]:
    """같은 키가 여러 파일에서 중복 수집된 경우 마지막 행만 남긴다(재수집 대비)."""
    seen: dict[tuple, dict] = {}
    for r in rows:
        k = tuple((r.get(x) or "").strip() for x in keys)
        seen[k] = r
    return list(seen.values()), len(rows) - len(seen)


def hosp_totals(use_fixtures: bool, files: dict | None = None) -> dict[str, int]:
    """hosp_list 응답의 totalCount(항목별 전체 기관 수)를 항목 코드별로 모은다.

    화면에서 '수집 932/932곳(전수)' 처럼 **수집 완료율을 정직하게** 표시하기 위한 값이다.
    """
    import sys
    sys.path.insert(0, str(BASE / "scripts"))
    from fetch_hira import parse_response  # noqa: E402
    totals: dict[str, int] = {}
    for p in _op_paths("hosp_list", use_fixtures, files):
        try:
            d = parse_response(p.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        if not d["items"]:
            continue
        code = (d["items"][0].get("npayCd") or "").strip()
        if code:
            totals[code] = max(totals.get(code, 0), d["total"])
    if not use_fixtures:
        # 스냅샷이 없으므로 여기서는 XML totalCount 만 쓴다(전 항목 수집 시 전부 채워짐).
        pass
    return totals


# ------------------------------------------------------------------ 정규화
def material_note(cmmt: str) -> dict:
    """cmmtTxt 는 943개 코드 중 1건만 값이 있다 → '확인됨'으로 표시하지 않는다.

    화면 문구는 `display` 를 그대로 쓴다. value 는 참/거짓 판정이 아니라 안내 문장이다.
    """
    text = (cmmt or "").strip()
    if not text:
        return {
            "included": None,
            "note": "치료재료·장비(1.5T/3.0T)·판독료 포함 여부는 병원마다 달라 방문 전 유선 확인이 필요합니다.",
            "basis": "cmmtTxt 없음(심평원 오픈API는 대부분 항목에 상세설명을 제공하지 않음)",
        }
    low = "미포함" if ("미포함" in text or "별도" in text) else ("포함" if "포함" in text else "")
    guided = ("치료재료·장비·판독료 조건이 달라질 수 있으므로 방문 전 유선 확인이 필요합니다.")
    if low == "미포함":
        note = "심평원 공개 상세설명상 치료재료가 별도입니다. " + guided
    elif low == "포함":
        note = "심평원 공개 상세설명상 치료재료가 포함입니다. " + guided
    else:
        note = "심평원 공개 상세설명이 있으나 포함 범위가 명시되지 않았습니다. " + guided
    return {"included": None, "note": note,
            "basis": "cmmtTxt: " + text[:120], "raw": text}


def _first(row: dict, *keys: str) -> str:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return ""


def normalize_codes(items: list[dict]) -> dict[str, dict]:
    """비급여 항목 코드 목록을 정규화한다.

    실응답 필드명은 `npayMdivCdNm` / `npaySdivCdNm` / `npayDtlDivCdNm` 이고
    `npayKorNm` 은 '중분류/소분류/상세분류' 경로 문자열이다(예: '자기공명영상진단료(MRI-기본검사)/뇌/일반').
    """
    out: dict[str, dict] = {}
    for r in items:
        code = (r.get("npayCd") or "").strip()
        if not code:
            continue
        kor = (r.get("npayKorNm") or "").strip()
        parts = [p.strip() for p in kor.split("/") if p.strip()]
        mid = _first(r, "npayMdivCdNm", "npayMdivNm") or (parts[0] if parts else "")
        sub = _first(r, "npaySdivCdNm", "npaySdivNm") or (parts[1] if len(parts) > 1 else "")
        dtl = _first(r, "npayDtlDivCdNm", "npayDtlDivNm") or (parts[2] if len(parts) > 2 else "")
        cmmt = (r.get("cmmtTxt") or "").strip()
        out[code] = {
            "code": code,
            "name": kor,
            "path": parts,
            "leaf": parts[-1] if parts else "",
            "mid": mid,
            "sub": sub,
            "dtl": dtl,
            "cmmt": cmmt,
            "material": material_note(cmmt),
            "valid_from": r.get("adtFrDd", ""),
            "valid_to": r.get("adtEndDd", ""),
        }
    return out


def _mode(values: list[int]) -> int | None:
    if not values:
        return None
    c = Counter(values)
    top = max(c.values())
    return min(v for v, n in c.items() if n == top)


def _is_out_of_scope(row: dict) -> bool:
    cl = (row.get("clCd") or "").strip()
    nm = (row.get("clCdNm") or "").strip()
    if cl in CLCD_OUT_OF_SCOPE:
        return True
    return any(k in nm for k in OUT_OF_SCOPE_NAMES)


def aggregate(hosp_rows: list[dict], item_code: str) -> dict:
    rows = []
    dropped = []
    for r in hosp_rows:
        if (r.get("npayCd") or "").strip() != item_code:
            continue
        cl = (r.get("clCd") or "").strip()
        if _is_out_of_scope(r):
            dropped.append({"ykiho": r.get("ykiho"), "clCd": cl,
                            "reason": "공개 범위 밖(의원급/기타)"})
            continue
        lo, hi = num(r.get("minPrc")), num(r.get("maxPrc"))
        if lo is None and hi is None:
            dropped.append({"ykiho": r.get("ykiho"), "clCd": cl, "reason": "금액 없음(0/공란)"})
            continue
        rows.append({
            "ykiho": r.get("ykiho", ""),
            "name": (r.get("yadmNm") or "").strip(),
            "clCd": cl,
            "clCdNm": (r.get("clCdNm") or "").strip() or CLCD.get(cl, ""),
            "sido": (r.get("sidoCdNm") or "").strip() or SIDO.get((r.get("sidoCd") or "").strip(), ""),
            "sggu": (r.get("sgguCdNm") or "").strip(),
            "min": lo,
            "max": hi if hi is not None else lo,
        })

    if not rows:
        return {"item": item_code, "n": 0, "price": None, "by_clcd": {}, "by_sido": {},
                "hospitals": [], "dropped": dropped}

    avgs = [round(((r["min"] or 0) + (r["max"] or 0)) / 2) for r in rows]
    allvals = [v for r in rows for v in (r["min"], r["max"]) if v]
    by_clcd: dict[str, dict] = {}
    for cl in sorted({r["clCdNm"] for r in rows if r["clCdNm"]}):
        sub = [r for r in rows if r["clCdNm"] == cl]
        vals = [((r["min"] or 0) + (r["max"] or 0)) // 2 for r in sub]
        by_clcd[cl] = {
            "n": len(sub),
            "avg": round(sum(vals) / len(vals)),
            "median": int(statistics.median(vals)),
            "min": min(r["min"] for r in sub if r["min"]),
            "max": max(r["max"] for r in sub if r["max"]),
        }
    by_sido: dict[str, dict] = {}
    for sd in sorted({r["sido"] for r in rows if r["sido"]}):
        sub = [r for r in rows if r["sido"] == sd]
        vals = [((r["min"] or 0) + (r["max"] or 0)) // 2 for r in sub]
        by_sido[sd] = {"n": len(sub), "avg": round(sum(vals) / len(vals)),
                       "median": int(statistics.median(vals))}

    return {
        "item": item_code,
        "n": len(rows),
        "price": {
            "min": min(allvals),
            "max": max(allvals),
            "avg": round(sum(avgs) / len(avgs)),
            "median": int(statistics.median(avgs)),
            "mode": _mode(avgs),
            "basis": "기관별 (최저+최고)/2 의 평균·중간·최빈",
        },
        "by_clcd": by_clcd,
        "by_sido": by_sido,
        "hospitals": sorted(rows, key=lambda r: (r["min"] or 0, r["name"]))[:60],
        "dropped": dropped,
        "all_rows": sorted(rows, key=lambda r: (r["min"] or 0, r["name"])),
    }


def normalize_stats(items: list[dict], kind: str) -> dict[str, dict]:
    """종별(clcd)·지역(sido) 통계 응답을 정규화한다.

    stdDate 는 **호출 당일**이 찍혀 오므로 데이터 기준일로 쓰지 않는다.
    """
    out = {}
    for r in items:
        code = (r.get("npayCd") or "").strip()
        if not code:
            continue
        rec = {"name": r.get("npayKorNm", "")}
        if kind == "clcd":
            for key, label in (("All", "전체"), ("Usgh", "상급종합"), ("Gnhp", "종합병원"),
                               ("Hosp", "병원"), ("Recu", "요양병원"), ("Dety", "치과병원"),
                               ("Cmdc", "한방병원")):
                vals = {
                    "Max": num(_first(r, f"prcMax{key}")),
                    "Min": num(_first(r, f"prcMin{key}")),
                    "Avg": num(_first(r, f"prcAvg{key}")),
                    "Middle": num(_first(r, f"middAvg{key}", f"prcMiddle{key}", f"prcMidd{key}")),
                }
                if any(v is not None for v in vals.values()):
                    rec[label] = vals
        else:
            for key, v in r.items():
                if key.startswith("prc") and key[3:].startswith(("Avg", "Max", "Min", "Middle")):
                    rec.setdefault("values", {})[key] = num(v)
        out[code] = rec
    return out


def load_kosis() -> dict | None:
    p = DATA / "kosis_2026.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ 데이터셋
def build(use_fixtures: bool) -> tuple[dict, dict, dict]:
    files = {
        "codes": ["codes_p1.xml"],
        "hosp_list": ["hosp_list_p1.xml", "hosp_list_p2.xml"],
        "hosp_dtl": ["hosp_dtl.xml"],
        "clcd": ["clcd.xml"],
        "sido": ["sido.xml"],
    }
    codes_raw = load_op("codes", use_fixtures, files)
    codes_raw, dup_codes = dedupe_rows(codes_raw, ("npayCd",))
    codes = normalize_codes(codes_raw)

    hosp_raw = load_op("hosp_list", use_fixtures, files)
    hosp_rows, dup_hosp = dedupe_rows(hosp_raw, ("npayCd", "ykiho"))

    clcd_raw = load_op("clcd", use_fixtures, files)
    clcd_raw, dup_clcd = dedupe_rows(clcd_raw, ("npayCd",))
    clcd = normalize_stats(clcd_raw, "clcd")
    sido = normalize_stats(load_op("sido", use_fixtures, files, with_snapshots=False), "sido")

    totals = hosp_totals(use_fixtures, files)
    catalog = json.loads((DATA / "catalog_items.json").read_text(encoding="utf-8"))["items"]
    kosis = None if use_fixtures else load_kosis()
    kosis_by_code = {k["code"]: k for k in (kosis or {}).get("items", [])}

    items_out = []
    hospitals_out: dict[str, list] = {}
    quality = {"checked": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
               "source": "fixtures" if use_fixtures else "raw",
               "issues": [], "counts": {}}

    for it in catalog:
        agg = aggregate(hosp_rows, it["code"])
        code_meta = codes.get(it["code"])
        has_data = agg["n"] > 0
        if use_fixtures:
            has_data = False
        total = totals.get(it["code"])
        cov = {"collected": agg["n"], "total": total,
               "complete": bool(total and agg["n"] >= total)}
        if has_data and total and agg["n"] < total:
            quality["issues"].append({"code": it["code"], "type": "partial_collection",
                                      "collected": agg["n"], "total": total})
        kk = kosis_by_code.get(it["code"])
        items_out.append({
            "code": it["code"],
            "slug": it["slug"],
            "name": it["name"],
            "payment": it["payment"],
            "special3": it["special3"],
            "excluded5": it["excluded5"],
            "official": {"mid": (code_meta or {}).get("mid") or it["official_mid"],
                         "sub": (code_meta or {}).get("sub") or it["official_sub"],
                         "dtl": (code_meta or {}).get("dtl") or it["official_dtl"]},
            "cmmt": (code_meta or {}).get("cmmt", ""),
            "material": (code_meta or {}).get("material") or material_note(""),
            "has_data": has_data,
            "stats": ({k: v for k, v in agg.items() if k != "all_rows"} if has_data else None),
            "coverage": cov,
            "kosis": kk,
            "raw_stats_preview": ({
                "n": agg["n"], "price": agg["price"], "by_clcd": agg["by_clcd"],
            } if (agg["n"] and use_fixtures) else None),
            "clcd_stats": clcd.get(it["code"]),
            "sido_stats": sido.get(it["code"]),
        })
        if has_data:
            hospitals_out[it["code"]] = [
                [r["name"], r["clCdNm"], r["sido"], r["sggu"], r["min"], r["max"]]
                for r in agg["all_rows"]]
        if agg["price"]:
            p = agg["price"]
            if p["min"] > p["max"]:
                quality["issues"].append({"code": it["code"], "type": "min_gt_max", "value": p})
            if p["avg"] and p["avg"] > 10_000_000:
                quality["issues"].append({"code": it["code"], "type": "suspiciously_high",
                                          "value": p["avg"]})
        if not code_meta:
            quality["issues"].append({"code": it["code"], "type": "code_not_in_api_list"})
        if agg["dropped"]:
            quality["issues"].append({"code": it["code"], "type": "rows_dropped",
                                      "n": len(agg["dropped"]),
                                      "reasons": sorted({d["reason"] for d in agg["dropped"]})})
        if not use_fixtures and not kk:
            quality["issues"].append({"code": it["code"], "type": "kosis_clinic_row_missing"})

    quality["warnings"] = [
        "getNonPaymentItemSidoCdList 는 2페이지 이후 504(SERVICETIMEOUT)로 전 항목 수집이 불가해 "
        "지역 통계는 getNonPaymentItemHospList2 기관 행의 sidoCdNm 으로 직접 집계했다(by_sido).",
        "getNonPaymentItemClcdList 는 응답이 35~44초로 느리고 자주 504가 나서, 같은 날 수집한 "
        "JSON 스냅샷(data/raw/snapshots/clcd_all.json, 714건)을 사용했다.",
        "cmmtTxt 는 943개 코드 중 1건만 값이 있어 치료재료 포함 여부를 API로 표시할 수 없다 → "
        "화면에는 '방문 전 유선 확인 필요'로 안내한다.",
        "stdDate 는 데이터 기준일이 아니라 호출 당일이 찍힌다 → 화면에 기준일로 쓰지 않는다.",
    ] if not use_fixtures else ["픽스처 모드: 실제 공개가가 아니므로 화면에 표시하지 않는다."]
    quality["counts"] = {
        "api_codes": len(codes),
        "clcd_codes": len(clcd),
        "hosp_list_rows": len(hosp_rows),
        "duplicate_rows_removed": {"codes": dup_codes, "hosp_list": dup_hosp, "clcd": dup_clcd},
        "items_in_catalog": len(catalog),
        "items_with_data": sum(1 for i in items_out if i["has_data"]),
        "items_without_data": sum(1 for i in items_out if not i["has_data"]),
        "hospital_rows_used": sum(i["stats"]["n"] for i in items_out if i["stats"]),
        "kosis_items": len(kosis_by_code),
    }

    dataset = {
        "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "source": "fixtures" if use_fixtures else "raw",
        "synthetic": bool(use_fixtures),
        "license": "건강보험심사평가원 비급여진료비정보서비스 · 공공누리 제1유형(출처표시)",
        "scope": "병원급 이상(상급종합·종합병원·병원·요양병원·정신병원·치과병원·한방병원)",
        "clinic_scope": "의원·치과의원·한의원은 API 공개 범위 밖 → KOSIS 통계표(승인번호 354006) 전국 평균·중간값만 참고 표기",
        "data_period": "건강보험심사평가원 2026년 비급여 공개 자료 기준(오픈API 조회 2026-11-17)",
        "kosis": (kosis or {}).get("meta"),
        "note": ("픽스처 모드: 수집·정제 경로 검증용 데이터입니다. 실제 공개 가격이 아니며 "
                 "사이트에는 표시되지 않습니다." if use_fixtures else
                 "실수집 데이터(data/raw + snapshots)에서 정제한 결과입니다."),
        "items": items_out,
    }
    summary = {
        "generated": dataset["generated"],
        "source": dataset["source"],
        "items_with_data": quality["counts"]["items_with_data"],
        "counts": quality["counts"],
        "per_item": [{"code": i["code"], "name": i["name"],
                      "n": (i["stats"] or {}).get("n", 0),
                      "coverage": i["coverage"],
                      "avg": ((i["stats"] or {}).get("price") or {}).get("avg"),
                      "kosis_avg": (i.get("kosis") or {}).get("avg"),
                      "displayed": i["has_data"]} for i in items_out],
    }
    hospitals = {
        "generated": dataset["generated"],
        "note": "기관별 [병원명, 종별, 시도, 시군구, 최저가, 최고가]. 병원급 이상 공개가만 포함하며 의원급은 없다.",
        "items": hospitals_out,
    }
    return dataset, quality, summary, hospitals


def main() -> int:
    ap = argparse.ArgumentParser(description="심평원 XML 정제 → hira_dataset.json")
    ap.add_argument("--fixtures", action="store_true", help="픽스처 XML 로 파이프라인 검증")
    args = ap.parse_args()

    dataset, quality, summary, hospitals = build(args.fixtures)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "hira_dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (DATA / "data_quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    (DATA / "hospitals.json").write_text(json.dumps(hospitals, ensure_ascii=False,
                                                    separators=(",", ":")), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if quality["issues"]:
        print(f"\n검증 이슈 {len(quality['issues'])}건 → data/data_quality.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
