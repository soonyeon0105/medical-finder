#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
심평원 비급여진료비정보조회서비스(공공데이터포털 15001700) 수집기

data.go.kr 인증키만 넣으면 실제 XML 을 그대로 내려받아 data/raw/ 에 보관한다.
정제(집계·검증)는 scripts/prepare_data.py 가 이어서 한다.

수집 오퍼레이션(엔드포인트는 data.go.kr 활용가이드 기준)
  1. getNonPaymentItemCodeList2      비급여 항목 코드 목록 (+ cmmtTxt: 치료재료·부가설명 문구)
  2. getNonPaymentItemHospList2      항목별 병원 목록(요약) — itemCd 필수, minPrc/maxPrc 포함
  3. getNonPaymentItemHospDtlList    기관별 상세 — ykiho 필수
  4. getNonPaymentItemClcdList       종별(상급종합·종합·병원·요양·치과·한방) 통계
  5. getNonPaymentItemSidoCdList     지역(17개 시도) 통계
  +) 병원기본목록(getHospBasisList)   ykiho·주소·전화 보강용(별도 활용신청 필요)

사용 예
  # 1) 키 설정(환경변수 또는 data/config.json)
  export HIRA_SERVICE_KEY='발급받은_인증키'
  python3 scripts/fetch_hira.py --op codes
  python3 scripts/fetch_hira.py --op hosp_list --items HE1010001,EB4410000
  python3 scripts/fetch_hira.py --op all

  # 2) 키 없이 파서·페이지네이션·에러 처리만 검증
  python3 scripts/fetch_hira.py --selftest

인증키는 로그·매니페스트에 남기지 않는다(마스킹).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
FIXTURE_DIR = BASE_DIR / "data" / "fixtures" / "xml"
CONFIG_FILE = BASE_DIR / "data" / "config.json"
ENV_FILE = BASE_DIR / ".env.local"          # 키 보관 위치(깃 제외). 다른 작업과 공유하는 규약

API_ROOT = "https://apis.data.go.kr/B551182/nonPaymentDamtInfoService"
HOSP_ROOT = "https://apis.data.go.kr/B551182/hospInfoServicev2"

KST = timezone(timedelta(hours=9))

# resultCode 안내문 (공공데이터포털 공통 코드)
RESULT_CODES = {
    "00": "정상",
    "01": "APPLICATION_ERROR — 요청 파라미터 오류",
    "02": "DB_ERROR",
    "03": "NODATA_ERROR — 조회 결과 없음",
    "04": "HTTP_ERROR",
    "05": "SERVICETIME_OUT",
    "10": "INVALID_REQUEST_PARAMETER_ERROR — 필수 파라미터 누락/형식 오류",
    "11": "NO_MANDATORY_REQUEST_PARAMETERS_ERROR",
    "12": "NO_OPENAPI_SERVICE_ERROR — 존재하지 않는 오퍼레이션",
    "20": "SERVICE_ACCESS_DENIED_ERROR — 활용신청 승인 전이거나 트래픽 초과",
    "21": "TEMPORARILY_DISABLE_THE_SERVICEKEY_ERROR",
    "22": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR — 일일 트래픽 초과",
    "30": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR — 등록되지 않은 인증키",
    "31": "DEADLINE_HAS_EXPIRED_ERROR — 활용기간 만료",
    "32": "UNREGISTERED_IP_ERROR",
    "33": "UNSIGNED_CALL_ERROR",
    "99": "UNKNOWN_ERROR",
}

OPS = {
    "codes": {"path": "/getNonPaymentItemCodeList2", "label": "비급여 항목 코드 목록",
              "params": [], "paged": True},
    "hosp_list": {"path": "/getNonPaymentItemHospList2", "label": "항목별 병원 목록(요약)",
                  "params": ["itemCd"], "paged": True},
    "hosp_dtl": {"path": "/getNonPaymentItemHospDtlList", "label": "기관별 상세",
                 "params": ["ykiho"], "paged": True},
    "clcd": {"path": "/getNonPaymentItemClcdList", "label": "종별 통계",
             "params": [], "paged": True},
    "sido": {"path": "/getNonPaymentItemSidoCdList", "label": "지역별 통계",
             "params": [], "paged": True},
    "hospitals": {"path": "/getHospBasisList", "label": "병원기본목록(ykiho 보강)",
                  "params": ["sidoCd"], "paged": True, "root": "hosp"},
}


