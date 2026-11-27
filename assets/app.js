/*!
 * app.js — 계산기 화면 바인딩
 * 계산은 전부 calc.js(MedCalc)가 하고, 이 파일은 입력·출력만 다룬다.
 * 페이지에 [data-calc] 블록이 여러 개 있어도 각각 독립적으로 동작한다.
 */
(function () {
  'use strict';
  var CAT = (window.MED_CATALOG && window.MED_CATALOG.items) || [];
  var PREVIEW = !!window.MED_PREVIEW;

  function $(root, sel) { return root.querySelector(sel); }
  function $all(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  function fmt(n) { return MedCalc.won(n); }

  // ------------------------------------------------ 분석 이벤트(GA4, 선택적)
  // gtag 가 없거나 차단돼도 계산 동작에는 영향이 없다.
  function track(name, params) {
    if (typeof window.gtag !== 'function') { return; }
    try { window.gtag('event', name, params || {}); } catch (e) { /* 무시 */ }
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = text; }
    return n;
  }
  function itemByCode(code) {
    for (var i = 0; i < CAT.length; i++) { if (CAT[i].code === code) { return CAT[i]; } }
    return null;
  }
  function defAmount(it) {
    if (it && it.payment === '관리급여') { return it.price_fixture; }
    return (it && (it.amount_default || it.price_fixture)) || 300000;
  }

  function init(root) {
    var sel = $(root, '#item-select');
    if (!sel) { return; }

    var state = {
      item: CAT.length ? CAT[0].code : 'direct',
      amount: CAT.length ? defAmount(CAT[0]) : 300000,
      visit: 'out',
      inst: 'tertiary',
      severe: 0,
      gen2: 'unknown',
      rounds: 1,
      severeCum: 0
    };

    // ---------------------------------------------------- 딥링크(?item=…)
    try {
      var qs = new URLSearchParams(location.search);
      if (qs.get('item') && (qs.get('item') === 'direct' || itemByCode(qs.get('item')))) { state.item = qs.get('item'); }
      if (qs.get('visit') === 'in') { state.visit = 'in'; }
      if (qs.get('inst') && MedCalc.INSTITUTIONS[qs.get('inst')]) { state.inst = qs.get('inst'); }
      if (qs.get('severe') === '1') { state.severe = 1; }
      // 2세대 유형: early(전기) · late10/late20/sel2(후기 형별) · unknown(모름, 기본값).
      // 구 링크의 standard 는 late20, select2 는 sel2 로 읽는다.
      if (['early', 'late10', 'late20', 'sel2', 'unknown'].indexOf(qs.get('gen2')) >= 0) { state.gen2 = qs.get('gen2'); }
      if (qs.get('rounds')) { state.rounds = Math.max(1, parseInt(qs.get('rounds'), 10) || 1); }
      if (qs.get('amount') !== null && qs.get('amount') !== '') {
        // M-03: -1000 을 1000 으로 바꾸지 않고 그대로 읽어 검증 단계에서 막는다.
        var qa = Number(qs.get('amount'));
        state.amount = isFinite(qa) ? qa : NaN;
      } else {
        state.amount = state.item === 'direct' ? 300000 : defAmount(itemByCode(state.item));
      }
    } catch (e) { /* file:// 등에서 URLSearchParams 실패 시 기본값 유지 */ }

    var amountInput = $(root, '#amount-input');
    var roundsInput = $(root, '#rounds-input');
    var cumInput = $(root, '#severe-cum-input');
    var hint = $(root, '#item-hint');
    var chip = $(root, '#amount-chip');
    var managedBox = $(root, '#managed-box');
    var roundsRow = $(root, '#rounds-row');
    var severeCumRow = $(root, '#severe-cum-row');
    var tbody = $(root, '#result-table tbody');
    var summary = $(root, '#result-summary');
    var warnBox = $(root, '#result-warnings');
    var metaBox = $(root, '#result-meta');
    var amountError = $(root, '#amount-error');

    // ---------------------------------------------------- 금액 검증 (M-03)
    // 0·빈 값·읍수는 계산하지 않고 입력란 열에 바로 안내한다(조용한 0원 계산 금지).
    var AMOUNT_MAX_WARN = 500000000;  // 5억 원 — 넘으면 자릿수 오타 확인 안내
    function amountProblem() {
      var raw = String(amountInput.value == null ? '' : amountInput.value).trim();
      var n = state.amount;
      if (raw === '' || typeof n !== 'number' || !isFinite(n)) { return '금액을 입력해 주세요.'; }
      if (n < 0) { return '금액은 0보다 큰 값으로 입력해 주세요.'; }
      if (n === 0) { return '금액은 0보다 큰 값으로 입력해 주세요.'; }
      return '';
    }
    function setAmountError(msg) {
      if (amountError) {
        amountError.textContent = msg || '';
        amountError.hidden = !msg;
      }
      if (msg) { amountInput.setAttribute('aria-invalid', 'true'); amountInput.classList.add('is-invalid'); }
      else { amountInput.removeAttribute('aria-invalid'); amountInput.classList.remove('is-invalid'); }
    }

    // ---------------------------------------------------- 항목 목록
    // calc_block()이 서버에서 옵션을 이미 렌더링하므로, JS에서 다시 채우기
    // 전에 비운다. 안 비우면 서버 35개 + JS 35개 = 70개 중복 표시가 된다.
    while (sel.options.length) { sel.remove(0); }
    CAT.forEach(function (it) {
      var o = el('option', null, it.name + ' (' + it.code + ')');
      o.value = it.code;
      sel.appendChild(o);
    });
    var directOpt = el('option', null, '직접 입력 (금액만)');
    directOpt.value = 'direct';
    sel.appendChild(directOpt);
    sel.value = state.item;

    function currentItem() { return state.item === 'direct' ? null : itemByCode(state.item); }
    function isManaged() { var it = currentItem(); return !!it && it.payment === '관리급여'; }

    function syncItemUi(resetAmount) {
      var it = currentItem();
      if (it && it.payment === '관리급여') {
        roundsRow.style.display = '';
        roundsInput.value = state.rounds;
        state.amount = MedCalc.managedTotal(state.rounds);
        amountInput.value = state.amount;
        chip.textContent = '관리급여 수가';
        chip.style.display = '';
        managedBox.classList.add('show');
        managedBox.innerHTML = '<b>도수치료는 2026.7.1부터 관리급여(선별급여)</b>입니다. ' +
          '1회 ' + fmt(MedCalc.MANAGED_UNIT_PRICE) + ' (종별 동일·종별가산 없음), 건강보험 본인부담률 95% — ' +
          '1회 건강보험 본인부담 <b>' + fmt(Math.floor((MedCalc.MANAGED_UNIT_PRICE * 95 + 50) / 100)) + '</b>. ' +
          '실손은 그 본인부담금의 80~90%를 보장합니다(세대·유형별 상이 — 아래 표 참조). ' +
          '비급여 특약이 아니라 <b>급여</b>로 계산합니다.';
      } else {
        roundsRow.style.display = 'none';
        if (PREVIEW) {
          chip.textContent = '예시 금액';
          chip.style.display = '';
        } else if (it && it.has_data) {
          chip.textContent = '심평원 병원급 중간값';
          chip.style.display = '';
        } else {
          chip.textContent = '';
          chip.style.display = 'none';
        }
        managedBox.classList.remove('show');
        if (it && resetAmount) { state.amount = defAmount(it); }
        else if (!it && resetAmount) { state.amount = 300000; }
        amountInput.value = isFinite(state.amount) ? state.amount : '';
      }
      if (hint) {
        if (it) {
          hint.innerHTML = '<b>' + it.name + '</b> · ' + it.summary + '<br><span class="hint">' +
            (it.watch || '') + '</span>';
        } else {
          hint.innerHTML = '<b>직접 입력</b> · 병원에서 받은 비급여 금액을 직접 넣어 1~5세대 보장액을 비교합니다.';
        }
      }
      severeCumRow.style.display = state.severe ? '' : 'none';
    }

    function syncSegButtons() {
      $all(root, '#visit-group button').forEach(function (b) {
        b.setAttribute('aria-pressed', b.dataset.visit === state.visit ? 'true' : 'false');
      });
      $all(root, '#inst-group button').forEach(function (b) {
        b.setAttribute('aria-pressed', b.dataset.inst === state.inst ? 'true' : 'false');
      });
      $all(root, '#severe-group button').forEach(function (b) {
        b.setAttribute('aria-pressed', String(state.severe) === b.dataset.severe ? 'true' : 'false');
      });
      var g2 = $(root, '#gen2-select');
      if (g2) { g2.value = state.gen2; }
    }

    function render() {
      var it = currentItem();
      var problem = amountProblem();
      if (problem) {
        setAmountError(problem);
        tbody.innerHTML = '';
        var badRow = el('tr');
        var badCell = el('td', null, problem);
        badCell.colSpan = 5;
        badCell.style.color = '#6e7462';
        badRow.appendChild(badCell);
        tbody.appendChild(badRow);
        summary.innerHTML = '';
        warnBox.innerHTML = '';
        warnBox.style.display = 'none';
        if (metaBox) { metaBox.textContent = '금액을 입력하면 세대별 보장액을 계산합니다'; }
        return;
      }
      setAmountError('');
      var req = {
        item_code: state.item,
        amount: state.amount,
        visit: state.visit,
        institution: state.inst,
        severe: !!state.severe,
        gen2_type: state.gen2,
        severe_cum: state.severeCum,
        rounds: state.rounds
      };
      var res;
      try { res = MedCalc.compute(req, CAT); } catch (e) { console.error(e); return; }

      tbody.innerHTML = '';
      res.generations.forEach(function (r) {
        var tr = el('tr');
        tr.setAttribute('data-gen', String(r.gen));
        if (r.sub) { tr.setAttribute('data-sub', r.sub); }
        if (r.status === 'excluded') { tr.classList.add('is-excluded'); }
        if (res.summary.best_key === r.key) { tr.classList.add('is-best'); }

        var tdGen = el('td', 'gen-cell');
        tdGen.setAttribute('data-label', '세대');
        tdGen.appendChild(el('span', 'g', r.name));
        tdGen.appendChild(el('span', 'p', r.period));
        tr.appendChild(tdGen);

        var tdRate = el('td', 'rate-cell');
        tdRate.setAttribute('data-label', '자기부담 기준');
        tdRate.textContent = r.rate_label;
        tr.appendChild(tdRate);

        var tdCov = el('td', 'num covered-cell');
        tdCov.setAttribute('data-label', '예상 보장액');
        tdCov.classList.add('covered');
        // '모르겠어요' 후기 행은 보장액도 범위로 표시한다(부이 #1245 ①).
        tdCov.textContent = (r.covered_lo !== null && r.covered_lo !== undefined)
          ? fmt(r.covered_lo) + ' ~ ' + fmt(r.covered) : fmt(r.covered);
        if (r.status === 'excluded') {
          tr.appendChild(tdCov);
          tdCov.textContent = '0원';
        } else {
          tr.appendChild(tdCov);
        }

        var tdCop = el('td', 'num copay-cell');
        tdCop.setAttribute('data-label', '환자 최종 부담');
        tdCop.classList.add('copay');
        tdCop.textContent = (r.copay_hi !== null && r.copay_hi !== undefined)
          ? fmt(r.copay) + ' ~ ' + fmt(r.copay_hi) : fmt(r.copay);
        tr.appendChild(tdCop);

        var tdNote = el('td');
        tdNote.setAttribute('data-label', '적용 규칙 · 한도');
        var bd = el('div', 'badges');
        if (r.badges.length === 0) {
          bd.appendChild(el('span', 'badge', '기본'));
        } else {
          r.badges.forEach(function (b) {
            var cls = 'badge';
            if (b.indexOf('제외') >= 0) { cls += ' exclude'; }
            else if (b.indexOf('관리급여') >= 0) { cls += ' managed'; }
            else if (b.indexOf('특약') >= 0) { cls += ' special'; }
            bd.appendChild(el('span', cls, b));
          });
        }
        if (r.cap_applied) { bd.appendChild(el('span', 'badge cap', '회당 한도 적용')); }
        // 부이 #1245 ⑤ — 고른 2세대 유형 행을 강조한다.
        if (r.gen === 2 && r.sub) {
          var isSel = (state.gen2 === 'early' && r.sub === 'early') ||
            (state.gen2 !== 'early' && state.gen2 !== 'unknown' && r.sub === 'late');
          if (isSel) {
            tr.classList.add('is-selected');
            bd.appendChild(el('span', 'badge selected', '선택한 유형'));
          }
          if (r.sub === 'late' && r.same_amount &&
              (state.gen2 === 'late10' || state.gen2 === 'unknown')) {
            bd.appendChild(el('span', 'badge same', '전기·후기 10%형과 같은 금액'));
          }
        }
        tdNote.appendChild(bd);
        if (r.status === 'excluded') {
          tdNote.appendChild(el('div', 'zero-note', '보장 제외 → 전액 본인부담'));
        }
        if (r.limits && r.limits.length) {
          var ul = el('ul', 'limits');
          r.limits.forEach(function (t) { ul.appendChild(el('li', null, t)); });
          tdNote.appendChild(ul);
        }
        tr.appendChild(tdNote);
        tbody.appendChild(tr);
      });

      // 요약 — 보장액과 환자 최종 부담을 나란히 큰 숫자로 (밀크·부이 검수 2026-11-25)
      summary.innerHTML = '';
      var best = res.generations.filter(function (r) { return r.key === res.summary.best_key; })[0];
      if (best) {
        var box = el('div', 'best');
        var left = el('div');
        left.appendChild(el('div', 'lbl', '가장 많이 돌려받는 세대'));
        left.appendChild(el('div', 'big', (best.covered_lo !== null && best.covered_lo !== undefined)
          ? fmt(best.covered_lo) + ' ~ ' + fmt(best.covered) : fmt(best.covered)));
        var who = el('div', 'who');
        who.innerHTML = '<b>' + best.name + '</b> 기준';
        left.appendChild(who);
        box.appendChild(left);
        var right = el('div', 'copay-box');
        right.appendChild(el('div', 'lbl', '환자 최종 부담'));
        right.appendChild(el('div', 'big', (best.copay_hi !== null && best.copay_hi !== undefined)
          ? fmt(best.copay) + ' ~ ' + fmt(best.copay_hi) : fmt(best.copay)));
        box.appendChild(right);
        summary.appendChild(box);
      }

      // 경고/안내
      warnBox.innerHTML = '';
      var extraWarn = [];
      if (res.input.amount > AMOUNT_MAX_WARN) {
        extraWarn.push('입력한 금액이 5억 원을 넘습니다. 액수를 다시 한 번 확인해 주세요(자릿수 오타 가능성).');
      }
      extraWarn.concat(res.warnings).forEach(function (w) { warnBox.appendChild(el('li', null, w)); });
      if (extraWarn.length + res.warnings.length) { warnBox.style.display = ''; } else { warnBox.style.display = 'none'; }

      // 기준 정보
      if (metaBox) {
        var it2 = currentItem();
        var parts = [
          res.input.visit_label + ' · ' + res.input.institution_label,
          '비급여 금액 ' + fmt(res.input.amount),
          it2 ? it2.code : '직접 입력'
        ];
        if (it2 && it2.payment === '관리급여') {
          parts.push('관리급여 본인부담 기준 ' + fmt(best ? best.base : 0));
        }
        metaBox.textContent = parts.join('  ·  ');
      }

      // 주소에 조건 반영(공유·뒤로가기용)
      try {
        var q = new URLSearchParams();
        if (state.item !== 'direct') { q.set('item', state.item); }
        else { q.set('item', 'direct'); }
        q.set('amount', String(state.amount));
        if (state.visit !== 'out') { q.set('visit', state.visit); }
        if (state.inst !== 'tertiary') { q.set('inst', state.inst); }
        if (state.severe) { q.set('severe', '1'); }
        if (state.gen2 !== 'unknown') { q.set('gen2', state.gen2); }
        if (state.rounds > 1) { q.set('rounds', String(state.rounds)); }
        history.replaceState(null, '', location.pathname + '?' + q.toString() + location.hash);
      } catch (e) { /* 무시 */ }
    }

    var calcTracked = false;
    function trackCalc() {
      if (calcTracked) { return; }
      calcTracked = true;
      track('calc_use', {
        item_code: state.item,
        visit: state.visit,
        institution: state.inst,
        payment: (currentItem() || {}).payment || 'direct'
      });
    }

    // ---------------------------------------------------- 이벤트
    sel.addEventListener('change', function () {
      state.item = sel.value;
      state.rounds = 1;
      if (state.item !== 'direct') { state.amount = defAmount(itemByCode(state.item)); }
      syncItemUi(true); syncSegButtons(); render();
      trackCalc();
    });
    amountInput.addEventListener('input', function () {
      // M-03: 숫자만 뽑아내면 -1000 이 1000 이 된다. 입력값을 그대로 해석해 검증에 맡긴다.
      var raw = String(amountInput.value == null ? '' : amountInput.value).trim();
      var n = raw === '' ? NaN : Number(raw);
      state.amount = isFinite(n) ? n : NaN;
      render();
      trackCalc();
    });
    if (roundsInput) {
      roundsInput.addEventListener('input', function () {
        state.rounds = Math.max(1, parseInt(roundsInput.value, 10) || 1);
        state.amount = MedCalc.managedTotal(state.rounds);
        amountInput.value = state.amount;
        render();
        trackCalc();
      });
    }
    if (cumInput) {
      cumInput.addEventListener('input', function () {
        var v = parseInt(String(cumInput.value).replace(/[^0-9]/g, ''), 10);
        state.severeCum = isNaN(v) ? 0 : Math.max(0, v);
        render();
      });
    }
    $all(root, '#visit-group button').forEach(function (b) {
      b.addEventListener('click', function () { state.visit = b.dataset.visit; syncSegButtons(); render(); trackCalc(); });
    });
    $all(root, '#inst-group button').forEach(function (b) {
      b.addEventListener('click', function () { state.inst = b.dataset.inst; syncSegButtons(); render(); trackCalc(); });
    });
    $all(root, '#severe-group button').forEach(function (b) {
      b.addEventListener('click', function () {
        state.severe = Number(b.dataset.severe);
        syncItemUi(false); syncSegButtons(); render(); trackCalc();
      });
    });
    var g2 = $(root, '#gen2-select');
    if (g2) { g2.addEventListener('change', function () { state.gen2 = g2.value; render(); }); }

    // 초기 상태
    if (typeof state.amount !== 'number' || !isFinite(state.amount)) {
      state.amount = state.item === 'direct' ? 300000 : defAmount(itemByCode(state.item));
    }
    syncItemUi(true);
    syncSegButtons();
    if (cumInput) { cumInput.value = state.severeCum || ''; }
    render();
    root.setAttribute('data-ready', '1');
  }

  // ---------------------------------------------------- 항목 상세 조회(GA4)
  function initItemViewTracking() {
    var m = /\/items\/([^/]+)\/?$/.exec(location.pathname || '');
    if (!m) { return; }
    track('item_view', { item_slug: m[1], location: 'item_detail' });
  }

  function boot() {
    initNavOverflow();
    Array.prototype.slice.call(document.querySelectorAll('[data-calc]')).forEach(init);
    initItemViewTracking();
    initHospTables();
  }

  // ---------------------------------------------------- 헤더 메뉴 넘김 단서 (밀크 검수 2026-11-24)
  // 좁은 화면에서 메뉴가 넘치면 .is-scrollable 클래스를 달아 CSS 페이드로 알린다.
  function initNavOverflow() {
    var nav = document.querySelector('.nav');
    if (!nav) { return; }
    function update() {
      var over = nav.scrollWidth > nav.clientWidth + 1;
      nav.classList.toggle('is-scrollable', over);
      nav.classList.toggle('is-scrolled', over && nav.scrollLeft > 4);
    }
    nav.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(update);
    }
    update();
  }

  // ---------------------------------------------------- 병원급 기관 목록 필터
  // 두 가지 카드 모드를 지원한다.
  //  ① 항목 페이지: data-hosp data-code=항목코드 + 시도/종별/검색 필터
  //  ② 지역 페이지: data-hosp data-region=시도 + 항목/시군구/검색 필터
  var HOSP_CACHE = null;
  // 병원명 표시용 2자 마스킹: 앞 2자만 보이고 나머지는 ** (가드레일: 병원 실명 금지).
  // 빌드 시 /assets/hospitals.json의 이름도 같은 규칙으로 마스킹돼 배포되므로
  // 검색은 마스킹된 이름(r[0]) 기준으로 동작한다(앞부분 입력으로 찾는다).
  function maskHospName(n) {
    var s = String(n || '').replace(/^\([^)]*\)\s*/, '');
    return s.length > 2 ? s.slice(0, 2) + '**' : s;
  }
  function initHospTables() {
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-hosp]'));
    if (!cards.length || !window.fetch) { return; }
    function load() {
      if (HOSP_CACHE) { return HOSP_CACHE; }
      HOSP_CACHE = fetch('/assets/hospitals.json', { cache: 'force-cache' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { return d && d.items ? d.items : {}; })
        .catch(function () { return {}; });
      return HOSP_CACHE;
    }
    load().then(function (all) {
      cards.forEach(function (card) { initCard(card, all); });
    });

    function initCard(card, all) {
      var body = card.querySelector('[data-hosp-body]');
      if (!body) { return; }
      var fixedCode = card.getAttribute('data-code') || '';
      var itemSel = card.querySelector('[data-hosp-item]');
      var sidoSel = card.querySelector('[data-hosp-sido]');
      var sgguSel = card.querySelector('[data-hosp-sggu]');
      var clSel = card.querySelector('[data-hosp-cl]');
      var qInput = card.querySelector('[data-hosp-q]');
      var countEl = card.querySelector('[data-hosp-count]');
      var moreBtn = card.querySelector('[data-hosp-more]');
      var region = card.getAttribute('data-region') || '';
      var sgguPrefix = card.getAttribute('data-region-sggu-prefix') || '';
      var sgguNotPrefix = card.getAttribute('data-region-sggu-not-prefix') || '';
      var shown = 50;

      function currentCode() {
        return itemSel ? itemSel.value : fixedCode;
      }
      function regionOk(r) {
        if (!region) { return true; }
        if (r[2] !== region) { return false; }
        var sg = String(r[3] || '');
        if (sgguPrefix && sg.indexOf(sgguPrefix) !== 0) { return false; }
        if (sgguNotPrefix && sg.indexOf(sgguNotPrefix) === 0) { return false; }
        return true;
      }
      function rowsOf(code) {
        var rows = all[code] || [];
        return region ? rows.filter(regionOk) : rows;
      }
      function fillSggu() {
        if (!sgguSel) { return; }
        var keep = sgguSel.value;
        var seen = {};
        var names = [];
        rowsOf(currentCode()).forEach(function (r) {
          var s = String(r[3] || '');
          if (!s || seen[s]) { return; }
          seen[s] = 1; names.push(s);
        });
        names.sort(function (a, b) { return a.localeCompare(b, 'ko'); });
        sgguSel.innerHTML = '';
        var allOpt = document.createElement('option');
        allOpt.value = ''; allOpt.textContent = '전체 시·군·구';
        sgguSel.appendChild(allOpt);
        names.forEach(function (s) {
          var o = document.createElement('option');
          o.value = s; o.textContent = s;
          sgguSel.appendChild(o);
        });
        sgguSel.value = seen[keep] ? keep : '';
      }

      function render() {
        var rows = rowsOf(currentCode());
        var sd = sidoSel ? sidoSel.value : '';
        var sg = sgguSel ? sgguSel.value : '';
        var cl = clSel ? clSel.value : '';
        var q = qInput ? qInput.value.trim().toLowerCase() : '';
        var list = rows.filter(function (r) {
          if (sd && r[2] !== sd) { return false; }
          if (sg && String(r[3] || '') !== sg) { return false; }
          if (cl && r[1] !== cl) { return false; }
          if (q && String(r[0]).toLowerCase().indexOf(q) < 0) { return false; }
          return true;
        });
        var slice = list.slice(0, shown);
        body.innerHTML = '';
        if (!slice.length) {
          var empty = document.createElement('tr');
          var td0 = document.createElement('td');
          td0.colSpan = 5;
          td0.textContent = region
            ? '이 항목은 이 지역에 공개된 병원급 기관이 없습니다. 다른 항목이나 필터를 선택하세요.'
            : '조건에 맞는 기관이 없습니다.';
          empty.appendChild(td0);
          body.appendChild(empty);
        }
        slice.forEach(function (r) {
          var tr = document.createElement('tr');
          var loc = region ? String(r[3] || '') : (r[2] || '') + ' ' + (r[3] || '');
          var hospLabels = ['기관', '종별', '지역', '최저', '최고'];
          [maskHospName(r[0]), r[1], loc, fmt(r[4]), fmt(r[5])]
            .forEach(function (v, i) {
              var td = document.createElement('td');
              td.textContent = v === null || v === undefined || v === '' ? '—' : v;
              td.setAttribute('data-label', hospLabels[i]);
              if (i >= 3) { td.className = 'num'; }
              tr.appendChild(td);
            });
          body.appendChild(tr);
        });
        if (countEl) {
          if (region) {
            countEl.textContent = '이 지역 전체 ' + rows.length.toLocaleString('ko-KR') + '곳 중 조건에 맞는 ' +
              list.length.toLocaleString('ko-KR') + '곳 · ' + slice.length.toLocaleString('ko-KR') +
              '곳 표시(낮은 금액 순)';
          } else {
            countEl.textContent = '전체 ' + rows.length.toLocaleString('ko-KR') + '곳 중 조건에 맞는 ' +
              list.length.toLocaleString('ko-KR') + '곳 · ' + slice.length.toLocaleString('ko-KR') +
              '곳 표시(낮은 금액 순)';
          }
        }
        if (moreBtn) { moreBtn.style.display = list.length > shown ? '' : 'none'; }
      }
      [sidoSel, clSel, sgguSel].forEach(function (elm) {
        if (elm) {
          elm.addEventListener('change', function () {
            shown = 50; render();
            track('hospital_filter', {
              item_code: currentCode(),
              sido: region || (sidoSel ? sidoSel.value : ''),
              sggu: sgguSel ? sgguSel.value : '',
              clinic_type: clSel ? clSel.value : ''
            });
          });
        }
      });
      if (itemSel) {
        itemSel.addEventListener('change', function () {
          shown = 50; fillSggu(); render();
          track('hospital_filter', { item_code: currentCode(), sido: region, change: 'item' });
        });
      }
      if (qInput) {
        qInput.addEventListener('input', function () { shown = 50; render(); });
      }
      if (moreBtn) {
        moreBtn.addEventListener('click', function () { shown += 50; render(); });
      }
      fillSggu();
      render();
    }
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', boot); }
  else { boot(); }
})();
