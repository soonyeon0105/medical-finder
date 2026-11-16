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
      gen2: 'standard',
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
      if (qs.get('gen2') === 'select2') { state.gen2 = 'select2'; }
      if (qs.get('rounds')) { state.rounds = Math.max(1, parseInt(qs.get('rounds'), 10) || 1); }
      if (qs.get('amount') !== null && qs.get('amount') !== '') {
        state.amount = Math.max(0, parseInt(qs.get('amount'), 10) || 0);
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

    // ---------------------------------------------------- 항목 목록
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
          '1회 ' + fmt(MedCalc.MANAGED_UNIT_PRICE) + ' (종별 동일·종별가산 없음), 본인부담률 95% — ' +
          '1회 환자 부담 <b>' + fmt(Math.floor((MedCalc.MANAGED_UNIT_PRICE * 95 + 50) / 100)) + '</b>. ' +
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
        amountInput.value = state.amount;
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
        if (r.status === 'excluded') { tr.classList.add('is-excluded'); }
        if (res.summary.best_gen === r.gen) { tr.classList.add('is-best'); }

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
        tdCov.textContent = fmt(r.covered);
        if (r.status === 'excluded') {
          tr.appendChild(tdCov);
          tdCov.textContent = '0원';
        } else {
          tr.appendChild(tdCov);
        }

        var tdCop = el('td', 'num copay-cell');
        tdCop.setAttribute('data-label', '환자 최종 부담');
        tdCop.classList.add('copay');
        tdCop.textContent = fmt(r.copay);
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

      // 요약
      summary.innerHTML = '';
      var best = res.generations.filter(function (r) { return r.gen === res.summary.best_gen; })[0];
      if (best) {
        var box = el('div', 'best');
        var left = el('div', 'big', fmt(best.covered));
        var right = el('div');
        right.appendChild(el('div', 'lbl', '가장 많이 돌려받는 세대'));
        var who = el('div', 'who');
        who.innerHTML = '<b>' + best.name + '</b> 기준 · 환자 최종 부담 ' + fmt(best.copay);
        right.appendChild(who);
        box.appendChild(left);
        box.appendChild(right);
        summary.appendChild(box);
      }

      // 경고/안내
      warnBox.innerHTML = '';
      res.warnings.forEach(function (w) { warnBox.appendChild(el('li', null, w)); });
      if (res.warnings.length) { warnBox.style.display = ''; } else { warnBox.style.display = 'none'; }

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
        if (state.gen2 !== 'standard') { q.set('gen2', 'select2'); }
        if (state.rounds > 1) { q.set('rounds', String(state.rounds)); }
        history.replaceState(null, '', location.pathname + '?' + q.toString() + location.hash);
      } catch (e) { /* 무시 */ }
    }

    // ---------------------------------------------------- 이벤트
    sel.addEventListener('change', function () {
      state.item = sel.value;
      state.rounds = 1;
      if (state.item !== 'direct') { state.amount = defAmount(itemByCode(state.item)); }
      syncItemUi(true); syncSegButtons(); render();
    });
    amountInput.addEventListener('input', function () {
      var v = parseInt(String(amountInput.value).replace(/[^0-9]/g, ''), 10);
      state.amount = isNaN(v) ? 0 : v;
      render();
    });
    if (roundsInput) {
      roundsInput.addEventListener('input', function () {
        state.rounds = Math.max(1, parseInt(roundsInput.value, 10) || 1);
        state.amount = MedCalc.managedTotal(state.rounds);
        amountInput.value = state.amount;
        render();
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
      b.addEventListener('click', function () { state.visit = b.dataset.visit; syncSegButtons(); render(); });
    });
    $all(root, '#inst-group button').forEach(function (b) {
      b.addEventListener('click', function () { state.inst = b.dataset.inst; syncSegButtons(); render(); });
    });
    $all(root, '#severe-group button').forEach(function (b) {
      b.addEventListener('click', function () {
        state.severe = Number(b.dataset.severe);
        syncItemUi(false); syncSegButtons(); render();
      });
    });
    var g2 = $(root, '#gen2-select');
    if (g2) { g2.addEventListener('change', function () { state.gen2 = g2.value; render(); }); }

    // 초기 상태
    if (state.item === 'direct') { state.amount = state.amount || 300000; }
    else if (!parseInt(state.amount, 10) && state.item !== 'direct') { state.amount = defAmount(itemByCode(state.item)); }
    syncItemUi(true);
    syncSegButtons();
    if (cumInput) { cumInput.value = state.severeCum || ''; }
    render();
    root.setAttribute('data-ready', '1');
  }

  function boot() {
    Array.prototype.slice.call(document.querySelectorAll('[data-calc]')).forEach(init);
    initHospTables();
  }

  // ---------------------------------------------------- 병원급 기관 목록 필터
  var HOSP_CACHE = null;
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
      cards.forEach(function (card) {
        var code = card.getAttribute('data-code');
        var rows = all[code] || [];
        if (!rows.length) { return; }
        var body = card.querySelector('[data-hosp-body]');
        var sidoSel = card.querySelector('[data-hosp-sido]');
        var clSel = card.querySelector('[data-hosp-cl]');
        var qInput = card.querySelector('[data-hosp-q]');
        var countEl = card.querySelector('[data-hosp-count]');
        var moreBtn = card.querySelector('[data-hosp-more]');
        var shown = 50;

        function render() {
          var sd = sidoSel ? sidoSel.value : '';
          var cl = clSel ? clSel.value : '';
          var q = qInput ? qInput.value.trim().toLowerCase() : '';
          var list = rows.filter(function (r) {
            if (sd && r[2] !== sd) { return false; }
            if (cl && r[1] !== cl) { return false; }
            if (q && String(r[0]).toLowerCase().indexOf(q) < 0) { return false; }
            return true;
          });
          var slice = list.slice(0, shown);
          body.innerHTML = '';
          slice.forEach(function (r) {
            var tr = document.createElement('tr');
            [r[0], r[1], (r[2] || '') + ' ' + (r[3] || ''), fmt(r[4]), fmt(r[5])]
              .forEach(function (v, i) {
                var td = document.createElement('td');
                td.textContent = v === null || v === undefined ? '—' : v;
                if (i >= 3) { td.className = 'num'; }
                tr.appendChild(td);
              });
            body.appendChild(tr);
          });
          if (countEl) {
            countEl.textContent = '전체 ' + rows.length.toLocaleString('ko-KR') + '곳 중 조건에 맞는 ' +
              list.length.toLocaleString('ko-KR') + '곳 · ' + slice.length.toLocaleString('ko-KR') +
              '곳 표시(낮은 금액 순)';
          }
          if (moreBtn) { moreBtn.style.display = list.length > shown ? '' : 'none'; }
        }
        [sidoSel, clSel].forEach(function (elm) {
          if (elm) { elm.addEventListener('change', function () { shown = 50; render(); }); }
        });
        if (qInput) {
          qInput.addEventListener('input', function () { shown = 50; render(); });
        }
        if (moreBtn) {
          moreBtn.addEventListener('click', function () { shown += 50; render(); });
        }
        render();
      });
    });
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', boot); }
  else { boot(); }
})();
