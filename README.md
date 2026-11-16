# 🏥 메디컬·비급여 시세 비교 파인더 — M-04 실데이터 · KOSIS 연동 · 라이브 빌드

병원급 이상 **심평원 공개 비급여 가격**(전수 수집)과 **1~5세대 실손 보장액**을 한 화면에서 계산하고,
**통계청 KOSIS(승인번호 354006) 의원급 통계**를 참고값으로 함께 보여 주는 정적 사이트입니다.
2026-05-06 출시된 **5세대 실손**(중증 특약1 / 비중증 특약2)과 2026-07-01 시행
**도수치료 관리급여(1회 43,850원 · 본인부담 95%)**를 계산에 반영했습니다.

- 라이브 도메인(배포 예정): `https://medical-finder.pages.dev` — 빌드 시 `--base` 로 교체
- 정적 산출물: `dist/` (Cloudflare Pages 가 빌드 커맨드 없이 이 폴더를 그대로 서빙)

## 이번 단계에서 실제로 수집한 데이터 (2026-11-17)

| 오퍼레이션 | 결과 | 비고 |
| --- | --- | --- |
| `getNonPaymentItemCodeList2` | **943/943건** | 항목 코드·공식 분류·`cmmtTxt` |
| `getNonPaymentItemHospList2` | **13,650행 / 13개 항목** | 항목별 `totalCount` 와 일치(수집률 100%) |
| `getNonPaymentItemClcdList` | **714/714건** | 응답 35~44초·재호출 504 → 같은 날 JSON 스냅샷 사용 |
| `getNonPaymentItemSidoCdList` | 사용 안 함 | 2페이지부터 504 → 기관 행의 `sidoCdNm` 으로 직접 집계 |
| KOSIS 354006 (의원·치과의원) | **13개 항목** | 통계표 직접다운로드(CSV·UTF-8), 로그인·API키 불필요 |

항목별 수집 기관 수(전수): 뇌 MRI 932 · 경추 MRI 1,055 · 요천추 MRI 1,055 · 무릎 MRI 1,059 ·
복부 초음파 683 · 유방 초음파 900 · 갑상선 초음파 1,304 · 진정내시경 환자관리료 Ⅰ 339 ·
지르코니아 임플란트 420 · 체외충격파 1,804 · 증식치료(사지) 1,141 · 도수치료 1,617 · 신장분사치료 1,341

## 구조

```
work/medical-finder/
├─ data/
│  ├─ catalog_items.json      핵심 13개 항목 카탈로그(코드·공식 분류·5세대 처리)
│  ├─ kosis_2026.json         KOSIS 의원·치과의원 통계표에서 직접 수집한 참고값(코드↔분류 경로 확정)
│  ├─ hira_dataset.json       prepare_data.py 산출물(항목별 시세·종별/시도 집계·커버리지)
│  ├─ hospitals.json          항목별 병원급 기관 목록(시도/종별 필터용 경량 JSON)
│  ├─ data_quality.json       정제 검증 결과   ·  summary.json  사람이 읽는 요약
│  ├─ raw/                    수집 원본(fetch_hira.py) + 스냅샷(깃 제외)
│  └─ fixtures/xml/           키 없이 파서·페이지네이션을 검증하는 응답 픽스처
├─ scripts/
│  ├─ fetch_hira.py           data.go.kr 15001700 XML 수집기(+ --selftest)
│  ├─ prepare_data.py         정제·집계·검증 → hira_dataset.json / hospitals.json
│  ├─ calc_engine.py          1~5세대 실손 + 관리급여 계산 엔진(Python 기준 구현)
│  ├─ build_site.py           정적 사이트 빌드(dist/)
│  ├─ crosscheck_calc.py      Python↔JS 전수 교차검증
│  ├─ qa_check.py             정적 검사(--live: 비밀값·제4유형·의원 개별명 미포함 포함)
│  ├─ verify_site.py          Playwright 렌더 검수 + 스크린샷(--live)
│  └─ _browser.py             헤드리스 크로미움 라이브러리 경로 보정
├─ assets/  calc.js · app.js · style.css
└─ dist/    빌드 산출물 (ko/index, ko/calc, ko/items, ko/items/{slug}, ko/insurance, ko/guide, ko/privacy, 404.html)
```

