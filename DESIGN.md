# DESIGN.md — 메디컬·비급여 시세 비교 파인더 디자인 시스템 v1

- 작성: Muse · 2026-11-21 · 디자인 패스 1차 + 폰트 표준화
- 원칙: 케이메디체크 DESIGN.md v1의 토큰·규율을 채택하고, 폰트는 주차장 파인더와 동일하게 Pretendard 자체 호스팅으로 표준화한다. 레이아웃·기능은 건드리지 않고 표면(색·폰트·모서리·간격)만 맞춘다.

## 제품 맥락

- **무엇**: 병원급 이상 비급여 공개가와 1~5세대 실손 보장액을 함께 계산하는 중립 정보 사이트.
- **누구에게**: 비급여 진료비를 내기 전, 휴대폰으로 가격과 보장액을 확인하는 국내 사용자.
- **일의 본질**: 출처 있는 숫자로 "얼마 내고 얼마 돌려받는지"에 답하는 것. 신뢰가 제품이다.
- **제약**: 외부 CDN 없음(폰트는 Pretendard 자체 호스팅), 정적 빌드, 한국어 단일 언어.

## 적용한 표준 (2026-11-21)

### 폰트

- Pretendard Variable 자체 호스팅: 동적 서브셋 woff2 92종 + `pretendardvariable-dynamic-subset.css` + OFL 라이선스를 `assets/fonts/`에 동봉 (주차장 파인더와 동일 구성·동일 파일).
- 전 페이지 head에 subset.91 preload + 폰트 CSS 링크. 폰트 CSS도 기존 자산과 같은 `?v=<hash8>` 캐시 버스팅 대상에 포함.
- CLS 대책: "Pretendard Fallback" @font-face에 메트릭 오버라이드(ascent 95.21% / descent 24.12% / line-gap 0%) — 폰트 파일 실측 기준, 주차장과 동일 수치.
- 스택: `"Pretendard Variable", "Pretendard", "Pretendard Fallback", -apple-system, …`
- 자간: 본문 -0.02em (기존 -0.01em에서 표준값으로).

### 색상 — 케이메디 토큰 채택

| 이름 | Hex | 토큰 | 비고 |
|---|---|---|---|
| Clinic Paper | `#F6F8F7` | `--bg` | 페이지 배경 (← 청회색 #F4F6FB) |
| Chip Grey | `#EDF1EF` | `--bg-soft` | 보조 배경 |
| Ledger Ink | `#14181C` | `--ink` | 본문 잉크 |
| Soft Ink | `#46505A` | `--ink-2` | 보조 텍스트 |
| Caption Muted | `#6D7883` | `--muted` | 3차 정보 |
| Rule | `#D9E1DE` | `--line` | 헤어라인 (녹회색) |
| Rule Soft | `#E7EDEA` | `--line-2` | 연한 구분선 (Rule 파생) |
| Clinic Teal | `#0F766E` | `--accent` | 1차 액션·브랜드 (기존과 동일) |
| Teal Deep | `#0B5D56` | `--accent-ink` | 호버·틴트 위 텍스트 (기존과 동일) |
| Teal Wash | `#E6F4F1` | `--accent-soft` | 틴트 패널 (기존과 동일) |
| Brand Line | `#C3E2DB` | `--brand-line` | 틴트 보더 (신규 토큰 — raw #B9D8D3·#BFE3DD를 토큰화) |

- 의미 전용 색(blue·violet·amber·red 계열)과 그 틴트 보더는 현행 유지 — 의미가 색에 붙어 있어 합치지 않는다.
- 범위 고지 스트립: 청회색 raw hex(#EEF3FB·#35507A) → Teal Wash 배경 + Teal Deep 텍스트로 통일.
- 포커스 색: 팔레트 밖 #99D5CD → Clinic Teal.

### radius 규율

- 표면(카드·패널·버튼·결과): **10px** (`--radius`, ← 16px). 산재한 12px·14px 표면도 토큰으로 정규화.
- 입력 필드·작은 컨트롤: **8px** (`--radius-sm`, ← 10px). select·input·세그먼트 버튼·칩 버튼에 적용.
- 999px pill(메타데이터 칩·배지), 6px 배지(판정 스탬프 성격)는 현행 유지.

### 그라데이션

- 장식 그라데이션 0이 규율: 히어로의 radial/linear 배경과 로고 마크의 linear-gradient를 제거하고 평면(히어로=흰 표면, 마크=Clinic Teal 단색)으로 교체.

### 그림자

- 구조는 유지하되 기준색만 Ledger Ink 계열 rgba(20,24,28)로 교체.

## 적용 범위 밖 (후속 후보)

- 타입 스케일 정리(12/12.5/13/13.5px 근접 중복) — 케이메디 2차 패스 백로그와 같은 항목.
- 틴트 패널 위 텍스트 대비 전수 측정.
- 스크린샷 기반 시각 QA 게이트 편입 여부.
