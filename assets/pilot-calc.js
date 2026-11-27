/*!
 * pilot-calc.js — P0 파일럿(도수치료 상세 내장 계산) 결과 재구성 레이어
 *
 * 계산은 기존 calc.js(MedCalc.compute)를 그대로 호출한다 — 계산 규칙은 건드리지 않는다.
 * 이 파일은 표시만 담당한다:
 *   1) '내 세대' 선택(1~5세대·모름)을 받아 결과 맨 위 히어로에 그 세대의
 *      환자 최종 부담을 큰 숫자로 표시한다.
 *   2) 입력 금액이 항목 시세(중간값·최저~최고) 어디인지 1줄로 붙인다.
 *   3) 비교표에서 내 세대 행을 강조한다.
 * app.js 가 표를 다시 그릴 때마다 MutationObserver 로 히어로를 동기화한다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-pilot-calc]');
  if (!root || !window.MedCalc) { return; }

  var STATS = window.PILOT_STATS || null;   // {code, n, avg, median, min, max, mode}
  var myGen = 0;                            // 0 = 모름

  function $(sel) { return root.querySelector(sel); }
  function won(n) { return window.MedCalc.won(n); }

  /* app.js 와 같은 입력 규칙으로 현재 폼 상태를 읽는다(표시용 재계산에만 쓴다). */
  function readState() {
    var sel = $('#item-select');
    var amountInput = $('#amount-input');
    var visitBtn = root.querySelector('#visit-group button[aria-pressed="true"]');
    var instBtn = root.querySelector('#inst-group button[aria-pressed="true"]');
    var sevBtn = root.querySelector('#severe-group button[aria-pressed="true"]');
    var g2 = $('#gen2-select');
    var roundsInput = $('#rounds-input');
    var cumInput = $('#severe-cum-input');
    var amt = amountInput ? Number(String(amountInput.value).trim()) : NaN;
    var cum = cumInput ? parseInt(String(cumInput.value).replace(/[^0-9]/g, ''), 10) : NaN;
    return {
      item_code: sel ? sel.value : 'direct',
      amount: isFinite(amt) ? amt : NaN,
      visit: visitBtn ? visitBtn.getAttribute('data-visit') : 'out',
      institution: instBtn ? instBtn.getAttribute('data-inst') : 'tertiary',
      severe: sevBtn ? sevBtn.getAttribute('data-severe') === '1' : false,
      gen2_type: g2 ? g2.value : 'standard',
      severe_cum: isNaN(cum) ? 0 : cum,
      rounds: roundsInput ? Math.max(1, parseInt(roundsInput.value, 10) || 1) : 1
    };
  }

  function marketLine(amount, itemCode) {
    // 관리급여 항목은 시세 위치 줄을 끈다 (밀크 #1164 ④).
    // 입력 금액이 관리급여 수가(43,850원×횟수)인데 병원급 비급여 공개가 중간값과
    // 비교하면 '중간값보다 50% 낮음' 같은 오해를 만든다. 시세 기준도 전환 전
    // 비급여 공개자료라 같은 페이지의 전환 안내와 모순된다.
    if (STATS && STATS.managed) { return ''; }
    if (!STATS || itemCode !== STATS.code || !(amount > 0)) { return ''; }
    var med = STATS.median, lo = STATS.min, hi = STATS.max;
    var diff = Math.round((amount - med) / med * 100);
    var rel = diff === 0 ? '중간값 ' + won(med) + '와 같은 수준입니다'
      : diff > 0 ? '중간값 ' + won(med) + '보다 ' + diff + '% 높습니다'
        : '중간값 ' + won(med) + '보다 ' + Math.abs(diff) + '% 낮습니다';
    var range = (amount >= lo && amount <= hi)
      ? '공개 구간(' + won(lo) + '~' + won(hi) + ') 안에 있습니다'
      : '공개 구간(' + won(lo) + '~' + won(hi) + ') 밖에 있습니다';
    return '시세 위치: 입력 금액 ' + won(amount) + ' — 전국 병원급 공개가 ' + rel + ', ' + range + '. ' +
      '시세는 관리급여 전환 전 2026년 비급여 공개자료 기준입니다.';
  }

  function renderCompare(res) {
    // '다른 세대와 비교' 접기 표 (밀크 #1164 ⑤): 세대·보장액·최종부담 3열 5줄.
    var body = $('#pilot-compare-body');
    if (!body || !res) { return; }
    body.innerHTML = '';
    res.generations.forEach(function (r) {
      var tr = document.createElement('tr');
      if (r.gen === myGen) { tr.className = 'pilot-selected'; }
      [[r.name, ''], [won(r.covered), 'num'], [won(r.copay), 'num']].forEach(function (cell) {
        var td = document.createElement('td');
        td.textContent = cell[0];
        if (cell[1]) { td.className = cell[1]; }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function render() {
    var lbl = $('#pilot-hero-lbl');
    var num = $('#pilot-hero-num');
    var sub = $('#pilot-hero-sub');
    var mkt = $('#pilot-hero-market');
    if (!num || !sub || !mkt) { return; }

    root.querySelectorAll('#result-table tbody tr').forEach(function (tr) {
      tr.classList.toggle('pilot-selected',
        !!myGen && tr.getAttribute('data-gen') === String(myGen));
    });
    root.classList.toggle('pilot-has-gen', !!myGen);

    var st = readState();
    mkt.textContent = marketLine(st.amount, st.item_code);
    // 관리급여 항목은 시세 위치 줄이 꺼지므로 빈 <p>의 구분선도 함께 숨긴다.
    mkt.style.display = mkt.textContent ? '' : 'none';

    if (!myGen) {
      lbl.textContent = '내 최종 부담';
      num.textContent = '세대를 고르면 크게 표시됩니다';
      num.classList.add('pilot-hero-num--guide');
      sub.textContent = '내 실손 세대를 모르면 아래 비교표에서 세대별로 확인하세요.';
      // 모름 상태에서는 전체 비교표가 보이고 '다른 세대와 비교' 접기는 숨긴다.
      if (st.amount > 0) {
        try {
          renderCompare(window.MedCalc.compute(st, (window.MED_CATALOG && window.MED_CATALOG.items) || []));
        } catch (e) { /* 무시 */ }
      }
      return;
    }
    if (!(st.amount > 0)) {
      lbl.textContent = '내 최종 부담';
      num.textContent = '금액을 입력해 주세요';
      num.classList.add('pilot-hero-num--guide');
      sub.textContent = '';
      return;
    }
    var res;
    try {
      res = window.MedCalc.compute(st, (window.MED_CATALOG && window.MED_CATALOG.items) || []);
    } catch (e) { return; }
    renderCompare(res);
    var row = null;
    res.generations.forEach(function (r) { if (r.gen === myGen) { row = r; } });
    if (!row) { return; }

    lbl.textContent = '내 최종 부담 · ' + row.name + ' 기준';
    num.classList.remove('pilot-hero-num--guide');
    num.textContent = won(row.copay);
    if (row.status === 'excluded') {
      sub.textContent = '이 항목은 ' + row.name + '에서 보장 제외라 전액 본인부담입니다(예상 보장액 0원).';
    } else {
      sub.textContent = '예상 보장액 ' + won(row.covered) + ' · 자기부담 기준 ' + row.rate_label +
        ' · 진료비 ' + won(res.input.amount) + ' 중 내가 내는 금액입니다.';
    }
  }

  /* 내 세대 선택 */
  var genGroup = $('#pilot-gen-group');
  if (genGroup) {
    genGroup.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        myGen = Number(b.getAttribute('data-mygen')) || 0;
        genGroup.querySelectorAll('button').forEach(function (x) {
          x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
        });
        render();
      });
    });
  }

  /* app.js 가 결과 표를 다시 그리면 히어로도 따라간다 */
  var tbody = $('#result-table tbody');
  if (tbody && window.MutationObserver) {
    new MutationObserver(function () { render(); }).observe(tbody, { childList: true });
  }
  /* 세대 선택 전에도 시세 위치 줄은 금액 입력에 반응한다 */
  root.addEventListener('input', function () { render(); });
  root.addEventListener('change', function () { render(); });

  render();
})();
