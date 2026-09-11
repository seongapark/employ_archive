// 보도자료 화면. 총괄 카드를 누르면 여기로 온다.
//
// 누른 카드를 그대로 맨 위에 다시 그린다(overview 의 cardHtml 을 빌려 쓴다).
// 화면을 바꾸면서 방금 본 숫자가 사라지면, 아래를 읽는 동안 그것이 무엇에
// 대한 것인지를 기억으로만 붙들어야 한다.
//
// 그 아래가 이 화면의 본론이다: 그 조사가 발표하는 **주요 지표**와 그 시계열.
// 보도자료 요약과 속성별 상위는 접어 둔다 — 지표가 주인공이다(사용자 판단).

import { switcherHtml, bindSwitcher } from '../switcher.js';
import { cardHtml } from './overview.js';
import { comboSvg, indexAtRatio } from '../chart.js';
import {
  overviewCards, topMovers, segmentsOf, indicatorSeries, fmtValue, fmtChange,
  fmtDelta, deltaTone, monthLabel, esc,
} from '../data.js';

// 그림에 쓰는 기간. 25개월이면 휴대폰 가로폭에서 막대가 아직 구분된다.
const TREND_MONTHS = 25;

// 출처마다 발표하는 지표가 다르다. 지금은 경활만 총괄 지표를 읽는다 —
// 사업체·행정통계는 이 화면을 보고 넓히기로 했다(2026-09-11 사용자 판단).
// 여기 없는 출처는 지표 구역 자체가 뜨지 않는다.
const INDICATORS = {
  eaps: {
    // KPI 는 보도자료가 직접 앞세우는 넷이다. 그래서 아래 접힌 요약과 숫자가
    // 딱 맞아떨어진다 — 요약이 "15~64세 고용률 70.4%" 라고 말하면 타일도 70.4% 다.
    kpis: [
      { label: '15~64세 고용률', sub: 'OECD 비교기준', indicator: 'employment_rate',
        breakdown: 'scope', category: '15-64' },
      { label: '청년층 고용률', sub: '15~29세', indicator: 'employment_rate',
        breakdown: 'scope', category: '15-29' },
      { label: '실업률', sub: '15세 이상', indicator: 'unemployment_rate' },
      { label: '청년층 실업률', sub: '15~29세', indicator: 'unemployment_rate',
        breakdown: 'scope', category: '15-29' },
    ],
    trends: [
      { name: '취업자', indicator: 'headcount' },
      { name: '실업자', indicator: 'unemployed' },
      { name: '고용률', indicator: 'employment_rate' },
      { name: '실업률', indicator: 'unemployment_rate' },
      { name: '경제활동참가율', indicator: 'participation_rate' },
      { name: '비경제활동인구', indicator: 'inactive' },
    ],
  },
};

// 사업체노동력조사의 released_at 은 보도자료 발표일이 아니라 KOSIS 표 갱신일이다.
const DEPTH = { '□': 1, '▣': 1, '○': 2, 'ㅇ': 2, '-': 2, '*': 3, '▸': 3 };

function digestHtml(card) {
  const lines = card.summaryLines || [];
  if (!lines.length) {
    // 지어내지 않는다. 아직 안 읽은 달과 원문 형식이 바뀐 달이 여기로 온다.
    return `<p class="digest__empty">이 달 요약은 아직 없습니다.
      <a href="${esc(card.releaseUrl)}" rel="noopener">보도자료 원문</a>에서 확인해 주세요.</p>`;
  }
  return lines.map(line =>
    `<p class="digest__line" data-depth="${DEPTH[line.slice(0, 1)] || 1}">${esc(line)}</p>`
  ).join('') + `<p class="digest__note">${esc(card.name_ko)} 보도자료 원문의 요약을 그대로 옮긴 것입니다.</p>`;
}

function moversHtml(groups) {
  const block = group => {
    const rows = group.rows.map(row => {
      const href = `#/b/${esc(group.breakdown)}/${encodeURIComponent(row.code)}`;
      return `<a class="mover" href="${href}">
        <span class="mover__name">${esc(row.short_ko || row.name_ko)}</span>
        <span class="mover__delta num ${deltaTone(row.yoy)}">${esc(fmtDelta(row.yoy))}</span>
      </a>`;
    }).join('');
    return `<div class="movers__group">
      <h4 class="movers__title">${esc(group.name_ko)}</h4>
      <div class="movers__rows">${rows}</div>
    </div>`;
  };
  return groups.map(block).join('')
    + '<p class="movers__note">전년동월대비 증감 · 누르면 세 출처를 나란히 봅니다</p>';
}

function kpiHtml(spec, point) {
  if (!point) {
    return `<div class="kpi kpi--empty">
      <div class="kpi__label">${esc(spec.label)}<span class="kpi__sub">${esc(spec.sub)}</span></div>
      <div class="kpi__value kpi__value--empty">미발표</div>
    </div>`;
  }
  return `<div class="kpi">
    <div class="kpi__label">${esc(spec.label)}<span class="kpi__sub">${esc(spec.sub)}</span></div>
    <div class="kpi__value num">${esc(fmtValue(point.value, point.unit))}</div>
    <div class="kpi__delta num ${deltaTone(point.yoy)}">${esc(fmtChange(point.yoy, point.unit))}</div>
  </div>`;
}

