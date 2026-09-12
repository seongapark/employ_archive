import { esc, roundOf, dayLabel, citeRate } from '../data.js';
import { pieChart, card, headlineRow, section } from '../ui.js';

// 홈은 '이 회차 보도가 어떻게 됐나'를 세 숫자로 먼저 말한다.
//
// KPI 는 **수집 → 인용 → 논조** 순이다. 앞의 것이 뒤의 것의 분모다 —
// 81건을 모아 73건이 인용이고, 그 73건의 논조가 어느 쪽이었다. 순서를 바꾸면
// 숫자끼리 무슨 관계인지 알 수 없다.
//
// 「보도자료 밖 표현」 밴드와 「보도자료 ↔ 기사의 격차」 상자는 2026-09-11 에
// 뺐다. 낱말 몇 개와 숫자 세 줄이 화면 맨 위에서 시선을 먼저 가져갔는데,
// 그것만 보고는 무엇을 해야 하는지 알 수 없었다. 밖 표현은 기사 화면의
// 키워드그래프와 후속 화면의 「살아남은 표현」이 이미 더 잘 보여준다.

function kpis(round) {
  const r = round.regular;
  const st = round.stance || { label: '판정 없음', judged: 0 };
  const cells = [
    { n: r.kept, label: '수집', sub: '', info: true },
    { n: r.cited, label: '인용', sub: `해당 보도자료 직접인용 ${citeRate(round)}%` },
    // 내역(부정12·긍정31)은 바로 아래 막대와 범례가 말한다 — 여기서 또 쓰면
    // 같은 숫자가 두 줄 연달아 나온다.
    { n: st.label, label: '언론 논조',
      sub: st.judged ? `인용 ${st.judged}건 기준` : 'LLM 판정 필요', small: true },
  ];
  // 이름이 먼저, 숫자가 뒤. 숫자만 셋이 나란히 서면 무엇의 숫자인지 밑줄까지
  // 내려가 읽어야 한다 — 셋을 훑는 눈이 매번 위아래로 왕복한다.
  const body = cells.map((c) => `
    <div class="card kpi" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:1px;">
      ${c.info ? `<button type="button" class="kpi__info" data-info
          aria-expanded="false" aria-controls="collectInfo" aria-label="수집 기준 보기">i</button>` : ''}
      <div style="font-size:11px;color:var(--text-secondary);">${esc(c.label)}</div>
      <div class="num" style="font-size:${c.small ? 15 : 22}px;font-weight:700;line-height:1.3;padding:${c.small ? '2px 0 1px' : '0'};">${esc(String(c.n))}</div>
      ${c.sub ? `<div class="num" style="font-size:10px;color:var(--text-muted);">${esc(c.sub)}</div>` : ''}
    </div>`).join('');
  // 수집 기준은 늘 펼쳐 두지 않는다 — 매번 읽을 글은 아니지만, 숫자만 있고
  // 기준이 없으면 '81건'이 무엇의 81건인지 알 수 없어 지울 수도 없다.
  return `<div style="position:relative;">
    <div style="display:flex;gap:8px;">${body}</div>
    ${criteria(round)}
  </div>`;
}

/** 논조 막대. 판정이 없으면 그리지 않는다 — 빈 막대는 '중립'처럼 보인다. */
function stanceBar(round) {
  const st = round.stance;
  if (!st || !st.judged) {
    return `<div style="font-size:10px;color:var(--text-muted);padding:0 2px;">
      논조는 기사마다 LLM 이 판정합니다. 이 회차는 아직 판정이 없습니다.</div>`;
  }
  const seg = (n, cls, name) => (n ? `<div class="stance__seg ${cls}"
    style="flex:${n};" title="${esc(name)} ${n}건"></div>` : '');
  // 색만으로 뜻을 나르지 않는다 — 어느 색이 무엇인지 바로 아래가 글자로 말한다.
  const key = (n, cls, name) => (n ? `<span class="stance__key">
    <i class="stance__dot ${cls}"></i>${name} ${n}</span>` : '');
  return `<div style="padding:0 2px;">
    <div class="stance">
      ${seg(st.neg, 'stance__seg--neg', '부정')}
      ${seg(st.neu, 'stance__seg--neu', '중립')}
      ${seg(st.pos, 'stance__seg--pos', '긍정')}
    </div>
    <div class="stance__keys">
      ${key(st.neg, 'stance__seg--neg', '부정')}
      ${key(st.neu, 'stance__seg--neu', '중립')}
      ${key(st.pos, 'stance__seg--pos', '긍정')}
    </div>
  </div>`;
}

