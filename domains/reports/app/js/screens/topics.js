// 주제 — 이 도메인이 푸는 문제에 실제로 닿는 화면이다.
// 3년 전 보고서는 타임라인 저 아래에 있고, 검색은 찾을 단어를 이미 알아야 쓴다.
// 주제 칩은 단어를 모를 때 쓰는 입구다.
import { esc } from '../data.js';
import { reportRow, empty } from '../ui.js';

export function topicChips(reports) {
  const count = new Map();
  for (const r of reports || []) {
    for (const t of r.matched || []) count.set(t, (count.get(t) || 0) + 1);
  }
  return [...count.entries()]
    .map(([topic, n]) => ({ topic, count: n }))
    .sort((a, b) => b.count - a.count || (a.topic < b.topic ? -1 : 1));
}

export function reportsForTopic(reports, topic) {
  return (reports || [])
    .filter((r) => (r.matched || []).includes(topic))
    .sort((a, b) => (a.published < b.published ? 1 : -1));
}

export function render(el, ctx) {
  const topic = ctx.route.params[0];
  if (!topic) {
    const chips = topicChips(ctx.reports);
    el.innerHTML = chips.length ? `
      <div class="section-title">주제로 찾기</div>
      <div class="grid">
        ${chips.map((c) => `
          <a class="tile" href="#/topics/${encodeURIComponent(c.topic)}">
            <div class="tile__name">${esc(c.topic)}</div>
            <div class="tile__count">${c.count}건</div>
          </a>`).join('')}
      </div>` : empty('아직 주제를 붙일 보고서가 없습니다.');
    return;
  }
  const rows = reportsForTopic(ctx.reports, topic);
  el.innerHTML = `
    <a class="back" href="#/topics">← 주제</a>
    <div class="section-title">${esc(topic)} · ${rows.length}건</div>
    <div class="list">${rows.map((r) => reportRow(r)).join('')}</div>`;
}
