/*!
 * med-calc.js — 1~5세대 실손의료보험 + 도수치료 관리급여(95%) 계산 엔진 (Vanilla JS)
 *
 * scripts/calc_engine.py 의 규칙을 그대로 옮긴 화면용 구현이다.
 * 두 구현의 동일성은 scripts/crosscheck_calc.py 가 수천 건 조합으로 전수 검증한다.
 * 금액 계산은 정수 퍼센트 연산(pct)으로만 하여 파이썬과 부동소수 오차가 생기지 않게 했다.
 */
(function (root) {
  'use strict';

  var DEDUCT_GEN23 = { tertiary: 20000, general: 20000, hospital: 15000, clinic: 10000 };
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
      gen2_type: req.gen2_type === 'select2' ? 'select2' : 'standard',
      severe_cum: Math.max(0, Math.trunc(Number(req.severe_cum) || 0)),
      rounds: Math.max(1, Math.trunc(Number(req.rounds) || 1))
    };
  }

  function limitsFor(gen, ctx, item) {
    var notes = [];
    var managed = item.payment === '관리급여';
    if (gen === 1) {
      notes.push('세대 표준형 기준 · 상품별 약관(한도·자기부담) 차이 있음');
    } else if (gen === 2) {
      notes.push('통원 회당 보장한도·연간 한도는 상품별 약관 확인 필요');
      if (ctx.gen2_type === 'select2') { notes.push('선택형Ⅱ: 급여 90% · 비급여 80%'); }
    } else if (gen === 3) {
      notes.push('비급여 연간 한도·갱신 조건은 약관 확인 필요');
    } else if (gen === 4) {
      if (!managed) { notes.push('통원 회당 보장 20만원 한도 적용'); }
      notes.push('연간 보장한도 5천만원 · 비급여 이용량 차등할증 대상');
    } else if (gen === 5) {
      if (managed) {
        notes.push('관리급여 본인부담 95% · 1회 ' + won(MANAGED_UNIT_PRICE) + '(종별 동일)');
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

  function rateLabel(gen, ctx, item) {
    var visit = ctx.visit;
    var managed = item.payment === '관리급여';
    if (gen === 1) { return visit === 'in' ? '입원 100%' : '5천원 공제 후 100%'; }
    if (gen === 2) {
      if (managed && ctx.gen2_type === 'select2') { return visit === 'in' ? '급여 90%' : 'Max(10%, 외래공제)'; }
      return visit === 'in' ? '80%' : 'Max(20%, 외래공제)';
    }
    if (gen === 3) {
      if (item.special3 && !managed) { return visit === 'in' ? '20%' : 'Max(30%, 2만원)'; }
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

  function genRow(gen, ctx) {
    var item = ctx.item;
    var visit = ctx.visit;
    var inst = ctx.institution;
    var managed = item.payment === '관리급여';
    var meta = null;
    for (var i = 0; i < GENERATIONS.length; i++) { if (GENERATIONS[i].gen === gen) { meta = GENERATIONS[i]; } }

    var total = ctx.amount;
    var base = managed ? pct(total, 95) : total;
    var ded23 = DEDUCT_GEN23[inst];
    var ded45 = DEDUCT_GEN45[inst];

    var status = 'covered';
    var badges = [];
    var coveredCap = null;
    var copay = 0;
    var capApplied = false;
    var extraNote = [];
    var raw = 0;
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
      var cut = (managed && ctx.gen2_type === 'select2') ? 10 : 20;
      raw = pct(base, cut);
      if (visit === 'out') { raw = Math.max(raw, Math.min(ded23, base)); }
      copay = Math.min(raw, base);
    } else if (gen === 3) {
      if (item.special3 && !managed) {
        badges.push('3세대 비급여 특약');
        if (visit === 'in') { raw = pct(base, 20); }
        else { raw = Math.max(pct(base, 30), Math.min(20000, base)); }
      } else {
        raw = pct(base, 20);
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
    if (status !== 'excluded' && coveredCap !== null && covered > coveredCap) {
      covered = coveredCap;
      copay = base - covered;
      capApplied = true;
    }

    if (managed) { badges.unshift('관리급여 95%'); }
    if (genExcluded) { badges.push('약관상 보장 제외'); }
    else if (gen === 5 && !managed && item.excluded5) { badges.push('5세대 보장 제외'); }

    var limits = limitsFor(gen, ctx, item);
    for (var k = 0; k < extraNote.length; k++) { limits.push(extraNote[k]); }
    var rate = rateLabel(gen, ctx, item);
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
    else if (gen === 2) { rule = '비급여 80% 보장 · 통원은 20%와 외래공제(의원 1만·병원 1.5만·종합/상급 2만) 중 큰 금액 공제'; }
    else if (gen === 3) {
      rule = (item.special3 && !managed)
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

    return {
      gen: gen,
      name: meta.name,
      period: meta.period,
      status: status,
      base: base,
      copay: copay,
      covered: covered,
      rate_label: rate,
      rule: rule,
      badges: badges,
      limits: limits,
      cap_applied: capApplied
    };
  }

  function compute(req, items) {
    items = items || (root.MED_CATALOG && root.MED_CATALOG.items) || [];
    var ctx = normalize(req, items);
    var rows = [1, 2, 3, 4, 5].map(function (g) { return genRow(g, ctx); });

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