## 실행

```bash
cd work/medical-finder

# 0) 인증키는 .env.local 에만 둔다(깃 제외). 형식: DATA_GO_KR_SERVICE_KEY_DEC=발급키
python3 scripts/fetch_hira.py --op codes --rows 1000
python3 scripts/fetch_hira.py --op hosp_list --rows 300            # 카탈로그 13개 항목 전수
python3 scripts/prepare_data.py                                   # → data/hira_dataset.json, hospitals.json

python3 scripts/build_site.py --live --base https://medical-finder.pages.dev   # → dist/
python3 scripts/qa_check.py --live                                # 정적 검사
python3 scripts/crosscheck_calc.py                                # Python↔JS 전수 교차검증
MED_SHOTS_DIR=/workspace/downloads/medical-mvp python3 scripts/verify_site.py --live
```

`--live` 없이 빌드하면 프리뷰 모드(배너 + `noindex` + `robots Disallow`)가 되고,
`--live` 빌드에서만 배너·noindex 가 사라지고 `robots.txt` 가 색인을 허용합니다.

### KOSIS 의원급 통계를 다시 받는 방법

1. <https://kosis.kr/common/meta_onedepth.jsp?vwcd=MT_OTITLE&listid=354_001_004_001>
2. `의원 비급여 진료비용`(표 `DT_354006_2021A016`) / `치과의원 비급여 진료비용`(`DT_354006_2021A018`)
   → **직접파일 다운로드** → CSV · UTF-8 · 시점 2026 → 다운로드 (로그인·API키 불필요)
3. 통계표 조회화면의 3단 분류(진료비용별(1)(2)(3))로 항목을 대조한다.
   CSV 직접다운로드는 (3)단만 남아 상위 분류를 잃으므로, 코드↔경로 확정은 조회화면에서 한다.
4. 결과를 `data/kosis_2026.json` 형식으로 옮긴다(값은 KOSIS 표기 그대로, 추정·보간 금지).

## 검증 결과 (2026-11-17, 라이브 빌드 기준)

| 검사 | 결과 |
| --- | --- |
| `crosscheck_calc.py` | 엔진 16,176건 × 5세대 × 6항목 = **485,280개 값 불일치 0** + 화면 표본 48건(720값) 일치 |
| `qa_check.py --live` | 범위 고지·프리뷰 배너/ noindex 부재·JSON-LD·canonical·내부 링크·sitemap 37개·골든 15케이스·**지역 페이지 17개 전수**·비밀값 0·제4유형 엑셀 0·의원 개별 기관 0 전부 통과 |
| `verify_site.py --live` | 모바일 390px(innerWidth 390 확인)·데스크톱 1440px **86/86 통과**, 콘솔 오류 0, 가로 스크롤 0, 기관 필터(시도·종별·검색)·지역 필터(항목·시군구) 동작 확인 |
| `fetch_hira.py --selftest` | XML 파서·페이지네이션·게이트웨이 오류(30)·NODATA·빈 응답·키 마스킹 통과 |

스크린샷: `/workspace/downloads/medical-mvp/m04-*.png` (모바일 390 / 데스크톱 1440)

## 화면

- `/ko/` — 계산기 + 병원급↔의원급(KOSIS) 비교표 + 13개 항목
- `/ko/calc/` — 계산기 전체 옵션(입원/통원·종별·중증·2세대 유형·관리급여 횟수)
- `/ko/items/`, `/ko/items/{slug}/` — 항목별 시세(종별·시도) + KOSIS 의원급 참고 카드 + **기관별 공개가 필터**
- `/ko/regions/`, `/ko/regions/{sido}/` — **17개 시·도별 비급여 시세**(항목별 평균·중간값·최저~최고·전국 대비, 종별 분포, 시·군·구 시세)
  + 지역 한정 **기관·항목별 공개가 검색**(항목·시·군·구·병원명 필터)
