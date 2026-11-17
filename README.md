# 🏥 메디컬·비급여 시세 비교 파인더 — M-07 항목 확장(20개) · KOSIS 연동 · 라이브 빌드

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
| `getNonPaymentItemHospList2` | **17,932행 / 20개 항목** | 항목별 `totalCount` 와 일치(수집률 100%) |
| `getNonPaymentItemClcdList` | **714/714건** | 응답 35~44초·재호출 504 → 같은 날 JSON 스냅샷 사용 |
| `getNonPaymentItemSidoCdList` | 사용 안 함 | 2페이지부터 504 → 기관 행의 `sidoCdNm` 으로 직접 집계 |
| KOSIS 354006 (의원·치과의원) | **20개 항목** | 통계표 조회화면에서 값 대조(로그인·API키 불필요) |

항목별 수집 기관 수(전수, 17,932행): 뇌 MRI 932 · 경추 MRI 1,055 · 요천추 MRI 1,055 · 무릎 MRI 1,059 ·
복부 초음파 683 · 유방 초음파 900 · 갑상선 초음파 1,304 · 진정내시경 환자관리료 Ⅰ 339 ·
지르코니아 임플란트 420 · 체외충격파 1,804 · 증식치료(사지) 1,141 · 도수치료 1,617 · 신장분사치료 1,341 ·
**백내장 다초점 인공수정체 72 · 지르코니아 크라운 458 · PFM 크라운 428 · 라식 26 · 대상포진 예방접종 1,345 ·
진정내시경 환자관리료 Ⅱ 1,011 · Ⅲ 942**

### 세대별 보장 제외 (`excluded_gens`)

카탈로그의 `excluded_gens` 가 그 세대의 계산을 0원(전액 본인부담)으로 만든다. 표준 실손약관의
시력교정술·예방접종·치과 비급여 보철 제외 문언을 반영한 것으로, `calc_engine.py` 와 `assets/calc.js` 가 같은 규칙을 쓴다.

| 항목 | 보장 제외 세대 | 근거 |
| --- | --- | --- |
| 라식 | 1~5세대 | 시력교정술(미용·생활 편의) 면책 |
| 대상포진 예방접종 | 1~5세대 | 예방 목적 — 질병 치료 목적 아님 |
| 지르코니아·PFM 크라운, 지르코니아 임플란트 | 1~5세대 | 치과치료(K00~K08) 비급여 보장 제외 |
| 백내장 다초점 인공수정체 | 2~5세대 | 2016.1 이후 약관의 시력교정술 면책(다초점 렌즈를 안경 대체로 봄) |

## 구조

