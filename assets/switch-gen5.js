/*!
 * switch-gen5.js — 실손 5세대 전환 손익 시뮬레이터 (Vanilla JS)
 *
 * scripts/switch_engine.py 의 계산 규칙을 그대로 옮긴 화면용 구현이다.
 * 두 구현의 동일성은 scripts/crosscheck_switch.py 가 수천 건 조합으로 검증한다.
 * 금액 계산은 정수 퍼센트 연산(pct)만 써서 파이썬과 부동소수 오차가 생기지 않게 했다.
 *
 * 개인정보 원칙: 입력값은 브라우저 안에서만 계산하고 전송·저장하지 않는다.
 * 공유 링크(URL)에도 입력값을 담지 않는다.
 */
(function (root) {
  'use strict';

  /* ------------------------------------------------------------ 상수 (Python 과 동일) */
  var DEDUCT = {
    2: { tertiary: 20000, general: 20000, hospital: 15000, clinic: 10000 },
    3: { tertiary: 20000, general: 20000, hospital: 20000, clinic: 10000 },
    4: { tertiary: 20000, general: 20000, hospital: 20000, clinic: 10000 },
    5: { tertiary: 20000, general: 20000, hospital: 20000, clinic: 10000 }
  };
  var MILD5_MIN_VISIT = 50000;
  var LIMITS = { 4: { severe: 50000000, mild: 50000000 }, 5: { severe: 50000000, mild: 10000000 } };
  var EST_DISCOUNT = { 1: 50, 2: 50, 3: 30, 4: 30 };
  var DISCOUNT_MIN = 10;
  var DISCOUNT_MAX = 70;
  var HOLD_THRESHOLD = 50000;
  var BE_MIN_XMAX = 2000000;
  var BE_STEP = 100000;
  var BE_POINTS = 200;

  function num(v) {
    var n = Number(v);
    return isFinite(n) ? n : 0;
  }

  function pct(base, p) {
    var b = Math.trunc(num(base));
    if (b <= 0) { return 0; }
    return Math.floor((b * Math.trunc(num(p)) + 50) / 100);
  }

  function rates(gen, gen1Rate, gen2Type, gen3Type) {
    if (gen === 1) {
      if (gen1Rate === null || gen1Rate === undefined || gen1Rate === '') { return null; }
      var r = Math.round(num(gen1Rate));
      if (r < 0 || r > 100) { return null; }
      return { cov_in: r, cov_out: r, severe: r, mild: r };
    }
    if (gen === 2) {
      if (gen2Type === 'select1') { return { cov_in: 10, cov_out: 10, severe: 20, mild: 20 }; }
      return { cov_in: 20, cov_out: 20, severe: 20, mild: 20 };
    }
    if (gen === 3) {
      if (gen3Type === 'select2') { return { cov_in: 20, cov_out: 20, severe: 20, mild: 20 }; }
      return { cov_in: 10, cov_out: 10, severe: 20, mild: 20 };
    }
    if (gen === 4) { return { cov_in: 20, cov_out: 20, severe: 30, mild: 30 }; }
    if (gen === 5) { return { cov_in: 20, cov_out: 20, severe: 30, mild: 50 }; }
    return null;
  }

  function visitOop(amount, visits, rate, minVisit) {
    var amt = Math.max(0, Math.trunc(num(amount)));
    var v = Math.trunc(num(visits));
    if (amt === 0) { return 0; }
    if (v <= 0) { return pct(amt, rate); }
    var per = Math.floor((amt + Math.floor(v / 2)) / v);
    var one = pct(per, rate);
    if (minVisit) { one = Math.max(one, Math.trunc(minVisit)); }
    return Math.min(amt, one * v);
  }

  function limitCap(amount, oop, limit) {
    if (!limit) { return oop; }
    var paid = amount - oop;
    if (paid <= limit) { return oop; }
    return amount - limit;
  }

  function oopParts(gen, r, usage) {
    var inst = usage.inst || 'clinic';
    var minVisit = (DEDUCT[gen] || {})[inst];
    if (gen === 1) { minVisit = null; }
    var covIn = Math.max(0, Math.trunc(num(usage.in_cov)));
    var covOut = Math.max(0, Math.trunc(num(usage.out_cov)));
    var severe = Math.max(0, Math.trunc(num(usage.severe)));
    var mild = Math.max(0, Math.trunc(num(usage.mild)));
    var outVisits = Math.trunc(num(usage.out_visits));
    var mildVisits = Math.trunc(num(usage.mild_visits));
    var lim = LIMITS[gen] || {};
    var parts = {
      cov_in: pct(covIn, r.cov_in),
      cov_out: visitOop(covOut, outVisits, r.cov_out, minVisit),
      severe: limitCap(severe, pct(severe, r.severe), lim.severe),
      mild: visitOop(mild, mildVisits, r.mild, gen === 5 ? MILD5_MIN_VISIT : minVisit)
    };
    parts.mild = limitCap(mild, parts.mild, lim.mild);
    parts.total = parts.cov_in + parts.cov_out + parts.severe + parts.mild;
    return parts;
  }

  function premium5(pcur, mode, p5, discount, gen) {
    var cur = Math.max(0, Math.trunc(num(pcur)));
    if (mode === 'manual') { return { p5: Math.max(0, Math.trunc(num(p5))), estimated: false, discount: 0 }; }
    var d = (discount === null || discount === undefined) ? (EST_DISCOUNT[gen] || 30) : Math.trunc(num(discount));
    d = Math.max(DISCOUNT_MIN, Math.min(DISCOUNT_MAX, d));
    return { p5: pct(cur, 100 - d), estimated: true, discount: d };
  }

  function deltaAt(mildAmount, base, rCur, r5, gen, premiumSaving) {
    var usage = {};
    for (var k in base) { if (Object.prototype.hasOwnProperty.call(base, k)) { usage[k] = base[k]; } }
    usage.mild = Math.trunc(num(mildAmount));
    var cur = oopParts(gen, rCur, usage).total;
    var g5 = oopParts(5, r5, usage).total;
    return premiumSaving + (cur - g5);
  }

  function breakEven(base, rCur, r5, gen, premiumSaving, currentMild) {
    var xmax = Math.max(BE_MIN_XMAX, Math.trunc(num(currentMild)) * 2);
    xmax = Math.ceil(xmax / BE_STEP) * BE_STEP;
    var points = [];
    var prevX = 0;
    var prevD = deltaAt(0, base, rCur, r5, gen, premiumSaving);
    points.push([0, prevD]);
    var be = null;
    for (var i = 1; i <= BE_POINTS; i++) {
      var x = Math.floor(xmax * i / BE_POINTS);
      var d = deltaAt(x, base, rCur, r5, gen, premiumSaving);
      points.push([x, d]);
      if (be === null && ((prevD > 0) !== (d > 0))) {
        var denom = d - prevD;
        be = denom ? prevX + Math.trunc((0 - prevD) * (x - prevX) / denom) : x;
      }
      prevX = x;
      prevD = d;
    }
    var dir = null;
    if (be !== null) { dir = (points[points.length - 1][1] < points[0][1]) ? 'down' : 'up'; }
    return { xmax: xmax, points: points, break_even: be, dir: dir };
  }

  function compute(req) {
    req = req || {};
    var gen = Math.trunc(num(req.gen));
    var pcur = Math.max(0, Math.trunc(num(req.pcur)));
    var usage = {
      in_cov: Math.max(0, Math.trunc(num(req.in_cov))),
      out_cov: Math.max(0, Math.trunc(num(req.out_cov))),
      out_visits: Math.max(0, Math.trunc(num(req.out_visits))),
      severe: Math.max(0, Math.trunc(num(req.severe))),
      mild: Math.max(0, Math.trunc(num(req.mild))),
      mild_visits: Math.max(0, Math.trunc(num(req.mild_visits))),
      inst: req.inst || 'clinic'
    };
    var out = {
      ok: false, hold: null, gen: gen, pcur: pcur,
      p5: 0, p5_estimated: true, discount: EST_DISCOUNT[gen] || 30,
      oop_cur: 0, oop5: 0, premium_saving: 0, oop_increase: 0, delta: 0,
      verdict: 'hold', break_even: null, break_even_dir: null,
      chart: { xmax: BE_MIN_XMAX, points: [] },
      parts: {}, managed: !!req.managed
    };
    if (gen === 5) { out.hold = 'already_gen5'; out.ok = true; return out; }
    if (gen !== 1 && gen !== 2 && gen !== 3 && gen !== 4) { out.hold = 'gen_missing'; return out; }
    if (pcur <= 0) { out.hold = 'premium_unknown'; return out; }
    var rCur = rates(gen, req.gen1_rate === '' ? null : req.gen1_rate,
      req.gen2_type || 'standard', req.gen3_type || 'standard');
    if (!rCur) { out.hold = 'gen1_rate'; return out; }
    var r5 = rates(5);
    var prem = premium5(pcur, req.p5_mode === 'manual' ? 'manual' : 'auto', req.p5, req.discount, gen);
    if (prem.p5 <= 0) { out.hold = 'p5_missing'; return out; }

    var curParts = oopParts(gen, rCur, usage);
    var g5Parts = oopParts(5, r5, usage);
    var premiumSaving = (pcur - prem.p5) * 12;
    var oopIncrease = g5Parts.total - curParts.total;
    var delta = premiumSaving - oopIncrease;
    var verdict = 'hold';
    if (delta > HOLD_THRESHOLD) { verdict = 'save'; }
    else if (delta < -HOLD_THRESHOLD) { verdict = 'loss'; }
    var be = breakEven(usage, rCur, r5, gen, premiumSaving, usage.mild);

    out.ok = true;
    out.p5 = prem.p5;
    out.p5_estimated = prem.estimated;
    out.discount = prem.estimated ? prem.discount : 0;
    out.oop_cur = curParts.total;
    out.oop5 = g5Parts.total;
    out.premium_saving = premiumSaving;
    out.oop_increase = oopIncrease;
    out.delta = delta;
    out.verdict = verdict;
    out.break_even = be.break_even;
    out.break_even_dir = be.dir;
    out.chart = { xmax: be.xmax, points: be.points };
    out.parts = { cur: curParts, gen5: g5Parts };
    return out;
  }

  root.Gen5Sim = { compute: compute, rates: rates, oopParts: oopParts, HOLD_THRESHOLD: HOLD_THRESHOLD };

  /* ------------------------------------------------------------ 화면 (있을 때만) */
  if (typeof document === 'undefined') { return; }

  function $(sel, sc) { return (sc || document).querySelector(sel); }
  function $all(sel, sc) { return Array.prototype.slice.call((sc || document).querySelectorAll(sel)); }
  function won(n) { return String(Math.round(num(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '원'; }
  function manwon(n) {
    var v = Math.round(num(n));
    if (Math.abs(v) >= 100000000) { return (v / 100000000).toFixed(v % 100000000 === 0 ? 0 : 1) + '억원'; }
    if (Math.abs(v) >= 10000) { return Math.round(v / 10000) + '만원'; }
    return v + '원';
  }
  function signed(n) { return (n > 0 ? '+' : n < 0 ? '−' : '') + won(Math.abs(n)); }

  function init() {
    var form = $('[data-sim]');
    if (!form) { return; }
    var resultBox = $('#sim-result');
    var out = $('#sim-out');
    var base = form.getAttribute('data-base') || (location.origin + '');
    var gen = 4;
    var pcurUnknown = false;
    var last = null;

    function val(k) {
      var el = $('[data-k="' + k + '"]', form);
      if (!el) { return null; }
      if (el.type === 'checkbox') { return el.checked; }
      return el.value;
    }
    function setSeg(k, v) {
      $all('[data-seg="' + k + '"]', form).forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === String(v)));
      });
    }
    function syncRange(k) {
      var n = $('[data-k="' + k + '"]', form);
      var r = $('[data-range="' + k + '"]', form);
      if (!n || !r) { return; }
      if (document.activeElement === r) { n.value = r.value; }
      else { r.value = Math.min(Number(r.max) || 20000000, Math.max(0, num(n.value))); }
    }
    function setHidden(el, hidden) {
      if (!el) { return; }
      if (hidden) { el.setAttribute('hidden', ''); } else { el.removeAttribute('hidden'); }
    }

    function read() {
      var g = gen;
      var req = {
        gen: g,
        gen1_rate: val('gen1_rate'),
        gen2_type: val('gen2_type') || 'standard',
        gen3_type: val('gen3_type') || 'standard',
        pcur: pcurUnknown ? 0 : Math.trunc(num(val('pcur'))),
        p5_mode: val('p5_mode') || 'auto',
        p5: Math.trunc(num(val('p5'))),
        discount: gen >= 1 ? Math.trunc(num(val('discount'))) : 0,
        in_cov: Math.trunc(num(val('in_cov'))),
        out_cov: Math.trunc(num(val('out_cov'))),
        out_visits: Math.trunc(num(val('out_visits'))),
        severe: Math.trunc(num(val('severe'))),
        mild: Math.trunc(num(val('mild'))),
        mild_visits: Math.trunc(num(val('mild_visits'))),
        inst: val('inst') || 'clinic',
        managed: !!val('managed')
      };
      return req;
    }

    function holdMessage(code) {
      if (code === 'already_gen5') {
        return '<div class="sim-hold"><b>이미 5세대 실손입니다.</b> 5세대에서 다른 세대로 되돌아가는 전환은 없습니다. ' +
          '아래 세대별 자기부담 구조표로 내 조건의 보장 수준을 확인할 수 있습니다.</div>';
      }
      if (code === 'premium_unknown') {
        return '<div class="sim-hold"><b>현재 월 보험료를 입력하면 결과가 나옵니다.</b> 보험료를 모르면 보험사 앱·' +
          '보험증권·보험료 납입 내역에서 확인할 수 있습니다. 일반적으로 4세대는 월 1만~3만 원대, 1·2세대는 ' +
          '월 3만~10만 원대의 분포가 보고되지만 가입 시기·상품·연령에 따라 크게 다르므로 계산에는 쓰지 않습니다.</div>';
      }
      if (code === 'gen1_rate') {
        return '<div class="sim-hold"><b>1세대는 약관상 자기부담률을 직접 입력해야 계산할 수 있습니다.</b> ' +
          '1세대는 계약별 자기부담이 달라(생명보험 20%·손해보험 0% 등) 단일 기준이 없습니다. 보험증권·약관의 ' +
          '자기부담률을 확인해 입력해 주세요.</div>';
      }
      if (code === 'p5_missing') {
        return '<div class="sim-hold"><b>5세대 월 보험료를 입력하거나 자동 추정을 선택해 주세요.</b></div>';
      }
      return '<div class="sim-hold"><b>현재 실손 세대를 선택해 주세요.</b></div>';
    }

    function verdictText(res) {
      if (res.verdict === 'save') {
        return '입력한 이용 패턴으로는 5세대로 전환하면 연간 약 ' + won(res.delta) + ' 절약되는 것으로 계산됩니다.';
      }
      if (res.verdict === 'loss') {
        return '입력한 이용 패턴으로는 지금 세대를 유지하는 쪽이 연간 약 ' + won(-res.delta) + ' 유리한 것으로 계산됩니다.';
      }
      return '절감액과 증가액이 비슷해 이용 패턴이 조금만 달라져도 결과가 바뀝니다. 전환 전 약관과 철회 기한을 꼭 확인하세요.';
    }

    function chartSvg(res) {
      var pts = res.chart.points || [];
      if (!pts.length) { return ''; }
      // 다크모드에서는 어두운 카드 위에서도 읽히는 팔레트로 그린다(공유 이미지 카드는 라이트 고정).
      var DARK = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      var C = DARK
        ? { bg: 'none', grid: '#26302a', label: '#8d9991', zero: '#5f6f66', axis: '#b6c0ba', curve: '#14b8a6', be: '#f2b04e', cur: '#8db1ff' }
        : { bg: '#fff', grid: '#eef2f7', label: '#98a2b3', zero: '#94a3b8', axis: '#344054', curve: '#0f766e', be: '#b45309', cur: '#1d4ed8' };
      var W = Math.max(280, Math.min(900, (out.clientWidth || 340) - 2));
      var big = W >= 560;
      var H = big ? 260 : 215;
      var L = big ? 62 : 48, R = 14, T = 24, B = big ? 46 : 40;
      var FS = big ? 11.5 : 10.5;
      var xs = pts.map(function (p) { return p[0]; });
      var ys = pts.map(function (p) { return p[1]; });
      var maxX = Math.max.apply(null, xs) || 1;
      var minY = Math.min.apply(null, ys.concat([0]));
      var maxY = Math.max.apply(null, ys.concat([0]));
      if (maxY === minY) { maxY = minY + 10000; }
      var pad = (maxY - minY) * 0.12;
      minY -= pad; maxY += pad;
      function sx(x) { return L + (W - L - R) * (x / maxX); }
      function sy(y) { return T + (H - T - B) * (1 - (y - minY) / (maxY - minY)); }
      var path = pts.map(function (p, i) {
        return (i ? 'L' : 'M') + sx(p[0]).toFixed(1) + ' ' + sy(p[1]).toFixed(1);
      }).join(' ');
      var cur = Math.trunc(num(val('mild')));
      var curY = deltaLocal(res, cur);
      var parts = [];
      parts.push('<svg class="sim-chart-svg" viewBox="0 0 ' + W + ' ' + H +
        '" role="img" aria-label="비중증 비급여 연간 이용액에 따른 전환 손익 곡선">');
      parts.push('<rect x="0" y="0" width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>');
      // 가로 그리드 + y축 금액 라벨
      [0, 0.5, 1].forEach(function (t) {
        var gy = T + (H - T - B) * t;
        var gv = maxY - (maxY - minY) * t;
        parts.push('<line x1="' + L + '" y1="' + gy.toFixed(1) + '" x2="' + (W - R) + '" y2="' + gy.toFixed(1) +
          '" stroke="' + C.grid + '"/>');
        parts.push('<text x="' + (L - 6) + '" y="' + (gy + 3.5).toFixed(1) + '" text-anchor="end" font-size="' + FS +
          '" fill="' + C.label + '">' + (Math.abs(gv) >= 10000 ? manwon(gv) : Math.round(gv) + '원') + '</text>');
      });
      // 0선
      var zy = sy(0);
      parts.push('<line x1="' + L + '" y1="' + zy.toFixed(1) + '" x2="' + (W - R) + '" y2="' + zy.toFixed(1) +
        '" stroke="' + C.zero + '" stroke-width="1.3" stroke-dasharray="5 4"/>');
      // 곡선
      parts.push('<path d="' + path + '" fill="none" stroke="' + C.curve + '" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>');
      // 손익분기 세로선
      if (res.break_even !== null && res.break_even > 0 && res.break_even < maxX) {
        var bx = sx(res.break_even);
        parts.push('<line x1="' + bx.toFixed(1) + '" y1="' + T + '" x2="' + bx.toFixed(1) + '" y2="' + (H - B) +
          '" stroke="' + C.be + '" stroke-width="1.3"/>');
        parts.push('<text x="' + bx.toFixed(1) + '" y="' + (H - B + 13) + '" text-anchor="middle" font-size="' + FS +
          '" fill="' + C.be + '" font-weight="700">손익분기</text>');
      }
      // 현재 입력 위치
      if (cur <= maxX) {
        var cx = sx(cur);
        parts.push('<line x1="' + cx.toFixed(1) + '" y1="' + T + '" x2="' + cx.toFixed(1) + '" y2="' + (H - B) +
          '" stroke="' + C.cur + '" stroke-width="1.1" stroke-dasharray="4 3"/>');
        parts.push('<circle cx="' + cx.toFixed(1) + '" cy="' + sy(curY).toFixed(1) + '" r="4.4" fill="' + C.cur + '"/>');
        parts.push('<text x="' + (cx > W * 0.72 ? cx - 6 : cx + 6).toFixed(1) + '" y="' + (T - 8) +
          '" text-anchor="' + (cx > W * 0.72 ? 'end' : 'start') + '" font-size="' + FS + '" fill="' + C.cur + '" font-weight="700">내 입력</text>');
      }
      // x축 라벨
      [0, 0.5, 1].forEach(function (t) {
        var x = L + (W - L - R) * t;
        parts.push('<text x="' + x.toFixed(1) + '" y="' + (H - B + 13) + '" text-anchor="' +
          (t === 0 ? 'start' : t === 1 ? 'end' : 'middle') + '" font-size="' + FS + '" fill="' + C.label + '">' + manwon(maxX * t) + '</text>');
      });
      // 축 이름
      parts.push('<text x="' + (L + (W - L - R) / 2).toFixed(1) + '" y="' + (H - 5) +
        '" text-anchor="middle" font-size="' + FS + '" fill="' + C.axis + '">연간 비중증 비급여 이용액</text>');
      parts.push('</svg>');
      return parts.join('');
    }

    function deltaLocal(res, mildAmount) {
      // 그래프의 현재 점 — 엔진 결과에서 mild 를 바꾼 값을 그대로 쓴다(곡선과 같은 식).
      var pts = res.chart.points;
      var best = pts[0];
      var dist = Math.abs(pts[0][0] - mildAmount);
      for (var i = 1; i < pts.length; i++) {
        var d = Math.abs(pts[i][0] - mildAmount);
        if (d < dist) { dist = d; best = pts[i]; }
      }
      return best[1];
    }

    function breakEvenLine(res) {
      if (res.break_even === null) {
        var p0 = res.chart.points[0][1];
        if (p0 > 0) { return '비중증 비급여를 쓰지 않아도 전환이 유리하고, 계산 범위 안에서는 역전되지 않습니다.'; }
        return '계산 범위 안에서 손익분기가 나타나지 않습니다(현재 조건에서는 유지가 유리).';
      }
      var amt = won(res.break_even);
      if (res.break_even_dir === 'down') {
        return '비중증 비급여를 연 ' + amt + ' 넘게 쓰면 전환이 손해로 바뀝니다.';
      }
      return '비중증 비급여를 연 ' + amt + ' 넘게 쓰면 전환이 유리해집니다.';
    }

    function render() {
      var req = read();
      var res = compute(req);
      last = res;
      if (!res.ok || res.verdict === 'hold' && res.hold) {
        if (res.hold) {
          out.innerHTML = holdMessage(res.hold) + disclaimers(req);
          $all('[data-share]', resultBox).forEach(function (b) { b.disabled = true; });
        }
        return;
      }
      var cls = res.verdict === 'save' ? 'is-save' : res.verdict === 'loss' ? 'is-loss' : 'is-hold';
      var label = res.verdict === 'save' ? '전환 유리' : res.verdict === 'loss' ? '유지 유리' : '판단 보류';
      var big = res.verdict === 'save' ? '연 ' + won(res.delta) + ' <em>절약</em>'
        : res.verdict === 'loss' ? '연 ' + won(-res.delta) + ' <em>손해</em>'
          : '연 ' + won(Math.abs(res.delta)) + ' 차이 <em>판단 보류</em>';
      var p5txt = res.p5_estimated
        ? won(res.p5) + ' <span class="sim-est">추정치 · 인하율 ' + res.discount + '% 적용</span>'
        : won(res.p5) + ' <span class="sim-est">직접 입력</span>';
      var html = [];
      html.push('<div class="sim-verdict ' + cls + '">');
      html.push('<div class="sim-badge">' + label + '</div>');
      html.push('<div class="sim-big">' + big + '</div>');
      html.push('<p class="sim-say">' + verdictText(res) + '</p>');
      html.push('</div>');
      html.push('<div class="sim-costs">');
      html.push('<div><span class="k">현재 세대 월 보험료</span><b>' + won(req.pcur) + '</b></div>');
      html.push('<div><span class="k">5세대 월 보험료</span><b>' + p5txt + '</b></div>');
      html.push('<div><span class="k">연간 총비용(현재)</span><b>' + won(req.pcur * 12 + res.oop_cur) +
        '</b></div>');
      html.push('<div><span class="k">연간 총비용(5세대)</span><b>' + won(res.p5 * 12 + res.oop5) + '</b></div>');
      html.push('</div>');
      html.push('<h4 class="sim-h4">판단 근거 3줄</h4>');
      html.push('<ul class="sim-why">');
      html.push('<li><b>보험료 절감액</b> (월 ' + won(req.pcur) + ' → ' + won(res.p5) + ') · 연 <b>' + signed(res.premium_saving) + '</b></li>');
      html.push('<li><b>자기부담 증가액</b> (현재 ' + won(res.oop_cur) + ' → 5세대 ' + won(res.oop5) + ') · 연 <b>' + signed(res.oop_increase) + '</b>' +
        (res.oop_increase > 0 ? ' <span class="sim-hint">주로 비중증 비급여 50% 적용분</span>' : '') + '</li>');
      html.push('<li><b>손익분기</b> ' + breakEvenLine(res) + '</li>');
      html.push('</ul>');
      html.push('<h4 class="sim-h4">손익분기 그래프</h4>');
      html.push('<div class="sim-chart">' + chartSvg(res) + '</div>');
      html.push('<p class="sim-legend"><span class="lg-cur">내 입력 위치</span><span class="lg-be">손익분기</span>' +
        '<span class="lg-zero">가로 점선 = 손익 0원</span></p>');
      html.push('<p class="calc-foot" style="margin-top:2px">곡선은 비중증 비급여 연간 이용액만 바꿔 계산한 전환 손익입니다. ' +
        '점선 위쪽(양수)은 전환 시 절약, 아래쪽(음수)은 손해입니다.</p>');
      if (req.severe > 0) {
        html.push('<div class="notice" style="margin-top:12px"><b>중증 비급여 보호</b> — 중증 비급여는 5세대에서도 30%로 계산되고, ' +
          '연간 보장한도 5,000만 원이 적용됩니다. 상급종합·종합병원 입원은 연간 자기부담 상한 500만 원이 별도로 적용되지만 ' +
          '입원 여부·기관에 따라 달라 1차 계산에는 넣지 않았습니다.</div>');
      }
      html.push(disclaimers(req));
      out.innerHTML = html.join('');
      $all('[data-share]', resultBox).forEach(function (b) { b.disabled = false; });
    }

    function disclaimers(req) {
      var d = [];
      d.push('<div class="sim-notes">');
      d.push('<h4>꼭 확인하세요</h4>');
      d.push('<div class="note-row"><b>참고용 추정치</b> — 이 결과는 입력한 값과 공개된 표준 자기부담률을 바탕으로 한 참고용 추정치입니다. ' +
        '실제 보장·보험료는 가입한 상품의 약관과 상품설명서 기준이며, 보험사·상품마다 다릅니다. 전환 전 약관을 확인하고, ' +
        '궁금한 점은 금융감독원 상담센터(국번 없이 1332)에 문의하세요.</div>');
      d.push('<div class="note-row"><b>보험료 할증</b> — 비급여 이용량에 따라 차기 갱신 시 할증될 수 있습니다(할증률은 보험사·상품별로 다릅니다). ' +
        '5세대 특약2 차등제의 첫 적용은 2028년 5월 이후 갱신분부터입니다. 할증 반영 계산은 준비 중입니다.</div>');
      d.push('<div class="note-row"><b>관리급여</b> — 관리급여는 급여로 편입되어 실손 급여 담보로 보상됩니다. 다만 선택형 할인 특약의 ' +
        '면책 옵션 선택 시 보장에서 제외될 수 있습니다. 도수치료는 2026년 7월 1일부터 본인부담 95%(1회 43,850원 표준가격, 주 2회·연 15회, ' +
        '예외 최대 24회)로 급여 규칙이 적용되며, 5세대 자기부담률은 입원 20%·외래 95%입니다. 이 계산에는 금액을 넣지 않았습니다.' +
        (req.managed ? ' 입력하신 관리급여 이용은 위 안내 기준으로 따로 확인하세요.' : '') + '</div>');
      d.push('<div class="note-row"><b>계약전환 할인·선택형 할인 특약</b> — 2013년 3월 이전에 판매된 재가입 조건 없는 초기 실손(약 1,700만 명)을 대상으로 ' +
        '계약전환 할인(3년간 50%, 6개월 한시 적용 후 연장 여부 검토)과 선택형 할인 특약이 2026년 11월 동시 시행됩니다. ' +
        '선택형 옵션은 근골격계 물리치료·체외충격파·비급여 주사제 면책, 비급여 MRI·MRA 면책, 자기부담률 20% 상향의 3가지이고 ' +
        '기한 없이 1회만 신청할 수 있습니다. 이 계산에는 반영하지 않았습니다.</div>');
      d.push('<div class="note-row"><b>재가입 주기</b> — 4·5세대는 5년마다 재가입(갱신)하며, 재가입 시점의 약관이 적용됩니다. ' +
        '약관은 변경될 수 있습니다.</div>');
      d.push('<div class="note-row"><b>철회 기한</b> — 전환 후 3개월 이내에는 조건 없이 철회할 수 있고, 3~6개월은 보험금을 받지 않은 경우에만 ' +
        '철회할 수 있으며, 6개월이 지나면 철회할 수 없습니다. 철회 시 전환 전후 보험료 차액을 정산하고, 전환 후 발생한 사고는 전환 전 계약에서 ' +
        '보장하며, 철회 후 5세대로 다시 전환하려면 별도 심사를 거칩니다.</div>');
      d.push('<div class="note-row"><b>계산에 넣지 않은 한도</b> — 5세대 비중증 통원 일당 보장 20만 원·병·의원 입원 회당 보장 300만 원, ' +
        '4세대 비급여 통원 회당 보장 20만 원, 3세대 비급여 특약 30% 등은 회차별 세부 정보가 필요해 1차 계산에서 제외했습니다. ' +
        '통원 횟수를 입력하면 건별 최소 자기부담금만 반영합니다.</div>');
      d.push('<div class="note-row"><b>입력값 보호</b> — 입력한 보험료·이용 금액은 브라우저 안에서만 계산하며 서버로 보내거나 저장하지 않습니다. ' +
        '공유 링크에도 입력값을 담지 않습니다.</div>');
      d.push('</div>');
      return d.join('');
    }

    /* ---------------------------------------------------------- 공유 · 카드 */
    function shareUrl(src, content) {
      return base + '/ko/switch-gen5/?utm_source=' + src +
        '&utm_medium=share_card&utm_campaign=gen5-simulator&utm_content=' + content;
    }
    function contentKey() {
      if (!last || !last.ok || last.hold) { return 'result-hold'; }
      return last.verdict === 'save' ? 'result-save' : last.verdict === 'loss' ? 'result-loss' : 'result-hold';
    }
    function shareLine() {
      var res = last || {};
      if (!res.ok || res.hold) { return '실손 5세대 전환, 내 조건에서는 얼마가 달라질까?'; }
      if (res.verdict === 'save') { return '나는 5세대 전환 시 연 ' + won(res.delta) + ' 절약'; }
      if (res.verdict === 'loss') { return '나는 5세대 전환 시 연 ' + won(-res.delta) + ' 손해'; }
      return '나는 5세대 전환 손익이 판단 보류(연 ' + won(Math.abs(res.delta)) + ' 차이)';
    }
    function resultOneLine() {
      var res = last || {};
      if (!res.ok || res.hold) { return '내 조건으로 1분 만에 확인하기'; }
      if (res.break_even !== null && res.break_even_dir === 'down') {
        return '비중증 비급여 연 ' + manwon(res.break_even) + ' 넘으면 유지가 유리';
      }
      if (res.break_even !== null && res.break_even_dir === 'up') {
        return '비중증 비급여 연 ' + manwon(res.break_even) + ' 넘으면 전환이 유리';
      }
      return res.verdict === 'save' ? '입력한 이용 패턴에서는 전환이 유리' : '입력한 이용 패턴에서는 유지가 유리';
    }

    function drawCard() {
      var W = 1200, H = 630;
      var cv = document.createElement('canvas');
      cv.width = W; cv.height = H;
      var c = cv.getContext('2d');
      var g = c.createLinearGradient(0, 0, W, H);
      g.addColorStop(0, '#ffffff');
      g.addColorStop(0.55, '#f4fbf9');
      g.addColorStop(1, '#e6f4f1');
      c.fillStyle = g; c.fillRect(0, 0, W, H);
      c.fillStyle = '#0f2942'; c.fillRect(0, 0, W, 10);
      var res = last || {};
      var ok = res.ok && !res.hold;
      var save = ok && res.verdict === 'save';
      var loss = ok && res.verdict === 'loss';
      var accent = save ? '#0f766e' : loss ? '#b42318' : '#b45309';
      // 로고 마크
      c.fillStyle = '#0f2942';
      roundRect(c, 72, 62, 56, 56, 14); c.fill();
      c.strokeStyle = '#14b8a6'; c.lineWidth = 8; c.lineCap = 'round';
      c.beginPath(); c.moveTo(100, 76); c.lineTo(100, 104); c.moveTo(86, 90); c.lineTo(114, 90); c.stroke();
      c.fillStyle = '#344054'; c.font = '600 26px ' + FONT;
      c.fillText('K-MediCheck · 메디컬 비급여 시세 파인더', 146, 100);
      c.fillStyle = '#0f2942'; c.font = '800 60px ' + FONT;
      c.fillText('실손 5세대 전환 손익', 72, 220);
      c.fillStyle = '#667085'; c.font = '500 28px ' + FONT;
      c.fillText('내 조건으로 계산한 참고용 추정치', 72, 270);
      // 큰 숫자
      var bigTxt = ok ? (save ? '연 ' + won(res.delta) : loss ? '연 ' + won(-res.delta) : '연 ' + won(Math.abs(res.delta)))
        : '내 조건으로 확인하기';
      var tagTxt = ok ? (save ? '절약' : loss ? '손해' : '판단 보류') : '';
      c.fillStyle = accent; c.font = '800 104px ' + FONT;
      var bigW = c.measureText(bigTxt).width;
      c.fillText(bigTxt, 72, 410);
      if (tagTxt) {
        c.font = '800 60px ' + FONT;
        c.fillText(tagTxt, 72 + bigW + 24, 410);
      }
      // 판단 근거 1줄
      c.fillStyle = '#344054'; c.font = '600 34px ' + FONT;
      wrapText(c, resultOneLine(), 72, 492, W - 144, 44, 2);
      // 하단
      c.fillStyle = '#0f2942'; c.fillRect(0, H - 84, W, 84);
      c.fillStyle = '#ffffff'; c.font = '700 30px ' + FONT;
      c.fillText('medical-finder-kr.pages.dev', 72, H - 34);
      c.fillStyle = '#a7c4bf'; c.font = '500 22px ' + FONT;
      c.textAlign = 'right';
      c.fillText('참고용 추정치 · 약관 확인 · 금융감독원 1332', W - 72, H - 36);
      c.textAlign = 'left';
      return cv;
    }
    var FONT = '"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR","Noto Sans CJK KR",sans-serif';
    function roundRect(c, x, y, w, h, r) {
      c.beginPath();
      c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
      c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
    }
    function wrapText(c, text, x, y, maxW, lh, maxLines) {
      var words = String(text).split(' ');
      var line = '';
      var n = 0;
      for (var i = 0; i < words.length; i++) {
        var test = line ? line + ' ' + words[i] : words[i];
        if (c.measureText(test).width > maxW && line) {
          c.fillText(line, x, y + n * lh); n++;
          line = words[i];
          if (maxLines && n >= maxLines) { return; }
        } else { line = test; }
      }
      if (line) { c.fillText(line, x, y + n * lh); }
    }
    function cardName() {
      var k = contentKey();
      return 'silson-gen5-' + (k === 'result-save' ? 'save' : k === 'result-loss' ? 'loss' : 'hold') + '.png';
    }
    function downloadCard() {
      var cv = drawCard();
      var a = document.createElement('a');
      a.download = cardName();
      a.href = cv.toDataURL('image/png');
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      flash('결과 카드를 저장했습니다. 이미지에 개인 입력값은 담기지 않습니다.');
    }
    function cardBlob(cb) {
      var cv = drawCard();
      if (cv.toBlob) { cv.toBlob(function (b) { cb(b); }, 'image/png'); }
      else { cb(null); }
    }
    function flash(msg) {
      var el = $('#sim-share-msg');
      if (!el) { return; }
      el.textContent = msg;
      clearTimeout(flash._t);
      flash._t = setTimeout(function () { el.textContent = ''; }, 5200);
    }
    function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
      }
      return Promise.resolve(legacyCopy(text));
    }
    function legacyCopy(text) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.top = '-1000px';
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }

    $all('[data-share]', resultBox).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var kind = btn.getAttribute('data-share');
        var content = contentKey();
        var line = shareLine();
        if (kind === 'card') { downloadCard(); return; }
        if (kind === 'kakao') {
          var url = shareUrl('kakaotalk', content);
          var msg = '[실손 5세대 전환 손익] ' + line + '. 내 결과 확인하기 👉 ' + url;
          if (navigator.share) {
            navigator.share({ title: '실손 5세대 전환 손익', text: line, url: url }).catch(function () { /* 취소 */ });
          } else {
            copyText(msg).then(function (ok) {
              flash(ok ? '카카오톡에 붙여넣을 문구를 복사했습니다. 대화창에 붙여넣기 해 주세요.' : '복사가 차단되었습니다. 주소를 직접 복사해 주세요: ' + url);
            });
          }
          return;
        }
        if (kind === 'image') {
          var iurl = shareUrl('og_share', content);
          cardBlob(function (blob) {
            var file = null;
            try { file = blob ? new File([blob], cardName(), { type: 'image/png' }) : null; } catch (e) { file = null; }
            if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
              navigator.share({ files: [file], title: '실손 5세대 전환 손익', text: line, url: iurl })
                .catch(function () { /* 취소 */ });
            } else {
              downloadCard();
              copyText(line + ' 👉 ' + iurl).then(function () {
                flash('이 브라우저는 이미지 공유를 지원하지 않아 카드를 저장했습니다. 문구도 함께 복사했습니다.');
              });
            }
          });
          return;
        }
        if (kind === 'copy') {
          var curl = shareUrl('link_copy', content);
          copyText(curl).then(function (ok) {
            if (ok) { flash('결과 링크를 복사했습니다. (utm_source=link_copy)'); }
            else {
              var el = $('#sim-link');
              if (el) { el.value = curl; el.hidden = false; el.select(); }
              flash('복사가 차단되었습니다. 아래 주소를 직접 복사해 주세요.');
            }
          });
        }
      });
    });

    /* ---------------------------------------------------------- 입력 이벤트 */
    $all('[data-seg="gen"]', form).forEach(function (b) {
      b.addEventListener('click', function () {
        gen = Number(b.getAttribute('data-v'));
        setSeg('gen', gen);
        setHidden($('#gen1-row', form), gen !== 1);
        setHidden($('#gen2-row', form), gen !== 2);
        setHidden($('#gen3-row', form), gen !== 3);
        var note = $('#gen-period', form);
        if (note) {
          var periods = { 1: '2009년 9월까지 가입', 2: '2009년 10월~2017년 3월 가입', 3: '2017년 4월~2021년 6월 가입', 4: '2021년 7월~2026년 4월 가입', 5: '2026년 5월 6일 이후 가입' };
          note.textContent = periods[gen] || '';
        }
        var dsug = $('[data-k="discount"]', form);
        if (dsug && EST_DISCOUNT[gen]) { dsug.value = EST_DISCOUNT[gen]; }
        var dlabel = $('#discount-val', form);
        if (dlabel) { dlabel.textContent = (dsug ? dsug.value : EST_DISCOUNT[gen]) + '%'; }
        render();
      });
    });
    $all('[data-seg="p5_mode"]', form).forEach(function (b) {
      b.addEventListener('click', function () {
        var mode = b.getAttribute('data-v');
        setSeg('p5_mode', mode);
        $('[data-k="p5_mode"]', form).value = mode;
        setHidden($('#p5-auto-row', form), mode !== 'auto');
        setHidden($('#p5-manual-row', form), mode !== 'manual');
        render();
      });
    });
    var unknownBtn = $('#pcur-unknown', form);
    if (unknownBtn) {
      unknownBtn.addEventListener('click', function () {
        pcurUnknown = !pcurUnknown;
        unknownBtn.setAttribute('aria-pressed', String(pcurUnknown));
        unknownBtn.textContent = pcurUnknown ? '모름 (입력 안 함)' : '모름';
        var inp = $('[data-k="pcur"]', form);
        if (inp) { inp.disabled = pcurUnknown; }
        render();
      });
    }
    $all('[data-range]', form).forEach(function (r) {
      r.addEventListener('input', function () {
        var k = r.getAttribute('data-range');
        var n = $('[data-k="' + k + '"]', form);
        if (n) { n.value = r.value; }
        render();
      });
    });
    form.addEventListener('input', function (e) {
      var k = e.target.getAttribute && e.target.getAttribute('data-k');
      if (k && k !== 'p5_mode') { syncRange(k); }
      render();
    });
    form.addEventListener('change', render);
    form.addEventListener('submit', function (e) { e.preventDefault(); render(); });

    var resizeTimer = null;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 180);
    });

    // 기기 테마가 페이지 열린 채로 바뀌면 차트 팔레트도 따라 다시 그린다.
    if (window.matchMedia) {
      var schemeMq = window.matchMedia('(prefers-color-scheme: dark)');
      if (schemeMq.addEventListener) { schemeMq.addEventListener('change', render); }
    }

    setSeg('p5_mode', 'auto');
    $('[data-k="p5_mode"]', form).value = 'auto';
    setHidden($('#p5-manual-row', form), true);
    render();
    form.setAttribute('data-ready', '1');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
