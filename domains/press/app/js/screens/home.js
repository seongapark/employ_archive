import { esc, roundOf, dayLabel, citeRate } from '../data.js';
import { barGroup, card, section } from '../ui.js';

// 홈은 '지금 무엇이 번지고 있나'를 먼저 보여준다. 기사 목록은 기사 탭이 맡는다.
// 순서를 바꾸지 말 것 — 이 도메인의 목적은 왜곡을 늦게 발견하지 않는 것이다.

function frameBand(round) {
  const top = round.outside.slice(0, 4);
  if (!top.length) {
    return `<div class="band"><div class="band__title">보도자료 밖 표현 없음</div>
      <div class="band__meta">두 곳 이상이 공통으로 쓴 새 표현이 없습니다.</div></div>`;
  }
  const words = top.map((x) => `${esc(x.w)} <span class="num">${x.n}</span>`).join(' · ');
  return `<div class="band band--frame">
    <div class="band__title">${words}</div>
    <div class="band__meta">보도자료에 없는 말 · 인용 ${round.regular.cited}건에서 셈</div>
  </div>`;
}

function kpis(round) {
  const r = round.regular;
  const f = round.follow;
  const cells = [
    { n: r.cited, label: '인용 기사', sub: `수집 ${r.collected}건 중` },
    { n: r.press, label: '보도 언론사', sub: f ? `후속 ${f.press}곳` : '정기 기준' },
    { n: round.outside.length, label: '밖 표현', sub: '2건 이상 반복' },
    { n: `${citeRate(round)}%`, label: '인용률', sub: `나머지 ${r.kept - r.cited}건은 딴 얘기` },
  ];
  const body = cells.map((c) => `
    <div class="card" style="flex:1;min-width:0;display:flex;flex-direction:column;gap:1px;">
      <div class="num" style="font-size:22px;font-weight:700;line-height:1.2;">${esc(String(c.n))}</div>
      <div style="font-size:11px;color:var(--text-secondary);">${esc(c.label)}</div>
      <div class="num" style="font-size:10px;color:var(--text-muted);">${esc(c.sub)}</div>
    </div>`).join('');
  return `<div style="display:flex;gap:8px;">${body}</div>`;
}

function gapCard(round) {
  if (!round.gaps.length) return '';
  const rows = round.gaps.map((g) => `<div>· ${esc(g)}</div>`).join('');
  return `<div class="gapbox">
    <div style="font-weight:700;">보도자료 ↔ 기사의 격차</div>${rows}</div>`;
}

function coverageCard(round) {
  const c = round.coverage;
  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:8px;">보도자료가 다룬 것 중 무엇이 기사화됐나</div>
    ${barGroup('보도자료 섹션', c.section)}
    ${barGroup('연령', c.age)}
    ${barGroup('산업', c.industry)}
    <div style="font-size:10px;color:var(--text-muted);">빗금 = 0건 · 축마다 눈금이 다르므로 막대 길이는 같은 축 안에서만 비교</div>`);
}

function issueCard(round, ctx) {
  const rows = round.issues.slice(0, 4).map((iss) => {
    const heads = iss.heads.slice(0, 3).map((h) => `
      <div style="font-size:12px;line-height:1.5;margin-top:3px;">
        ${h.url ? `<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a>`
                : esc(h.title)}
        <span style="color:var(--text-muted);">(${esc(h.press)})</span>
      </div>`).join('');
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

  // 이름 붙은 의제(2건 이상 모인 것)가 없으면 카드를 세우지 않는다 —
  // 서로 다른 주제 여덟 건은 '경쟁 의제'가 아니라 그냥 그날의 잡음이다.
  const named = rows.filter((r) => r.topic !== '그 밖');
  if (!named.length) {
    return `<div style="font-size:11px;color:var(--text-muted);padding:0 2px;">
      인용이 아닌 ${total}건은 서로 다른 주제였습니다 — 같이 번진 의제는 없습니다.
      <a href="#/articles">기사에서 보기 ›</a></div>`;
  }

  const body = named.map((r) => {
    const heads = r.heads.slice(0, 2).map((h) => `
      <div style="font-size:12px;line-height:1.5;margin-top:3px;">
        ${h.url ? `<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a>`
                : esc(h.title)}
        <span style="color:var(--text-muted);">(${esc(h.press)})</span>
      </div>`).join('');
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

function pressCard(round) {
  if (!round.new_press.length) return '';
  const names = round.new_press.slice(0, 12).join(' · ');
  const more = round.new_press.length > 12 ? ` 외 ${round.new_press.length - 12}곳` : '';
  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:4px;">지난 회차엔 없던 매체 ${round.new_press.length}곳</div>
    <div style="font-size:11px;color:var(--text-secondary);line-height:1.6;">${esc(names)}${esc(more)}</div>
    <div style="font-size:10px;color:var(--text-muted);margin-top:5px;">늘 쓰던 곳 밖에서 들어온 보도는 새 프레임이 생기는 자리입니다.</div>`);
}

function warnCard(round) {
  if (!round.truncated.length) return '';
  return `<div class="gapbox" style="color:var(--frame-fg);background:var(--frame-bg);">
    <div style="font-weight:700;">이 회차 수집은 불완전합니다</div>
    <div>검색어 ${esc(round.truncated.join(', '))} 가 1,000건 상한에 걸려 구간 전체를 못 훑었습니다.</div></div>`;
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }
  const f = round.follow;
  const meta = `${dayLabel(round.release)} 배포 · ${esc(round.title)}`
    + (f ? ` · 후속 ${f.cited}건` : ' · 후속 미수집');

  root.innerHTML = `
        ${frameBand(round)}
    ${section(`
      <div style="font-size:11px;color:var(--text-muted);margin:-2px 0 -2px 2px;">${meta}</div>
      ${warnCard(round)}
      ${kpis(round)}
      ${gapCard(round)}
      ${coverageCard(round)}
      ${issueCard(round, ctx)}
      ${rivalCard(round)}
      ${pressCard(round)}
    `)}`;

}