- `/ko/insurance/` — 1~5세대 실손 정리(5세대 특약1·2, 도수치료 관리급여)
- `/ko/guide/` — 수집 구조·라이선스·수집 상태
- `/ko/privacy/` — 개인정보처리방침 · 면책 고지 · 데이터 출처
- `/404.html`

## 방문 통계 (GA4 · Cloudflare)

- **GA4**: 측정 ID `G-9EQ04J49YZ` — 모든 페이지 `<head>` 에 `gtag.js` + `gtag('config', …, { anonymize_ip: true })`.
- **이벤트**: `calc_use`(계산기 첫 조작: 항목·입원/통원·종별·급여구분), `hospital_filter`(기관 목록 시도·종별 필터),
  `item_view`(항목 상세 조회, `item_slug`). 금액·개인 입력값은 전송하지 않는다.
- **고지**: `/ko/privacy/` 4항(쿠키·방문 통계)과 FAQ 에 수집 항목·쿠키(`_ga`)·거부 방법을 명시.
- **Cloudflare Web Analytics**: 비콘은 Cloudflare Pages 프로젝트 설정에서 자동 삽입(코드 미포함).

## 데이터·법적 경계 (지킨 것)

- **인증키**: `.env.local` 에만 보관, 코드·HTML·JSON·마크다운·로그·커밋에 원문 0건(`qa_check.py` 가 검사).
- **공공누리 제4유형 엑셀은 사용하지 않음**: 규모별·시도별 의원급 통계는 통계청 KOSIS 공개 통계표에서만 수집.
- **의원급 개별 가격·기관명은 표시하지 않음**: 공개 API 는 병원급 이상만 제공하며,
  의원급은 KOSIS **전국 규모 통계(평균·중간·최저·최고)** 만 참고값으로 표기.
- **좌표·지도 핀 미노출**: 병원정보서비스의 `XPos`/`YPos` 는 쓰지 않는다(위치기반서비스사업 신고 전 보류).
- **`cmmtTxt` 한계**: 943개 코드 중 1건만 값이 있어 치료재료·장비·판독료 포함 여부를 단정하지 않고
  "병원마다 달라 방문 전 유선 확인"으로 안내.
- **`stdDate` 주의**: 통계 응답의 `stdDate` 는 **호출 당일**이 찍히므로 데이터 기준일로 쓰지 않는다.
  화면 표기는 "건강보험심사평가원 2026년 비급여 공개 자료 기준 · 오픈API 조회 2026-11-17".
- **의료법 제27조**: 기관 목록은 공개가 순 나열이며 추천·순위·예약·상담 알선이 아니다.

## 알려진 제약

- `getNonPaymentItemSidoCdList` 는 2페이지부터 504 → 지역 집계는 기관 행에서 직접 계산(전남광주 통합 표기).
- `getNonPaymentItemClcdList` 는 35~44초 소요·간헐 504 → 스냅샷(`data/raw/snapshots/`)을 사용하며,
  치과·한방·요양병원 열이 없어 종별 집계는 기관 행 기준이 더 정확하다.
- 도수치료(`MX1220000`)의 병원급·의원급 공개가는 **2026-07-01 관리급여 전환 전 비급여 신고가**가 섞여 있어
  화면 상단에 전환 고지와 시점 차이를 명시하고, 계산은 급여 수가 43,850원으로 한다.
- 도수치료 관리급여 주기(주 2회·연 15회/예외 24회)는 누적 관리가 필요해 안내로만 표시.
- 상업 게시 전 심평원과의 사전 협의가 필요한 항목(의원급)은 계속 제외한다.
