# DESIGN.md — 메디컬·비급여 시세 비교 파인더 디자인 시스템

- v2: 2026-11-25 · 디자인 선택 대회 당선작 **Lanwell Health**(크림·세이지) 채택 — 아래 v2 절이 현행 기준이고, v1 절은 이력으로 남긴다.
- v1: Muse · 2026-11-21 · 디자인 패스 1차 + 폰트 표준화

## v2 적용 표준 (2026-11-25, Lanwell Health)

- **팔레트**: 배경 Cream `#FAF5EC` · 보조 `#F3EDDF` · 표면 `#FFFDF7` · 잉크 `#2F362A` · 뮤트 `#6E7462` · 라인 `#E3DAC6` · 세이지 `#71835F` · 세이지 딥(채움·강조 텍스트) `#4C5C3E` · 세이지 틴트 `#E8ECDC` · 경고는 Lanwell warn `#9A6B3F`/`#F5EAD9`. 의미 색(blue·violet·red)은 유지.
- **다크모드**: 기기 설정 자동 대응 유지. 딥 올리브 배경 `#1D211A` · 표면 `#262B21` · 잉크 `#EDE9DC` · 밝은 세이지 `#A7BC8E`/`#C9DCB0`로 변형하고, 채움 버튼의 세이지 딥은 라이트와 동일하게 유지해 흰 글씨 대비(약 7:1)를 지킨다.
- **모서리·그림자**: 표면 radius 20px(`--radius`) · 입력 12px(`--radius-sm`) · 그림자는 세이지 기준 rgba(76,92,62)의 부드러운 확산으로 교체.
- **컴포넌트**: 세그먼트 버튼은 pill(999px)로, 히어로는 세이지 틴트 그라데이션 배경 + 세리프 헤드라인(Nanum Myeongjo 스택, 자체 호스팅 폰트 제약상 시스템 세리프 폴백)으로 Lanwell 톤을 낸다.
- **브랜드 마크**: 로고·파비콘·공유 카드·OG 이미지의 남색/틸을 세이지 딥 `#4C5C3E` + 라이트 세이지 획 `#DCE5C8`로 교체 (마크 형태는 유지). 공유 카드 하단 도메인도 현행 kr.kmedicheck.com으로 정정.
- **유지**: 비급여 가격 데이터·계산 로직·수치, 심평원 출처 표기, GA/GTM 태그, Pretendard 자체 호스팅, 의미 색의 뜻(제외=red, 관리급여=blue, 특약=violet, 한도=amber).
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
