/*!
 * med-calc.js — 1~5세대 실손의료보험 + 도수치료 관리급여(95%) 계산 엔진 (Vanilla JS)
 *
 * scripts/calc_engine.py 의 규칙을 그대로 옮긴 화면용 구현이다.
 * 두 구현의 동일성은 scripts/crosscheck_calc.py 가 수천 건 조합으로 전수 검증한다.
 * 금액 계산은 정수 퍼센트 연산(pct)으로만 하여 파이썬과 부동소수 오차가 생기지 않게 했다.
 */
(function (root) {
  'use strict';

  var DEDUCT_GEN23 = { tertiary: 20000, general: 15000, hospital: 15000, clinic: 10000 };
  var DEDUCT_GEN45 = { tertiary: 20000, general: 20000, hospital: 20000, clinic: 10000 };
  var INSTITUTIONS = {
    tertiary: { label: '상급종합병원', short: '상급종합', api_scope: true },
    general: { label: '종합병원', short: '종합병원', api_scope: true },
    hospital: { label: '병원', short: '병원', api_scope: true },
    clinic: { label: '의원', short: '의원', api_scope: false }
  };
  var VISITS = { in: '입원', out: '통원' };
  var GENERATIONS = [
    { gen: 1, name: '1세대', period: '2009.9 이전', short: '1세대' },
    { gen: 2, name: '2세대', period: '2009.10~2017.3', short: '2세대' },
    { gen: 3, name: '3세대(착한실손)', period: '2017.4~2021.6', short: '3세대' },
    { gen: 4, name: '4세대', period: '2021.7~2026.4', short: '4세대' },
    { gen: 5, name: '5세대', period: '2026.5.6 출시', short: '5세대' }
  ];
  // 2세대 전기·후기 — 결과 표에서 두 행으로 분리 (calc_engine.py GEN2_META 와 동일)
  var GEN2_META = {
    early: { name: '2세대 전기', period: '2009.10~2013.3', short: '2세대 전기' },
    late: { name: '2세대 후기', period: '2013.4~2017.3', short: '2세대 후기' }
  };
  // 2세대 유형별 규칙 (인스팅트 #1247 반영 — 근거: 금융위 2012-12-21 보도자료 + 시기별 상세표, 2차 확인)
  var GEN2_SPEC = {
    // noncovered: 비급여 자기부담률(%) · managed: 관리급여(급여) 자기부담률(%) ·
    // out: 통원 공제 방식 — flat(정액만) / max(율과 정액 중 큰 금액)
    early: { noncovered: 10, managed: 10, out: 'flat' },
    late10: { noncovered: 10, managed: 10, out: 'flat' },
    late20: { noncovered: 20, managed: 20, out: 'max' },
    sel2: { noncovered: 20, managed: 10, out: 'max' }
  };
  var GEN2_TYPES = ['early', 'late10', 'late20', 'sel2', 'unknown'];
  var GEN2_LATE_LABEL = { late10: '10%형', late20: '표준형 20%', sel2: '선택형Ⅱ', unknown: '10%형~20%형' };
  var OUTPATIENT_CAP_GEN2 = 250000;  // 2세대 통원 외래 1일 보상한도 (표준약관 기준)

  function gen2Legacy(v) {
    // 2세대 유형 값 정규화 — 레거시 standard→표준형(late20), select2→선택형Ⅱ(sel2)
    if (GEN2_TYPES.indexOf(v) >= 0) { return v; }
    if (v === 'standard') { return 'late20'; }
    if (v === 'select2') { return 'sel2'; }
    return 'unknown';
  }

  function gen2CutCopay(base, cut, mode, visit, ded23) {
    // 2세대 본인부담 1건 — flat은 통원 정액만, max는 율과 정액 중 큰 금액
    var r = pct(base, cut);
    if (visit === 'out') {
      r = mode === 'flat' ? Math.min(ded23, base) : Math.max(r, Math.min(ded23, base));
    }
    return Math.min(r, base);
  }

  // 2세대 행의 본인부담 [copay, copayHi|null] — unknown은 후기 3유형의 최소~최대
  function gen2Copay(ctx, sub, item, base, ded23) {
    var managed = item.payment === '관리급여';
    var key = managed ? 'managed' : 'noncovered';
    if (sub === 'early') {
      var specE = GEN2_SPEC.early;
      return [gen2CutCopay(base, specE[key], specE.out, ctx.visit, ded23), null];
    }
    var t = ctx.gen2_type;
    if (t === 'early') { t = 'late20'; }  // 전기를 고른 경우 후기 행은 표준형(기존 기본값)으로 표시한다
    if (GEN2_SPEC[t]) {
      var spec = GEN2_SPEC[t];
      return [gen2CutCopay(base, spec[key], spec.out, ctx.visit, ded23), null];
    }
    var vals = ['late10', 'late20', 'sel2'].map(function (_t) {
      var s = GEN2_SPEC[_t];
      return gen2CutCopay(base, s[key], s.out, ctx.visit, ded23);
    });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    return [lo, hi > lo ? hi : null];
  }

  var MANAGED_UNIT_PRICE = 43850;
  var MANAGED_COPAY_RATE = 0.95;
  var MANAGED_ROUNDS_STD = 15;
  var MANAGED_ROUNDS_MAX = 24;

  var LIMIT5_SEVERE = 50000000;
  var LIMIT5_MILD = 10000000;
  var CAP5_SEVERE_INPATIENT_OOP = 5000000;

  function pct(base, p) { return Math.floor((base * p + 50) / 100); }

  function won(n) {
    return String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '원';
  }

  function managedTotal(rounds) {
    var n = Math.max(1, Math.round(Number(rounds) || 1));
    return MANAGED_UNIT_PRICE * n;
  }

  function itemByCode(code, items) {
    for (var i = 0; i < items.length; i++) { if (items[i].code === code) { return items[i]; } }
    return null;
  }

  function normalize(req, items) {
    var visit = req.visit || 'out';
    if (!VISITS[visit]) { throw new Error('visit 는 in/out 이어야 합니다: ' + visit); }
    var inst = req.institution || 'tertiary';
    if (!INSTITUTIONS[inst]) { throw new Error('알 수 없는 종별: ' + inst); }

    var code = req.item_code || 'direct';
    var item;
    if (code === 'direct') {
      item = { code: 'direct', name: '직접 입력 금액', payment: '비급여', special3: false, excluded5: null, slug: null };
    } else {
      item = itemByCode(code, items);
      if (!item) { throw new Error('카탈로그에 없는 항목: ' + code); }
    }

    var amount = req.amount;
    if (amount === null || typeof amount === 'undefined') {
      amount = item.payment === '관리급여' ? managedTotal(req.rounds || 1) : 0;
    }
    amount = Math.trunc(Number(amount) || 0);
    if (amount < 0) { amount = 0; }

    return {
      item: item,
      code: code,
      amount: amount,
      visit: visit,
      institution: inst,
      severe: !!req.severe,
      // 레거시 standard→표준형(late20), select2→선택형Ⅱ(sel2)
      gen2_type: gen2Legacy(req.gen2_type),
      severe_cum: Math.max(0, Math.trunc(Number(req.severe_cum) || 0)),
      rounds: Math.max(1, Math.trunc(Number(req.rounds) || 1))
    };
  }

  function limitsFor(gen, ctx, item, sub) {
    var notes = [];
    var managed = item.payment === '관리급여';
    if (gen === 1) {
      notes.push('세대 표준형 기준 · 상품별 약관(한도·자기부담) 차이 있음');
    } else if (gen === 2) {
      notes.push('통원 보상한도: 외래 1일 25만원 · 처방조제 1일 5만원 · 외래·처방조제 각각 연간 180회 (표준약관 기준)');
      notes.push('입원 보상한도: 상해·질병당 5,000만원 (표준약관 기준)');
      if (managed) { notes.push('관리급여 95%는 건강보험 본인부담률 — 실손은 그중 90% 보장(표준형은 80%)'); }
      if (sub === 'early') {
        notes.push('2013년 3월 이전 가입(전기) — 재가입 절차가 없는 유형입니다(약관 기준)');
        notes.push('단, 2013년 1월~3월에 표준형으로 가입한 경우 15년마다 재가입합니다 — 증권에서 확인하세요');
      } else if (ctx.gen2_type === 'unknown') {
        notes.push('2013년 4월 이후 가입(후기) · 자기부담 10%형/20%형 — 유형을 모르면 세 유형의 범위로 표시합니다');
        notes.push('15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. ' +
          '재가입 때 보험료와 조건은 보험사 안내를 확인하세요');
      } else if (ctx.gen2_type === 'late10') {
        notes.push('2013년 4월~2015년 8월 가입(후기 10%형·선택형) · 자기부담 10% · 15년마다 재가입합니다');
        notes.push('15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. ' +
          '재가입 때 보험료와 조건은 보험사 안내를 확인하세요');
      } else if (ctx.gen2_type === 'sel2') {
        notes.push('2015년 9월~2017년 3월 가입(후기 선택형Ⅱ) · 급여 10% · 비급여 20% · 15년마다 재가입합니다');
        notes.push('15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. ' +
          '재가입 때 보험료와 조건은 보험사 안내를 확인하세요');
      } else {  // late20 표준형
        notes.push('표준형(20%형) · 급여·비급여 자기부담 20% · 15년마다 재가입합니다');
        notes.push('15년마다 재가입하는 유형 — 가입 시점에 따라 2028년부터 재가입 시점이 도래합니다. ' +
          '재가입 때 보험료와 조건은 보험사 안내를 확인하세요');
      }
    } else if (gen === 3) {
      notes.push('비급여 연간 한도·갱신 조건은 약관 확인 필요');
      if (managed) { notes.push('관리급여 95%는 건강보험 본인부담률 — 실손은 그중 90% 보장(통원 10% 공제)'); }
    } else if (gen === 4) {
      if (!managed) { notes.push('통원 회당 보장 20만원 한도 적용'); }
      else { notes.push('관리급여 95%는 건강보험 본인부담률 — 실손은 그중 80% 보장(입원·통원 20% 공제)'); }
      notes.push('연간 보장한도 5천만원 · 비급여 이용량 차등할증 대상');
    } else if (gen === 5) {
      if (managed) {
        notes.push('관리급여 본인부담 95% · 1회 ' + won(MANAGED_UNIT_PRICE) + '(종별 동일)');
        notes.push('실손 보장 5% 수준 — 건강보험 본인부담금의 5%만 보장');
        notes.push('연간 ' + MANAGED_ROUNDS_STD + '회(수술·골절 등 예외 ' + MANAGED_ROUNDS_MAX + '회) 한도');
      } else if (ctx.severe) {
        notes.push('중증 비급여(특약1) 연간 ' + won(LIMIT5_SEVERE) + ' 한도 · 통원 회당 20만원');
        if (ctx.institution === 'tertiary' || ctx.institution === 'general') {
          notes.push('상급·종합병원 입원 연간 자기부담 상한 500만원(초과분 보장)');
        }
      } else {
        notes.push('비중증 비급여(특약2) 연간 ' + won(LIMIT5_MILD) + ' 한도 · 통원 일당 20만원');
        if (ctx.visit === 'in') { notes.push('입원 회당 300만원 한도'); }
        notes.push('특약2는 이용량에 따라 보험료 할인·할증 적용');
      }
    }
    return notes;
  }

  function rateLabel(gen, ctx, item, sub) {
    var visit = ctx.visit;
    var managed = item.payment === '관리급여';
    if (gen === 1) { return visit === 'in' ? '입원 100%' : '5천원 공제 후 100%'; }
    if (gen === 2) {
      var t2 = sub === 'early' ? 'early' : ctx.gen2_type;
      if (sub !== 'early' && t2 === 'early') { t2 = 'late20'; }  // 전기를 고른 경우 후기 행은 표준형으로 표시한다
      if (t2 === 'unknown') {
        return visit === 'in' ? '10%~20%' : 'Max(10%~20%, 외래공제)';
      }
      var spec2 = GEN2_SPEC[t2];
      var cut2 = spec2[managed ? 'managed' : 'noncovered'];
      if (visit === 'in') {
        return (managed && cut2 === 10) ? '급여 90%' : cut2 + '%';
      }
      if (spec2.out === 'flat') { return '정액만(외래공제)'; }
      return 'Max(' + cut2 + '%, 외래공제)';
    }
    if (gen === 3) {
      if (item.special3 && !managed) { return visit === 'in' ? '20%' : 'Max(30%, 2만원)'; }
      if (managed) { return visit === 'in' ? '급여 90%' : 'Max(10%, 외래공제)'; }
      return visit === 'in' ? '20%' : 'Max(20%, 외래공제)';
    }
    if (gen === 4) {
      if (managed) { return visit === 'in' ? '20%' : 'Max(20%, 1·2만원)'; }
      return visit === 'in' ? '30%' : 'Max(30%, 3만원)';
    }
    if (managed) { return visit === 'in' ? '20%' : 'Max(건보 95%, 1·2만원)'; }
    if (ctx.severe) { return visit === 'in' ? '30%' : 'Max(30%, 3만원)'; }
    return visit === 'in' ? '50%' : 'Max(50%, 5만원)';
  }

  function genRow(gen, ctx, sub) {
    var item = ctx.item;
    var visit = ctx.visit;
    var inst = ctx.institution;
    var managed = item.payment === '관리급여';
    var meta = null;
    if (gen === 2 && sub && GEN2_META[sub]) { meta = GEN2_META[sub]; }
    else {
      for (var i = 0; i < GENERATIONS.length; i++) { if (GENERATIONS[i].gen === gen) { meta = GENERATIONS[i]; } }
    }

    var total = ctx.amount;
    var base = managed ? pct(total, 95) : total;
    var ded23 = DEDUCT_GEN23[inst];
    var ded45 = DEDUCT_GEN45[inst];

    var status = 'covered';
    var badges = [];
    var coveredCap = null;
    var copay = 0;
    var copayHi = null;  // 범위 상한(모르겠어요 후기 행) — null이면 단일값
    var capApplied = false;
    var capOutpatient = false;  // 부이 #1279 ③ — 2세대 통원 외래 1일 25만원 한도 적용 여부
    var extraNote = [];
    var raw = 0;

    // 인스팅트 #1283 ① — 관리급여 통원은 공제가 방문 1회당이므로, 횟수가 2회 이상이면
    // 1회분으로 계산해 횟수를 곱한다. 총액에 1회만 적용하면 과소 계산됨
    // (도수치료 10회 통원·의원: 전 유형 100,000원). 금액이 1회 수가 × 횟수와 다르면
    // (직접 입력 등) 기존 총액 계산을 유지한다.
    var _n = ctx.rounds || 1;
    if (managed && visit === 'out' && _n > 1 && total === MANAGED_UNIT_PRICE * _n) {
      var unit = genRow(gen, Object.assign({}, ctx, { amount: MANAGED_UNIT_PRICE, rounds: 1 }), sub);
      if (unit.status === 'excluded') {
        unit.copay = base;
        unit.copay_hi = null;
        unit.covered = 0;
        unit.covered_lo = null;
      } else {
        unit.copay = unit.copay * _n;
        if (unit.copay_hi !== null && unit.copay_hi !== undefined) {
          unit.copay_hi = unit.copay_hi * _n;
          if (unit.copay_hi <= unit.copay) { unit.copay_hi = null; }
        }
        if (unit.copay > base) { unit.copay = base; unit.copay_hi = null; }
        unit.covered = base - unit.copay;
        unit.covered_lo = (unit.copay_hi !== null && unit.copay_hi !== undefined) ? base - unit.copay_hi : null;
      }
      unit.base = base;
      // 부이 #1296 — 이 분기는 rounds:1 로 재귀 호출하므로 per_visit을 여기서 직접 정한다.
      // 부이 #1310 ② — 3·4세대 행에도 같은 한 줄을 붙인다(회당 공제 × 횟수라 값은 규칙대로).
      unit.per_visit = gen === 2 || gen === 3 || gen === 4;
      return unit;
    }
    var excludedGens = item.excluded_gens || [];
    var genExcluded = excludedGens.indexOf(gen) >= 0;

    if (genExcluded) {
      status = 'excluded';
      copay = base;
    } else if (gen === 5 && !managed && item.excluded5 && !ctx.severe) {
      status = 'excluded';
      copay = base;
    } else if (gen === 1) {
      copay = visit === 'out' ? Math.min(5000, base) : 0;
    } else if (gen === 2) {
      // 2세대 유형별 규칙(인스팅트 #1247): 전기·후기 10%형은 통원 정액만,
      // 표준형·선택형Ⅱ는 통원 Max(형별 %, 정액). 관리급여도 같은 급여/비급여 구분을 따른다.
      var g2pair = gen2Copay(ctx, sub || 'late', item, base, ded23);
      copay = g2pair[0];
      copayHi = g2pair[1];
      // 통원 외래 1일 보상한도 25만원 — 비급여 통원에만 적용(관리급여는 회수 합산액이라 제외).
      if (visit === 'out' && !managed) {
        var floor2 = base - OUTPATIENT_CAP_GEN2;
        if (floor2 > 0) {
          if (copay < floor2) { copay = floor2; capApplied = true; capOutpatient = true; }
          if (copayHi !== null && copayHi < floor2) { copayHi = floor2; capApplied = true; capOutpatient = true; }
          if (copayHi !== null && copayHi <= copay) { copayHi = null; }
        }
      }
    } else if (gen === 3) {
      if (item.special3 && !managed) {
        badges.push('3세대 비급여 특약');
        if (visit === 'in') { raw = pct(base, 20); }
        else { raw = Math.max(pct(base, 30), Math.min(20000, base)); }
      } else {
        // 관리급여도 2세대와 같은 이유로 급여 90%(10% 공제).
        var cut3 = managed ? 10 : 20;
        raw = pct(base, cut3);
        if (visit === 'out') { raw = Math.max(raw, Math.min(ded23, base)); }
      }
      copay = Math.min(raw, base);
    } else if (gen === 4) {
      if (managed) {
        raw = pct(base, 20);
        if (visit === 'out') { raw = Math.max(raw, Math.min(ded45, base)); }
      } else if (visit === 'in') {
        raw = pct(base, 30);
      } else {
        raw = Math.max(pct(base, 30), Math.min(30000, base));
        coveredCap = 200000;
      }
      copay = Math.min(raw, base);
    } else if (gen === 5) {
      if (managed) {
        raw = pct(base, 20);
        if (visit === 'out') { raw = Math.max(raw, pct(base, 95), Math.min(ded45, base)); }
        copay = Math.min(raw, base);
      } else if (ctx.severe) {
        badges.push('특약1 중증');
        if (visit === 'in') {
          raw = pct(base, 30);
          if ((inst === 'tertiary' || inst === 'general') && ctx.severe_cum > 0) {
            var overflow = ctx.severe_cum + raw - CAP5_SEVERE_INPATIENT_OOP;
            if (overflow > 0) {
              var cutO = Math.min(overflow, raw);
              raw -= cutO;
              if (cutO) { extraNote.push('연간 자기부담 상한 500만원 초과분 ' + won(cutO) + ' 추가 보장 반영'); }
            }
          }
        } else {
          raw = Math.max(pct(base, 30), Math.min(30000, base));
          coveredCap = 200000;
        }
        copay = Math.min(raw, base);
      } else {
        badges.push('특약2 비중증');
        if (visit === 'in') {
          raw = pct(base, 50);
          coveredCap = 3000000;
        } else {
          raw = Math.max(pct(base, 50), Math.min(50000, base));
          coveredCap = 200000;
        }
        copay = Math.min(raw, base);
      }
    } else {
      throw new Error('알 수 없는 세대: ' + gen);
    }

    var covered = status === 'excluded' ? 0 : base - copay;
    var coveredLo = (status !== 'excluded' && copayHi !== null) ? base - copayHi : null;
    if (status !== 'excluded' && coveredCap !== null && covered > coveredCap) {
      covered = coveredCap;
      copay = base - covered;
      capApplied = true;
    }

    if (managed) { badges.unshift('관리급여 95%'); }
    if (genExcluded) { badges.push('약관상 보장 제외'); }
    else if (gen === 5 && !managed && item.excluded5) { badges.push('5세대 보장 제외'); }

    var limits = limitsFor(gen, ctx, item, sub);
    for (var k = 0; k < extraNote.length; k++) { limits.push(extraNote[k]); }
    var rate = rateLabel(gen, ctx, item, sub);
    if (status === 'excluded' && genExcluded) {
      rate = '보장 제외';
      limits = ['약관상 보장 제외(사유: ' + (item.exclude_reason || '보장 대상 아님') + ')',
        '가입 시기·상품 약관에 따라 판단이 달라질 수 있어 보험사 확인이 필요합니다',
        '같은 날 받은 급여 항목의 본인부담금은 별도로 청구할 수 있습니다'];
    } else if (status === 'excluded') {
      rate = '보장 제외';
      limits = ['5세대 특약2 보장 대상에서 제외(사유: ' + item.excluded5 + ')',
        '산정특례 대상 질환 치료 등 특약1 해당 여부는 보험사 심사로 확인',
        '4세대 이전 세대는 위 자기부담 기준으로 계산됩니다'];
    }

    var rule;
    if (gen === 1) { rule = '입원 100% 보장 / 통원 5,000원 공제 후 100% (표준형 기준)'; }
    else if (gen === 2) {
      var t2 = sub === 'early' ? 'early' : ctx.gen2_type;
      if (sub !== 'early' && t2 === 'early') { t2 = 'late20'; }  // 전기를 고른 경우 후기 행은 표준형으로 표시한다
      var dedTxt = '외래공제(의원 1만·종합병원·병원 1.5만·상급종합 2만)';
      if (t2 === 'unknown') {
        if (managed) {
          rule = '관리급여(급여) 항목: 통원은 정액 공제만 또는 형별 %와 ' + dedTxt + ' 중 큰 금액 — 유형별 범위 적용';
        } else {
          rule = '비급여 본인부담 10%형~20%형 범위 · 통원은 형별 %와 ' + dedTxt + ' 중 큰 금액 공제';
        }
      } else {
        var specR = GEN2_SPEC[t2];
        var cutR = specR[managed ? 'managed' : 'noncovered'];
        if (managed) {
          if (specR.out === 'flat') {
            rule = '관리급여(급여) 항목: ' + (100 - cutR) + '% 보장 · 통원은 정액 공제만(' + dedTxt + ')';
          } else {
            rule = '관리급여(급여) 항목: ' + (100 - cutR) + '% 보장 · 통원은 ' + cutR + '%와 ' + dedTxt + ' 중 큰 금액 공제';
          }
        } else if (specR.out === 'flat') {
          rule = '비급여 본인부담 ' + cutR + '% · 통원은 정액 공제만(' + dedTxt + ')';
        } else {
          rule = '비급여 본인부담 ' + cutR + '% · 통원은 ' + cutR + '%와 ' + dedTxt + ' 중 큰 금액 공제';
        }
      }
    }
    else if (gen === 3) {
      rule = managed
        ? '관리급여(급여) 항목: 90% 보장 · 통원은 10%와 외래공제 중 큰 금액 공제'
        : (item.special3 && !managed)
          ? '3세대 비급여 특약(도수·체외충격파·증식·비급여 주사·MRI): 통원 Max(30%, 2만원) 공제'
          : '기본 비급여 20% 공제 · 통원은 20%와 외래공제 중 큰 금액 공제';
    } else if (gen === 4) {
      rule = !managed
        ? '4세대 비급여 특약: 입원 30% · 통원 Max(30%, 3만원), 통원 회당 20만원 한도'
        : '급여 항목: 입원 20% · 통원 Max(20%, 1·2만원)';
    } else {
      if (managed) { rule = '5세대 급여: 통원 자기부담률을 건강보험 본인부담률(관리급여 95%)에 연동 → 실손 보장 5% 수준'; }
      else if (ctx.severe) { rule = '5세대 특약1(중증 비급여): 입원 30% · 통원 Max(30%, 3만원), 상급·종합 입원 연 자기부담 상한 500만원'; }
      else { rule = '5세대 특약2(비중증 비급여): 입원 50% · 통원 Max(50%, 5만원), 입원 회당 300만·통원 일당 20만 한도'; }
    }
    if (status === 'excluded' && genExcluded) {
      rule = '약관상 보장 제외 — ' + (item.exclude_reason || '보장 대상이 아닙니다.');
    } else if (status === 'excluded') {
      rule = '5세대 비중증 비급여 보장 제외 항목(' + item.excluded5 + ') — 특약2에서 보장하지 않습니다.';
    }

    var period = meta.period;
    if (gen === 2 && sub === 'late') {
      period = period + ' · ' + (GEN2_LATE_LABEL[ctx.gen2_type] || '10%형~20%형') + ' 기준';
    }
    var key = gen === 2 ? 'g2' + (sub || 'late').charAt(0) : 'g' + gen;
    return {
      gen: gen,
      sub: sub || '',
      key: key,
      name: meta.name,
      period: period,
      status: status,
      base: base,
      copay: copay,
      copay_hi: copayHi,
      covered: covered,
      covered_lo: coveredLo,
      same_amount: false,
      rate_label: rate,
      rule: rule,
      badges: badges,
      limits: limits,
      cap_applied: capApplied,
      cap_outpatient: capOutpatient,
      // 부이 #1296 — 관리급여 통원 2회 이상: 공제가 방문 1회마다 따로 적용됨을 표에 한 줄로 푼다.
      // 부이 #1310 ② — 3·4세대 행에도 같은 한 줄을 붙인다.
      per_visit: (gen === 2 || gen === 3 || gen === 4) && managed && ctx.visit === 'out' && ctx.rounds > 1
    };
  }

  function compute(req, items) {
    items = items || (root.MED_CATALOG && root.MED_CATALOG.items) || [];
    var ctx = normalize(req, items);
    var rows = [genRow(1, ctx), genRow(2, ctx, 'early'), genRow(2, ctx, 'late'),
      genRow(3, ctx), genRow(4, ctx), genRow(5, ctx)];

    // 부이 #1245 ⑤·⑧ — 후기 행 보충 안내 (전기 행과 후기 10%형 기준 대조)
    var earlyRow = rows[1], lateRow = rows[2];
    var ctx10 = Object.assign({}, ctx, { gen2_type: 'late10' });
    var late10Row = genRow(2, ctx10, 'late');
    var sameAmt = earlyRow.copay === late10Row.copay && earlyRow.covered === late10Row.covered &&
      earlyRow.status === late10Row.status;
    lateRow.same_amount = sameAmt;
    if (sameAmt && (ctx.gen2_type === 'late10' || ctx.gen2_type === 'unknown')) {
      lateRow.limits.push('전기(2013년 3월 이전 가입)와 후기 10%형은 같은 금액입니다');
    }
    var lateMaxCopay = lateRow.copay_hi !== null && lateRow.copay_hi !== undefined ? lateRow.copay_hi : lateRow.copay;
    if (lateMaxCopay > earlyRow.copay) {
      if (ctx.gen2_type === 'unknown') {
        lateRow.limits.push('후기 20%형·선택형Ⅱ는 전기·후기 10%형보다 본인부담이 큽니다');
      } else {
        lateRow.limits.push('후기 ' + (GEN2_LATE_LABEL[ctx.gen2_type] || '표준형 20%') + '는 전기·후기 10%형보다 본인부담이 큽니다');
      }
    }
    if (ctx.item.payment === '관리급여' && lateRow.copay_hi !== null && lateRow.copay_hi !== undefined) {
      // 범위인 경우는 '모르겠어요'뿐이다 — 표준형(20%형)은 83,315원 단일값으로 확정됨(#1247 (b))
      lateRow.limits.push('후기 관리급여는 유형·약관에 따라 ' + won(lateRow.copay) + '~' + won(lateRow.copay_hi) +
        '입니다 — 금액 옆 범위를 확인하세요');
    }

    var coveredRows = rows.filter(function (r) { return r.status !== 'excluded'; });
    var best = null;
    for (var i = 0; i < coveredRows.length; i++) {
      if (best === null || coveredRows[i].covered > best.covered) { best = coveredRows[i]; }
    }

    var warnings = [];
    if (ctx.item.payment === '관리급여') {
      warnings.push('도수치료는 2026.7.1부터 관리급여(선별급여)입니다. 비급여 특약이 아니라 급여 항목으로 계산하며, ' +
        '1회 ' + won(MANAGED_UNIT_PRICE) + '(종별 동일) · 본인부담률 95% 기준입니다.');
    }
    if (!INSTITUTIONS[ctx.institution].api_scope) {
      warnings.push('의원은 심평원 비급여 공개 API 대상이 아닙니다(병원급 이상만 제공). 종별 공제액 계산을 위한 참고 선택이며, 의원 가격은 방문 전 유선 확인이 필요합니다.');
    }
    if (ctx.item.excluded_gens && ctx.item.excluded_gens.length) {
      warnings.push('이 항목은 표준 실손약관상 보장 제외 대상입니다 — ' + (ctx.item.exclude_reason || '') +
        ' 세대별 표시를 확인하고, 실제 지급 여부는 가입 약관과 보험사 심사로 확인하세요.');
    }
    if (ctx.severe) {
      warnings.push('중증(산정특례) 여부는 5세대 특약1·2 구분에만 영향을 줍니다. 1~4세대는 해당 질환도 비급여 자기부담률이 같습니다(단, 4세대 비급여 차등할증에서 중증은 제외).');
    }
    var anyCap = rows.some(function (r) { return r.cap_applied; });
    if (anyCap) { warnings.push('일부 세대는 회당 보장한도가 적용되어 계산된 보장액이 한도에 걸렸습니다(표시 참조).'); }

    return {
      input: {
        item_code: ctx.code,
        item_name: ctx.item.name,
        payment: ctx.item.payment,
        amount: ctx.amount,
        visit: ctx.visit,
        visit_label: VISITS[ctx.visit],
        institution: ctx.institution,
        institution_label: INSTITUTIONS[ctx.institution].label,
        severe: ctx.severe,
        gen2_type: ctx.gen2_type,
        severe_cum: ctx.severe_cum,
        rounds: ctx.rounds
      },
      generations: rows,
      summary: {
        best_gen: best ? best.gen : null,
        best_key: best ? best.key : null,
        best_covered: best ? best.covered : 0,
        excluded_gens: rows.filter(function (r) { return r.status === 'excluded'; }).map(function (r) { return r.gen; })
      },
      warnings: warnings
    };
  }

  root.MedCalc = {
    compute: compute,
    won: won,
    pct: pct,
    managedTotal: managedTotal,
    MANAGED_UNIT_PRICE: MANAGED_UNIT_PRICE,
    MANAGED_COPAY_RATE: MANAGED_COPAY_RATE,
    MANAGED_ROUNDS_STD: MANAGED_ROUNDS_STD,
    MANAGED_ROUNDS_MAX: MANAGED_ROUNDS_MAX,
    GENERATIONS: GENERATIONS,
    INSTITUTIONS: INSTITUTIONS,
    VISITS: VISITS
  };
})(typeof window !== 'undefined' ? window : globalThis);