class HiraError(RuntimeError):
    pass


@dataclass
class FetchResult:
    op: str
    params: dict
    ok: bool
    items: list = field(default_factory=list)
    total: int = 0
    pages: int = 0
    raw_files: list = field(default_factory=list)
    error: str | None = None
    result_code: str | None = None
    result_msg: str | None = None
    fetched_at: str = ""


# ------------------------------------------------------------------ 키·요청
def mask_key(key: str) -> str:
    if not key:
        return "(없음)"
    k = urllib.parse.unquote(key)
    return k[:4] + "*" * max(0, len(k) - 8) + k[-4:] if len(k) > 8 else "****"


def read_env_file(path: Path) -> dict:
    """KEY=VALUE 형식 .env 파일을 읽는다(주석·따옴표 허용). 값은 로그에 남기지 않는다."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("'").strip('"')
    return out


def load_key(cli_key: str | None) -> tuple[str | None, str]:
    """(키, 출처) 를 돌려준다. 출처는 마스킹된 상태로만 표시한다.

    우선순위: CLI → .env.local(DEC/ENC) → 환경변수 → data/config.json
    ENC(Encoding) 키는 이미 URL 인코딩된 형태이므로 그대로 쿼리에 넣는다.
    """
    if cli_key and cli_key.strip():
        return cli_key.strip(), "--service-key 인자"
    env_file = read_env_file(ENV_FILE)
    for name in ("DATA_GO_KR_SERVICE_KEY_DEC", "DATA_GO_KR_SERVICE_KEY_ENC",
                 "HIRA_SERVICE_KEY", "DATA_GO_KR_SERVICE_KEY"):
        if env_file.get(name):
            return env_file[name], f".env.local:{name}"
    for name in ("HIRA_SERVICE_KEY", "DATA_GO_KR_SERVICE_KEY",
                 "DATA_GO_KR_SERVICE_KEY_DEC", "DATA_GO_KR_SERVICE_KEY_ENC"):
        if os.environ.get(name):
            return os.environ[name].strip(), f"env:{name}"
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            key = (cfg.get("hira_service_key") or cfg.get("service_key") or "").strip()
            if key:
                return key, "data/config.json"
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {CONFIG_FILE} 를 읽지 못했습니다: {exc}", file=sys.stderr)
    return None, "없음"


def build_url(op: str, params: dict, key: str, rows: int, page: int,
              root: str | None = None) -> str:
    meta = OPS[op]
    base = HOSP_ROOT if (meta.get("root") or root) == "hosp" else API_ROOT
    q = {"serviceKey": key, "pageNo": str(page), "numOfRows": str(rows), "_type": "xml"}
    q.update({k: str(v) for k, v in params.items() if v not in (None, "")})
    return f"{base}{meta['path']}?{urllib.parse.urlencode(q, safe='%')}"


def http_get(url: str, timeout: int = 30, retries: int = 3) -> bytes:
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "medical-finder/0.3 (HIRA nonPayment collector)",
                "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return data
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read()
            except Exception:  # noqa: BLE001
                pass
            # 인증 오류는 XML 본문에 코드가 담겨 온다 → 재시도 없이 그대로 넘긴다
            if exc.code in (400, 401, 403):
                return body
            last = f"HTTP {exc.code}: {body[:200]!r}"
        except Exception as exc:  # noqa: BLE001 (URLError, timeout 등)
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(1.5 * attempt)
    raise HiraError(f"요청 실패({retries}회): {last}")


# ------------------------------------------------------------------ XML 파싱
def _text(node) -> str:
    return (node.text or "").strip() if node is not None else ""


def parse_response(xml_bytes: bytes) -> dict:
    """공공데이터포털 표준 응답을 파싱한다.

    반환: {"result_code","result_msg","total","page","rows","items":[dict,...]}
    items 의 각 항목은 태그명을 그대로 키로 쓴다(스키마가 오퍼레이션마다 다름).
    """
    if not xml_bytes:
        raise HiraError("빈 응답")
    head = xml_bytes[:400].lstrip()
    if head[:1] not in (b"<", b"\xef"):     # BOM 등
        if head[:1] in (b"{", b"["):
            raise HiraError("JSON 응답을 받았습니다(XML 아님). _type=xml 파라미터를 확인하세요.")
        raise HiraError(f"XML 로 보이지 않는 응답: {xml_bytes[:160]!r}")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise HiraError(f"XML 파싱 실패: {exc} · {xml_bytes[:200]!r}") from exc

    # 게이트웨이 오류 응답(OpenAPI_ServiceResponse/cmmMsgHeader) 처리
    if root.tag == "OpenAPI_ServiceResponse" or root.find("cmmMsgHeader") is not None:
        hdr = root.find("cmmMsgHeader")
        reason = _text(hdr.find("returnReasonCode")) if hdr is not None else ""
        auth = _text(hdr.find("returnAuthMsg")) if hdr is not None else ""
        err = _text(hdr.find("errMsg")) if hdr is not None else ""
        return {"result_code": reason or "99", "result_msg": f"{auth} {err}".strip(),
                "total": 0, "page": 1, "rows": 0, "items": []}

    def find_text(*names: str) -> str:
        node = root
        for name in names:
            nxt = node.find(name)
            if nxt is None:
                return ""
            node = nxt
        return _text(node)

    code = find_text("header", "resultCode") or find_text("resultCode") or "00"
    msg = find_text("header", "resultMsg") or find_text("resultMsg")
    total = find_text("body", "totalCount") or find_text("totalCount")
    page = find_text("body", "pageNo") or find_text("pageNo")
    rows = find_text("body", "numOfRows") or find_text("numOfRows")

    items = []
    container = root.find("body/items")
    if container is not None:
        for item in container.findall("item"):
            row = {}
            for child in item:
                row[child.tag] = _text(child)
            if row:
                items.append(row)
    else:
        # 일부 오퍼레이션은 item 이 최상위에 바로 붙는다
        for item in root.findall("item"):
            items.append({child.tag: _text(child) for child in item})

    return {
        "result_code": code or "00",
        "result_msg": msg,
        "total": int(total) if str(total).isdigit() else len(items),
        "page": int(page) if str(page).isdigit() else 1,
        "rows": int(rows) if str(rows).isdigit() else len(items),
        "items": items,
    }


def check_result(parsed: dict) -> None:
    code = parsed["result_code"]
    if code not in ("00", "03"):        # 03 NODATA 는 정상 흐름으로 취급
        hint = RESULT_CODES.get(code, "알 수 없는 코드")
        raise HiraError(f"resultCode {code} ({hint}) · {parsed['result_msg']}")


# ------------------------------------------------------------------ 수집
def fetch_op(op: str, key: str, params: dict | None = None, rows: int = 100,
             max_pages: int = 200, out_dir: Path | None = None,
             dry_run: bool = False, sleep: float = 0.15,
             timeout: int = 30, retries: int = 3) -> FetchResult:
    meta = OPS[op]
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    missing = [p for p in meta["params"] if not params.get(p)]
    if missing:
        raise HiraError(f"{op}: 필수 파라미터 누락 {missing}")

    result = FetchResult(op=op, params=params, ok=False,
                         fetched_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"))
    out_dir = out_dir or RAW_DIR / op
    out_dir.mkdir(parents=True, exist_ok=True)

    page = 1
    while page <= max_pages:
        url = build_url(op, params, key, rows, page)
        if dry_run:
            print("DRY-RUN", url.replace(key, mask_key(key)), flush=True)
            return FetchResult(op, params, True, [], 0, 0, error="dry-run")
        try:
            body = http_get(url, timeout=timeout, retries=retries)
        except HiraError as exc:
            result.error = f"{exc} (timeout={timeout}s, retries={retries})"
            raise HiraError(f"{op}: {result.error}") from exc
        parsed = parse_response(body)
        try:
            check_result(parsed)
        except HiraError as exc:
            result.error = str(exc)
            result.result_code = parsed["result_code"]
            result.result_msg = parsed["result_msg"]
            raise

        stamp = datetime.now(KST).strftime("%Y%m%dT%H%M%S")
        suffix = "_".join(f"{k}-{v}".replace("/", "-") for k, v in params.items())
        name = f"{op}_{suffix}_{stamp}_p{page}.xml" if suffix else f"{op}_{stamp}_p{page}.xml"
        path = out_dir / name
        path.write_bytes(body)
        result.raw_files.append(str(path.relative_to(BASE_DIR)))

        result.items.extend(parsed["items"])
        result.total = parsed["total"]
        result.result_code, result.result_msg = parsed["result_code"], parsed["result_msg"]
        result.pages = page

        if not parsed["items"] or len(result.items) >= parsed["total"]:
            break
        if parsed["total"] <= parsed["rows"]:
            break
        page += 1
        time.sleep(sleep)

    result.ok = True
    return result


def fetch_catalog_codes(rows: int = 1000) -> list[str]:
    try:
        data = json.loads((BASE_DIR / "data" / "catalog_items.json").read_text(encoding="utf-8"))
        return [it["code"] for it in data["items"]]
    except Exception:  # noqa: BLE001
        return []


def write_manifest(results: list[FetchResult], key: str) -> Path:
    path = RAW_DIR / "manifest.json"
    prev = []
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8")).get("runs", [])
        except Exception:  # noqa: BLE001
            prev = []
    run = {
        "run_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "service_key": mask_key(key),
        "ops": [{
            "op": r.op, "params": r.params, "ok": r.ok, "items": len(r.items),
            "total": r.total, "pages": r.pages, "result_code": r.result_code,
            "result_msg": r.result_msg, "error": r.error, "raw_files": r.raw_files,
            "fetched_at": r.fetched_at,
        } for r in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runs": (prev + [run])[-20:]}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


# ------------------------------------------------------------------ 자체 검증
def selftest() -> int:
    """내장 XML 픽스처로 파서·페이지네이션·에러 처리를 키 없이 검증한다."""
    print("== selftest: XML 파서 / 에러 처리")
    fails = []

    def ok(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + (f" · {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    codes_path = FIXTURE_DIR / "codes_p1.xml"
    parsed = parse_response(codes_path.read_bytes())
    ok("codes: resultCode 00", parsed["result_code"] == "00", parsed["result_code"])
    ok("codes: 항목 5건 파싱", len(parsed["items"]) == 5, str(len(parsed["items"])))
    ok("codes: totalCount 5", parsed["total"] == 5, str(parsed["total"]))
    cmmt = [i.get("cmmtTxt", "") for i in parsed["items"]]
    ok("codes: cmmtTxt 추출", any("치료재료" in c for c in cmmt), cmmt[0][:30])

    p1 = parse_response((FIXTURE_DIR / "hosp_list_p1.xml").read_bytes())
    p2 = parse_response((FIXTURE_DIR / "hosp_list_p2.xml").read_bytes())
    ok("hosp_list: 1페이지 3건", len(p1["items"]) == 3, str(len(p1["items"])))
    ok("hosp_list: totalCount 5", p1["total"] == 5, str(p1["total"]))
    ok("hosp_list: 2페이지 이어받기", len(p1["items"]) + len(p2["items"]) == 5,
       f"{len(p1['items'])}+{len(p2['items'])}")
    ok("hosp_list: minPrc/maxPrc 필드", p1["items"][0].get("minPrc") == "120000"
       and p1["items"][0].get("maxPrc") == "260000", p1["items"][0])

    clcd = parse_response((FIXTURE_DIR / "clcd.xml").read_bytes())
    ok("clcd: 종별 통계 파싱", len(clcd["items"]) == 1 and "prcAvgAll" in clcd["items"][0],
       str(list(clcd["items"][0])[:6]))
    sido = parse_response((FIXTURE_DIR / "sido.xml").read_bytes())
    ok("sido: 지역 통계 파싱", len(sido["items"]) == 1 and "prcAvgKyg" in sido["items"][0],
       str([k for k in sido["items"][0] if k.startswith("prcAvg")][:4]))

    err = parse_response((FIXTURE_DIR / "error_not_registered.xml").read_bytes())
    try:
        check_result(err)
        ok("error: 미등록 키 예외", False)
    except HiraError as exc:
        ok("error: 미등록 키 예외", "30" in str(exc) and "등록되지 않은" in str(exc), str(exc)[:60])

    nodata = parse_response((FIXTURE_DIR / "nodata.xml").read_bytes())
    try:
        check_result(nodata)
        ok("nodata(03)은 예외 아님", True, nodata["result_msg"])
    except HiraError as exc:
        ok("nodata(03)은 예외 아님", False, str(exc))

    ok("키 마스킹", mask_key("abcd1234efgh5678").endswith("5678")
       and "*" in mask_key("abcd1234efgh5678"), mask_key("abcd1234efgh5678"))

    page2 = parse_response((FIXTURE_DIR / "127_empty_body.xml").read_bytes())
    ok("빈 items 응답 처리", page2["items"] == [], str(page2["items"]))

    # URL 조립(키 인코딩 유지)
    u = build_url("hosp_list", {"itemCd": "HE1010001"}, "KEY%2Bwith%3Dchars", 100, 2)
    ok("URL: itemCd·pageNo 포함", "itemCd=HE1010001" in u and "pageNo=2" in u and "_type=xml" in u, u[:70])

    print(f"\nselftest {len(fails)}건 실패" if fails else "\nselftest 모두 통과")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="심평원 비급여 API 수집기")
    ap.add_argument("--op", default="codes",
                    choices=sorted(OPS) + ["all"])
    ap.add_argument("--service-key", default=None, help="data.go.kr 인증키(미지정 시 env/config)")
    ap.add_argument("--items", default="", help="hosp_list 대상 항목 코드(쉼표 구분)")
    ap.add_argument("--ykiho", default="", help="hosp_dtl 대상 요양기관기호(쉼표 구분)")
    ap.add_argument("--sido", default="", help="hospitals:: 시도 코드")
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true", help="URL 만 확인(요청하지 않음)")
    ap.add_argument("--timeout", type=int, default=30, help="요청 타임아웃(초)")
    ap.add_argument("--retries", type=int, default=3, help="재시도 횟수")
    ap.add_argument("--selftest", action="store_true", help="내장 XML 로 파서 검증(키 불필요)")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    key, source = load_key(args.service_key)
    if not key:
        print("인증키가 없습니다.\n"
              "  work/medical-finder/.env.local 에 DATA_GO_KR_SERVICE_KEY_DEC=_발급키_ 형태로 저장하거나\n"
              "  export HIRA_SERVICE_KEY='발급키' / data/config.json {\"hira_service_key\": \"...\"}\n"
              "  (키 없이 파서만 확인하려면: --selftest)", file=sys.stderr)
        return 2
    print(f"인증키: {mask_key(key)} (출처: {source})", flush=True)

    results: list[FetchResult] = []
    try:
        if args.op in ("codes", "all"):
            results.append(fetch_op("codes", key, None, args.rows, args.max_pages,
                                    dry_run=args.dry_run, timeout=args.timeout,
                                    retries=args.retries))
        if args.op in ("clcd", "all"):
            results.append(fetch_op("clcd", key, None, args.rows, args.max_pages,
                                    dry_run=args.dry_run, timeout=args.timeout,
                                    retries=args.retries))
        if args.op in ("sido", "all"):
            results.append(fetch_op("sido", key, None, args.rows, args.max_pages,
                                    dry_run=args.dry_run, timeout=args.timeout,
                                    retries=args.retries))
        if args.op in ("hosp_list", "all"):
            codes = [c.strip() for c in args.items.split(",") if c.strip()]
            if not codes:
                codes = fetch_catalog_codes()
            print(f"hosp_list 대상 항목 {len(codes)}개")
            for code in codes:
                results.append(fetch_op("hosp_list", key, {"itemCd": code}, args.rows,
                                        args.max_pages, dry_run=args.dry_run))
        if args.op in ("hosp_dtl",) or (args.op == "all" and args.ykiho):
            for yk in [y.strip() for y in args.ykiho.split(",") if y.strip()]:
                results.append(fetch_op("hosp_dtl", key, {"ykiho": yk}, args.rows,
                                        args.max_pages, dry_run=args.dry_run))
        if args.op == "hospitals":
            results.append(fetch_op("hospitals", key, {"sidoCd": args.sido} if args.sido else {},
                                    args.rows, args.max_pages, dry_run=args.dry_run))
    except HiraError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        if results:
            write_manifest(results, key)
        return 1

    if not args.dry_run:
        man = write_manifest(results, key)
        print(f"매니페스트: {man.relative_to(BASE_DIR)}")
        for r in results:
            print(f"  {r.op:<10} {len(r.items):>6}건 / total {r.total:<6} pages {r.pages}"
                  + (f"  [{r.error}]" if r.error else ""))
        print("\n다음 단계: python3 scripts/prepare_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
