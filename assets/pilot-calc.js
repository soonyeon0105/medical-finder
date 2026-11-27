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
  var myGen2 = 'unknown';                   // 2세대 세부: 'unknown'(모름) | 'early' | 'late10' | 'late20' | 'sel2'

  function mySub() { return myGen2 === 'early' ? 'early' : 'late'; }

  // '모르겠어요' 후기 행은 보장액도 범위로 표시한다.
  function rangeNote(row) {
    if (row.copay_hi === null || row.copay_hi === undefined) { return ''; }
    return ' 유형에 따라 보장액 ' + won(row.covered_lo) + '~' + won(row.covered) +
      ' · 최종 부담 ' + won(row.copay) + '~' + won(row.copay_hi) + ' 범위입니다.';
  }

  // 부이 #1278 ② — 히어로 범위 안내(배수 + 증권 확인 + 선택하기 링크). #pilot-hero-range에 둔다.
  function setHeroRange(row) {
    var rangeEl = document.querySelector('#pilot-hero-range');
    if (!rangeEl) { return; }
    rangeEl.innerHTML = '';
    if (!row || row.copay_hi === null || row.copay_hi === undefined || !row.copay) { return; }
    var ratio = Math.round(row.copay_hi / row.copay);
    rangeEl.appendChild(document.createTextNode(
      ratio >= 2
        ? '가입 상품에 따라 최대 ' + ratio + '배 차이 — 증권에서 상품명을 확인하면 정확히 나와요 '
        : '가입 상품에 따라 달라요 — 증권에서 상품명을 확인하면 정확히 나와요 '));
    var a = document.createElement('a');
    a.href = '#pilot-gen2-group';
    a.textContent = '선택하기';
    a.addEventListener('click', function (e) {
      e.preventDefault();
      var g = document.querySelector('#pilot-gen2-group');
      if (g) { g.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    });
    rangeEl.appendChild(a);
  }
  function isMine(r) {
    if (r.gen !== myGen) { return false; }
    if (myGen !== 2) { return true; }
    return !myGen2 || r.sub === mySub();
  }

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
      gen2_type: g2 ? g2.value : 'unknown',
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
    // '다른 세대와 비교' 접기 표 (밀크 #1164 ⑤): 세대·보장액·최종부담 3열.
    // 2세대는 전기·후기 두 행으로 나뉘어 총 6줄이 된다 (2026-11-28 분리).
    var body = $('#pilot-compare-body');
    if (!body || !res) { return; }
    body.innerHTML = '';
    res.generations.forEach(function (r) {
      var tr = document.createElement('tr');
      if (isMine(r)) { tr.className = 'pilot-selected'; }
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

    // 메인 계산기의 #gen2-select 가 바뀌면 2세대 세부 선택도 따라간다.
    if (myGen === 2) {
      var g2selNow = $('#gen2-select');
      if (g2selNow && ['early', 'late10', 'late20', 'sel2', 'unknown'].indexOf(g2selNow.value) >= 0) {
        myGen2 = g2selNow.value;
        var g2grp = $('#pilot-gen2-group');
        if (g2grp) {
          g2grp.querySelectorAll('button').forEach(function (x) {
            x.setAttribute('aria-pressed', x.getAttribute('data-mygen2') === myGen2 ? 'true' : 'false');
          });
        }
      }
    }

    root.querySelectorAll('#result-table tbody tr').forEach(function (tr) {
      var mine = false;
      if (myGen) {
        if (Number(tr.getAttribute('data-gen')) === myGen) {
          mine = myGen !== 2 || !myGen2 || tr.getAttribute('data-sub') === mySub();
        }
      }
      tr.classList.toggle('pilot-selected', mine);
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
      setHeroRange(null);
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
      setHeroRange(null);
      sub.textContent = '';
      return;
    }
    var res;
    try {
      res = window.MedCalc.compute(st, (window.MED_CATALOG && window.MED_CATALOG.items) || []);
    } catch (e) { return; }
    renderCompare(res);
    var row = null;
    res.generations.forEach(function (r) { if (isMine(r)) { row = r; } });
    if (!row) { return; }

    lbl.textContent = '내 최종 부담 · ' + row.name + ' 기준';
    num.classList.remove('pilot-hero-num--guide');
    // 부이 #1245 ①·#1279 ④ — '모르겠어요' 후기 행은 범위로 표시한다. 375/360px에서
    // 한 줄에 안 들어가므로(32px) 글자를 줄이지 않고 하한/상한 두 줄로 나눈다.
    if (row.copay_hi !== null && row.copay_hi !== undefined) {
      num.innerHTML = '';
      var lo = document.createElement('div');
      lo.className = 'pilot-hero-range-line';
      lo.textContent = '하한 ' + won(row.copay);
      var hi = document.createElement('div');
      hi.className = 'pilot-hero-range-line';
      hi.textContent = '상한 ' + won(row.copay_hi);
      num.appendChild(lo);
      num.appendChild(hi);
    } else {
      num.textContent = won(row.copay);
    }
    setHeroRange(row);
    var rejoinNote = '';
    if (row.sub === 'early') {
      rejoinNote = ' 전기(2013년 3월 이전 가입)는 재가입 조건이 없어 보장이 그대로 유지됩니다' +
        '(단, 2013년 1월~3월 표준형 가입자는 15년마다 재가입합니다).';
    } else if (row.sub === 'late') {
      rejoinNote = ' 후기(2013년 4월 이후 가입)는 15년마다 재가입하는 유형으로, 가입 시점에 따라 ' +
        '2028년부터 재가입 시점이 도래합니다.';
    }
    if (row.status === 'excluded') {
      sub.textContent = '이 항목은 ' + row.name + '에서 보장 제외라 전액 본인부담입니다(예상 보장액 0원).' + rejoinNote;
    } else {
      // 관리급여 항목은 보장액+부담의 합이 진료비의 95%(건강보험 본인부담)라,
      // '진료비 중 내가 내는 금액'만 쓰면 합계가 안 맞는 것처럼 보인다 (인스팅트 #1215 ②).
      // 남은 5%는 공단 부담임을 밝혀 둔다. 1회 건강보험 본인부담과 10회 최종 부담이
      // 우연히 같은 숫자(41,658원)라 헷갈리므로 횟수도 함께 적는다.
      var items = (window.MED_CATALOG && window.MED_CATALOG.items) || [];
      var it = null;
      items.forEach(function (x) { if (x.code === st.item_code) { it = x; } });
      if (it && it.payment === '관리급여') {
        var burden95 = row.covered + row.copay;
        var insurer = res.input.amount - burden95;
        // 부이 #1296 — 2세대·통원·2회 이상: 공제가 방문 1회마다 따로 적용됨을 금액 바로 아래 한 줄로 푼다.
        // 부이 #1310 ② — 3·4세대도 회당 공제 × 횟수라 같은 한 줄을 붙인다.
        var perVisitNote = ((myGen === 2 || myGen === 3 || myGen === 4) && st.visit === 'out' && st.rounds > 1)
          ? ' 병원 방문 1회마다 공제가 따로 적용돼요(하루 1회 방문 기준).' : '';
        // 부이 #1310 ① — 1회 통원: 외래공제가 지배해 2세대 세부 유형 5개가 모두 같은 금액이면
        // 버튼을 눌러도 숫자가 안 바뀐다는 것을 한 줄로 밝힌다. 금액을 바꿔 유형별 금액이
        // 달라지는 경우에는 거짓 안내가 되므로, '모르겠어요' 범위로 실제 동일함을 확인한 때만 붙인다.
        var oneRoundNote = '';
        if (myGen === 2 && st.visit === 'out' && st.rounds === 1) {
          try {
            var resU = window.MedCalc.compute(Object.assign({}, st, { gen2_type: 'unknown' }), items);
            var eRow = null, lRow = null;
            resU.generations.forEach(function (r) {
              if (r.gen === 2 && r.sub === 'early') { eRow = r; }
              if (r.gen === 2 && r.sub === 'late') { lRow = r; }
            });
            if (eRow && lRow && (lRow.copay_hi === null || lRow.copay_hi === undefined) &&
                eRow.copay === lRow.copay) {
              oneRoundNote = ' 1회는 유형과 관계없이 같아요.';
            }
          } catch (e) { /* 무시 — 확인이 안 되면 붙이지 않는다 */ }
        }
        sub.textContent = '예상 보장액 ' + won(row.covered) + ' · 자기부담 기준 ' + row.rate_label +
          ' · ' + st.rounds + '회 진료비 ' + won(res.input.amount) + ' 중 건강보험 본인부담 ' + won(burden95) +
          '(95%)에서 내가 내는 금액입니다. 나머지 ' + won(insurer) + '(5%)은 공단이 부담합니다.' + perVisitNote + oneRoundNote + rangeNote(row) + rejoinNote;
      } else {
        sub.textContent = '예상 보장액 ' + won(row.covered) + ' · 자기부담 기준 ' + row.rate_label +
          ' · 진료비 ' + won(res.input.amount) + ' 중 내가 내는 금액입니다.' + rangeNote(row) + rejoinNote;
      }
    }
  }

  /* 내 세대 선택 */
  var genGroup = $('#pilot-gen-group');
  var gen2Sub = $('#pilot-gen2-sub');
  if (genGroup) {
    genGroup.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        myGen = Number(b.getAttribute('data-mygen')) || 0;
        genGroup.querySelectorAll('button').forEach(function (x) {
          x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
        });
        if (gen2Sub) { gen2Sub.style.display = myGen === 2 ? '' : 'none'; }
        render();
      });
    });
  }

  /* 2세대 세부(전기/후기) 선택 — 메인 계산기의 #gen2-select 와 값을 맞춘다 */
  var gen2Group = $('#pilot-gen2-group');
  if (gen2Group) {
    gen2Group.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        myGen2 = b.getAttribute('data-mygen2') || '';
        gen2Group.querySelectorAll('button').forEach(function (x) {
          x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
        });
        var g2sel = $('#gen2-select');
        if (g2sel && myGen2) {
          g2sel.value = myGen2;
          g2sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
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