```
work/medical-finder/
├─ data/
│  ├─ catalog_items.json      비급여 20개 항목 카탈로그(코드·공식 분류·세대별 보장 제외)
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
python3 scripts/fetch_hira.py --op hosp_list --rows 300            # 카탈로그 20개 항목 전수
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
| `crosscheck_calc.py` | 엔진 24,240건 × 5세대 × 6항목 = **727,200개 값 불일치 0** + 화면 표본 48건(720값) 일치 |
| `qa_check.py --live` | 범위 고지·프리뷰 배너/ noindex 부재·JSON-LD·canonical·내부 링크·sitemap 37개·골든 15케이스·**지역 페이지 17개 전수**·비밀값 0·제4유형 엑셀 0·의원 개별 기관 0 전부 통과 |
| `verify_site.py --live` | 모바일 390px(innerWidth 390 확인)·데스크톱 1440px **86/86 통과**, 콘솔 오류 0, 가로 스크롤 0, 기관 필터(시도·종별·검색)·지역 필터(항목·시군구) 동작 확인 |
| `fetch_hira.py --selftest` | XML 파서·페이지네이션·게이트웨이 오류(30)·NODATA·빈 응답·키 마스킹 통과 |

스크린샷: `/workspace/downloads/medical-mvp/m04-*.png`(기존) · `m07-*.png`(신규 항목 20개 확장)

## 화면

- `/ko/` — 계산기 + 병원급↔의원급(KOSIS) 비교표 + 20개 항목
- `/ko/calc/` — 계산기 전체 옵션(입원/통원·종별·중증·2세대 유형·관리급여 횟수)
- `/ko/items/`(20개), `/ko/items/{slug}/` — 항목별 시세(종별·시도) + KOSIS 의원급 참고 카드 + **기관별 공개가 필터** + 세대별 보장 제외 표시
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

---

## QA 확정 버그 수정 (2026-11-17 17:20) — 루트 301 · 조사 · 계산기 금액 경계

`T-M04_라이브_교차QA_v1`의 M-01~M-03을 반영하고 Cloudflare Pages `medical-finder-kr` 프로덕션에 재배포했습니다
(커밋 `3f2e57a`, 배포 zip `work/medical-finder-dist-qafix-20261117.zip` 62파일).

| 항목 | 변경 |
| --- | --- |
| M-01 | `dist/_redirects` 에 `/ /ko/ 301` — 라이브 빌드에서만 생성. Pages는 자산보다 redirect를 먼저 적용하므로 `dist/index.html`(직접 요청·no-JS 대비)이 남아 있어도 `/`는 HTTP 301. 라이브 `curl -I https://medical-finder-kr.pages.dev/` → `301`, `Location: /ko/`, `/ko/` 200. |
| M-02 | 항목 상세 20페이지 `470,000원로` → `470,000원으로`(`원`은 받침 ㄴ → 항상 `으로`). `qa_check.py` 에 `원로`·`원 로` 0건 검사 추가. |
| M-03 | 금액 입력을 숫자만 추려 변환하던 동작 제거 — `-1000`을 `1000`으로 바꾸지 않는다. 0·빈 값·음수면 계산하지 않고 입력란 아래 `role="alert"` 안내(`금액은 0보다 큰 값으로 입력해 주세요.`) + 결과 표는 안내 한 줄. 5억 원 초과는 `#result-warnings`에 자릿수 오타 확인 경고. |

검증: `qa_check.py --live` 48페이지 전항 통과 / `crosscheck_calc.py` 엔진 24,240건×5세대×6항목 = 727,200값 불일치 0 +
화면 표본 37건 일치(0원 케이스는 안내 노출 확인) / `verify_site.py --live` 95/95 통과·콘솔 오류 0·가로 스크롤 0 /
라이브 sitemap 48 URL 전수 200·`/ko/`·`/ko/calc/`·`/ko/items/*` 200·404 정상·GA4 `G-9EQ04J49YZ` 유지.
스크린샷: `downloads/medical-mvp/qa-fix-medical-finder-amount-zero.png`·`-amount-negative.png`·`-amount-overcap.png`

> 재배포 시: `python3 scripts/build_site.py --live --base https://medical-finder-kr.pages.dev` → `qa_check.py --live` →
> `dist/` 루트만 zip → Cloudflare Pages `medical-finder-kr` → 배포 생성 → 업로드(62파일 확인) → 저장 및 배포.

---

## SEO 해설 가이드 8편 (2026-11-18) — T-M12 5편 + T-M12-B 3편

`/ko/guide/<slug>/` 아래에 한국어 해설 가이드 8편을 추가하고 `/ko/guide/` 를 가이드 허브로 통합했습니다
(기존 '이용 안내 · 데이터 출처' 내용은 허브 하단에 그대로 유지). 본문 원본은 `scripts/guides.py`,
렌더링은 `build_site.page_guide_article()` 입니다.