// 머리줄이 스크럽 라벨을 겸한다. 그림 위에 뜨는 말풍선을 따로 두면 손가락이
// 그걸 가리므로, 읽을 자리를 손가락 밖에 고정해 둔다.
function trendHead(name, point) {
  return `<h3 class="trend__name">${esc(name)}</h3>
    <span class="trend__month num">${esc(monthLabel(point.period))}</span>
    <span class="trend__now num">${esc(fmtValue(point.value, point.unit))}</span>
    <span class="trend__delta num ${deltaTone(point.yoy)}">${esc(fmtChange(point.yoy, point.unit))}</span>`;
}

function trendHtml(spec, points) {
  const last = points[points.length - 1];
  const unit = last.unit;
  const values = points.map(p => p.value);
  const range = unit === '%'
    ? `${Math.min(...values).toFixed(1)} ~ ${Math.max(...values).toFixed(1)}%`
    : `${esc(fmtValue(Math.min(...values), unit))} ~ ${esc(fmtValue(Math.max(...values), unit))}`;
  return `<article class="trend" data-indicator="${esc(spec.indicator)}">
    <div class="trend__head">${trendHead(spec.name, last)}</div>
    <div class="trend__plot">${comboSvg(points, { selected: last.period })}</div>
    <div class="trend__foot">
      <span class="num">${esc(monthLabel(points[0].period))}</span>
      <span class="num">${range}</span>
      <span class="num">${esc(monthLabel(last.period))}</span>
    </div>
  </article>`;
}

// 그림을 누르거나 끌면 그 달로 세로선이 옮겨가고 머리줄이 그 달을 말한다.
// 손을 떼도 남는다 — 읽으라고 띄운 것이다.
function bindScrub(el, byIndicator) {
  el.querySelectorAll('.trend').forEach(card => {
    const points = byIndicator.get(card.dataset.indicator);
    if (!points || points.length < 2) return;
    const plot = card.querySelector('.trend__plot');
    const head = card.querySelector('.trend__head');
    const name = card.querySelector('.trend__name').textContent;
    let shown = points.length - 1;

    const move = event => {
      const box = plot.getBoundingClientRect();
      if (!box.width) return;
      const idx = indexAtRatio(points, (event.clientX - box.left) / box.width);
      if (idx === null || idx === shown) return;
      shown = idx;
      head.innerHTML = trendHead(name, points[idx]);
      plot.innerHTML = comboSvg(points, { selected: points[idx].period });
    };

    plot.addEventListener('pointerdown', event => {
      // 세로 스크롤을 뺏지 않으려면 손가락이 실제로 가로로 움직일 때만
      // 잡아야 하지만, 그림이 낮아(96px) 세로로 스치는 일이 드물다.
      // 대신 setPointerCapture 로 그림 밖으로 나가도 계속 따라온다.
      plot.setPointerCapture(event.pointerId);
      move(event);
    });
    plot.addEventListener('pointermove', event => {
      if (event.buttons || plot.hasPointerCapture?.(event.pointerId)) move(event);
    });
  });
}

export function render(el, ctx) {
  const code = ctx.state.releaseCode;
  const cards = overviewCards(ctx.series, ctx.sources, ctx.state.period, ctx.releases);
  const card = cards.find(c => c.code === code);
  if (!card) {                       // 라우트가 걸렀어야 하지만, 화면이 먼저 죽지는 않는다
    el.innerHTML = '<p class="note">알 수 없는 출처입니다. <a href="#/">총괄로</a></p>';
    return;
  }

  const spec = INDICATORS[code];
  const byIndicator = new Map();
  let kpiBlock = '';
  let trendBlock = '';

  if (spec) {
    const kpis = spec.kpis.map(k => {
      const points = indicatorSeries(ctx.series, {
        source: code, indicator: k.indicator,
        breakdown: k.breakdown || 'total', category: k.category || null,
      });
      return kpiHtml(k, points.find(p => p.period === ctx.state.period) || null);
    }).join('');
    kpiBlock = `<h2 class="section__title">주요 지표</h2><div class="kpis">${kpis}</div>`;

    const drawn = spec.trends.map(t => {
      const points = indicatorSeries(ctx.series, {
        source: code, indicator: t.indicator, months: TREND_MONTHS,
      });
      if (!points.length) return '';
      byIndicator.set(t.indicator, points);
      return trendHtml(t, points);
    }).filter(Boolean).join('');
    if (drawn) {
      trendBlock = `<h2 class="section__title">추이</h2><div class="trends">${drawn}</div>`;
    }
  }

  const groups = topMovers(ctx.series, {
    source: code, period: ctx.state.period,
    segments: segmentsOf(ctx.industries, ctx.segments),
  });

  el.innerHTML = `<a class="backlink" href="#/">
      <span aria-hidden="true">←</span> 총괄</a>`
    + switcherHtml(ctx)
    // 여기서는 카드가 문이 아니다. 이미 그 방 안이므로 이름을 링크로 두면
    // 같은 화면으로 가는 링크가 된다.
    + `<div class="cards">${cardHtml(card, { linked: false })}</div>`
    + kpiBlock
    + trendBlock
    + `<details class="fold">
        <summary>보도자료 요약 ${card.summaryLines.length
          ? `<span class="fold__count">${card.summaryLines.length}줄</span>` : ''}</summary>
        <div class="fold__body">${digestHtml(card)}</div>
      </details>`
    + (groups.length ? `<details class="fold">
        <summary>가장 크게 움직인 곳 <span class="fold__count">${
          groups.reduce((n, g) => n + g.rows.length, 0)}줄</span></summary>
        <div class="fold__body">${moversHtml(groups)}</div>
      </details>` : '');

  bindSwitcher(el, ctx);
  bindScrub(el, byIndicator);
}