/** 수집 기준 — 수집 KPI 의 i 를 누르면 그 아래에 뜬다. */
function criteria(round) {
  const r = round.regular;
  const qs = r.queries || [];
  const shown = qs.slice(0, 3).join(' · ');
  const more = qs.length > 3 ? ` 외 ${qs.length - 3}개` : '';
  const win = (r.window || []).map(dayLabel).join('~');
  return `<div class="infobox" id="collectInfo" hidden>
    <div class="infobox__title">수집 기준</div>
    <div>· 네이버 뉴스 검색어 ${qs.length}개 — ${esc(shown)}${esc(more)}</div>
    <div>· 발행 ${esc(win)} (배포 당일과 그 이튿날)</div>
    <div>· 제목·요약에 ${esc((r.anchors || []).join(' · '))} 중 하나가 든 것만 남김</div>
  </div>`;
}

function coverageCard(round) {
  const c = round.coverage;
  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:8px;">기사화 현황</div>
    <div class="pie__row">
      ${pieChart('섹션', c.section)}
      ${pieChart('연령', c.age)}
      ${pieChart('산업', c.industry)}
    </div>`);
}

function issueCard(round, ctx) {
  const rows = round.issues.slice(0, 4).map((iss) => {
    const heads = iss.heads.slice(0, 3).map(headlineRow).join('');
    const kw = iss.kw.length
      ? ` <span style="font-weight:400;color:var(--frame-fg);">— ${esc(iss.kw.join('·'))}</span>` : '';
    return `<div style="padding:8px 0;border-top:1px solid var(--border);">
      <div style="font-size:12px;font-weight:600;">${esc(iss.key)} ${iss.n}건${kw}</div>
      ${heads}</div>`;
  }).join('');
  const more = round.issues.length > 4
    ? `<div style="margin-top:8px;"><a href="#/articles">기사 전체 보기 ›</a></div>` : '';
  return card(`<div style="font-size:13px;font-weight:700;">이슈별 헤드라인</div>${rows}${more}`);
}

function rivalCard(round) {
  const rows = round.rivals || [];
  const total = rows.reduce((n, r) => n + r.n, 0);
  if (!total) return '';

  // 이름 붙은 의제(2건 이상 모인 것)가 없으면 아무것도 안 그린다 —
  // 서로 다른 주제 여덟 건은 '경쟁 의제'가 아니라 그냥 그날의 잡음이고,
  // 「없습니다」는 한 줄은 자리만 차지한다.
  const named = rows.filter((r) => r.topic !== '그 밖');
  if (!named.length) return '';

  const body = named.map((r) => {
    const heads = r.heads.slice(0, 2).map(headlineRow).join('');
    return `<div style="padding:8px 0;border-top:1px solid var(--border);">
      <div style="font-size:12px;font-weight:600;">${esc(r.topic)} ${r.n}건</div>
      ${heads}</div>`;
  }).join('');

  const other = rows.find((r) => r.topic === '그 밖');
  const tail = other
    ? `<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">그 밖 ${other.n}건</div>` : '';

  return card(`
    <div style="font-size:13px;font-weight:700;">그날 함께 돈 다른 의제</div>
    <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">
      이 보도자료를 인용하지 않았지만 같은 날 같은 지면에서 돈 기사입니다.</div>
    ${body}${tail}`);
}

// 화면이 자기 결함을 먼저 말한다. 수집이나 판정이 덜 된 채로 그린 숫자는
// 「언론이 덜 다뤘다」와 구별이 안 되는데, 뜻이 정반대다.
function warnCard(round) {
  const rows = [];
  if (round.truncated.length) {
    rows.push(`<div style="font-weight:700;">이 회차 수집은 불완전합니다</div>
      <div>검색어 ${esc(round.truncated.join(', '))} 가 1,000건 상한에 걸려 구간 전체를 못 훑었습니다.</div>`);
  }
  // 판정 없는 기사는 '인용 아님'으로 세어진다 — 말하지 않으면 인용률이 떨어진
  // 것처럼만 보이고, 그게 언론 탓인지 판정 탓인지 알 수 없다.
  if (round.unjudged) {
    rows.push(`<div style="font-weight:700;">판정이 덜 됐습니다</div>
      <div>기사 ${round.unjudged}건이 판정 없이 남아 인용이 아닌 것으로 세어지고 있습니다.
      아래 숫자는 그만큼 적게 잡힌 값입니다.</div>`);
  }
  if (!rows.length) return '';
  return `<div class="gapbox" style="color:var(--frame-fg);background:var(--frame-bg);">
    ${rows.join('<div style="height:6px;"></div>')}</div>`;
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }
  root.innerHTML = `
    ${section(`
      ${warnCard(round)}
      ${kpis(round)}
      ${stanceBar(round)}
      ${coverageCard(round)}
      ${issueCard(round, ctx)}
      ${rivalCard(round)}
    `)}`;

  bindInfo(root);
}

/** i 버튼. 한 번 더 누르거나 바깥을 누르면 닫힌다 — 열어 둔 채로는 덮인 곳을 못 본다. */
function bindInfo(root) {
  const btn = root.querySelector('[data-info]');
  const box = root.querySelector('#collectInfo');
  if (!btn || !box) return;

  const close = () => {
    box.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  };
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = box.hidden;
    box.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  });
  root.addEventListener('click', (e) => { if (!box.contains(e.target)) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
}