| 편 | 슬러그 | 주제 |
| --- | --- | --- |
| 01 | `silson-1-5-generation-guide` | 1~5세대 실손보험 비교·선택 |
| 02 | `how-to-read-noncovered-prices` | 비급여 진료비 시세 읽는 법 |
| 03 | `managed-benefit-95-calculator-guide` | 관리급여 본인부담 95% 계산기 사용법 |
| 04 | `regional-noncovered-price-differences` | 지역별 비급여 가격 차이와 비교 주의점 |
| 05 | `silson-claim-process-guide` | 실손보험 청구 절차·서류 |
| 06 | `mri-ultrasound-covered-vs-noncovered` | MRI·초음파 급여/비급여 |
| 07 | `dental-implant-crown-silson` | 치과 임플란트·크라운 실손 |
| 08 | `shockwave-prolotherapy-gen5-exclusion` | 체외충격파·증식치료 5세대 제외 |

### 콘텐츠 기준 (PM 14차 교차검증 반영)
- **급여 본인부담률**: 국민건강보험법 시행령 [별표 2](개정 2026.9.15) — 의원 30% · 병원 40%(읍·면 35%) ·
  종합병원 50%(읍·면 45%) · 상급종합 진찰료 전액 + (총액−진찰료)×60% · 입원 20%(식대 50%, 2~4인실 50·40·30% 차등) · 약국 30%.
- **산정특례 5%**: 시행령 별표2가 아니라 복지부 고시 「본인일부부담금 산정특례에 관한 기준」·NHIS 안내로 표기.
- **뇌 MRI**: 고시 제2023-134호(2023.10.1 시행) — 두통·어지럼 6유형 + 신경학적 검사 기록 시 급여,
  요건 미해당 시에도 본인부담 80% 선별급여 최대 1회 경로 존재("○○일 때만 급여" 단정 금지).
- **척추 MRI**: 고시 제2023-293호 — 퇴행성 질환은 명백한 신경학적 이상 + 진료 결과 이상 소견 기록 시 급여,
  횟수 초과 시 퇴행성은 선별급여도 불가(비급여).
- **초음파**: 복지부 보도자료 2019-01-30 — 상복부 2018.4 · 하복부·비뇨기 2019.2, 고위험군 경과관찰 연 1회 등,
  증상 변화 없는 반복은 선별급여 80%. 보도자료 범위를 넘는 부위별 세부 횟수는 기재하지 않음.
- **만 65세 이상 치과임플란트**: 고시 제2025-23호(2025.2.1 시행) — 보철수복 재료에 PFM(비귀금속도재관)과
  지르코니아 크라운이 급여. 부분무치악 · 평생 2개 · 본인부담 30%(차상위 10/20%) · 본인부담상한제 제외.
  2026년 치과의원 행위수가 1~3단계 135,100 + 580,950 + 634,990 = **1,351,040원**, 단계별 30% 산출 후
  **100원 미만 절사** 합계로 본인부담 **405,100원**(40,500 + 174,200 + 190,400, 식립재료 고정체·지대주 별도).
- **도수치료 관리급여**(2026-07-01 시행): 1회 43,850원 · 본인부담 95%(종별 동일), 주 2회·연 15회
  (수술·골절 등 관절 구축·강직 예외 연 24회).
- 초안 표시(`(추정)`·`(확인 필요)`) 0건, 병원 실명·외부 병원 링크·예약 유도·제휴 링크 0건, AdSense 코드 없음.

### 검증
- `qa_check.py --live` — 56페이지(가이드 8편 포함) 전항 통과 + **J. 가이드 8편** 검사 신설:
  페이지 생성·허브 링크·초안 표시 0건·Article/FAQPage/BreadcrumbList·목차 앵커·상호 교차링크 7편·
  기존 섹션 내부링크 2개 이상·14차 보정 문구·임플란트 절사 기준.
- `verify_site.py --live` — 115/115 통과(가이드 8편 모바일 390px 렌더·목차 앵커 이동·데스크톱 2단 포함),
  콘솔 오류 0, 가로 스크롤 0.
- `crosscheck_calc.py` — 엔진 24,240건 × 5세대 × 6항목 = 727,200값 불일치 0(계산 로직 보존 확인).
