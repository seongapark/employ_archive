// 증감 비교 시트의 그림. SVG 문자열만 만든다 — DOM 을 만지지 않아 테스트가 된다.
import { SOURCE_ORDER, SOURCE_COLORS, fmtLevel, fmtDelta, monthLabel, emptyLabel, esc } from './data.js';

// 한 행에 출처 약칭과 수준이 두 줄로 들어간다.
const ROW_H = 42;
// 출처 약칭(경활·사업체·행정통계)과 그 아래 수준(`2,913.6만명`)이 들어갈 폭.
// 정식명을 쓰던 때는 96 이었고 약칭으로 66 까지 줄었다. 값 라벨 여백
// (VALUE_GUTTER)과 함께 chart.test.mjs 의 좌표 불변식이 이 두 값을 지킨다.
export const LABEL_W = 66;
// 값 라벨이 들어갈 자리. `+27.7만명` 같은 한국어 라벨은 11px 기준 55~60px 다.
// 이 여백이 좁으면 최대 막대의 라벨이 출처명 열을 침범하거나 오른쪽에서 잘린다 —
// 값 직접 라벨은 #1baf7a 대비 미달에 대한 의무 완화 조치라 잘리면 안 된다(스펙 7.6).
export const VALUE_GUTTER = 64;

export function barsSvg(snapshot, { width = 320, sourceNames = {} } = {}) {
  const rows = snapshot.filter(s => SOURCE_ORDER.includes(s.source));
  const height = rows.length * ROW_H + 8;
  const plotW = width - LABEL_W - 8;
  const max = Math.max(1, ...rows.map(r => Math.abs(r.yoy ?? 0)));
  const zero = LABEL_W + plotW / 2;

  const parts = [
    `<line class="chart__zero" x1="${zero}" y1="0" x2="${zero}" y2="${height}" stroke="#e2e5ea" stroke-width="1"></line>`,
  ];

  rows.forEach((row, i) => {
    const top = i * ROW_H + 6;
    const name = sourceNames[row.source] || row.source;
    parts.push(`<text x="0" y="${top + 11}" font-size="11" fill="#667085">${esc(name)}</text>`);
    // 증감만으로는 규모를 알 수 없다 — 취업자 2,913.6만명 위의 +10.8만명 과
    // 상시가입자 1,587.7만명 위의 +27.7만명 은 뜻이 다르다. 수준을 같이 싣는다.
    if (row.value !== null && row.value !== undefined) {
      parts.push(`<text x="0" y="${top + 23}" font-size="9.5" fill="#98a2b3">${esc(fmtLevel(row.value))}</text>`);
    }

    if (row.state !== 'value') {
      parts.push(`<text x="${zero + 6}" y="${top + 15}" font-size="11" fill="#98a2b3">${esc(emptyLabel(row.state))}</text>`);
      return;
    }
    const w = (Math.abs(row.yoy) / max) * (plotW / 2 - VALUE_GUTTER);
    const x = row.yoy >= 0 ? zero : zero - w;
    parts.push(
      `<rect x="${x.toFixed(1)}" y="${top + 2}" width="${Math.max(w, 1).toFixed(1)}" height="18" rx="4" fill="${SOURCE_COLORS[row.source]}"></rect>`,
      // 값은 막대 끝에 직접 붙인다. #1baf7a 의 대비 미달에 대한 완화 조치이므로
      // 지울 수 없다(스펙 7.6). 글자에는 계열 색을 입히지 않는다.
      `<text x="${(row.yoy >= 0 ? x + w + 5 : x - 5).toFixed(1)}" y="${top + 15}" font-size="11" fill="#191d24" text-anchor="${row.yoy >= 0 ? 'start' : 'end'}">${esc(fmtDelta(row.yoy))}</text>`,
    );
  });

  return `<svg class="chart chart--bars" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img">${parts.join('')}</svg>`;
}

// 시계열이 실제로 그리는 기간 목록. 드래그가 x 좌표를 기간으로 옮길 때 같은
// 목록을 봐야 하므로 그림과 조작이 이 함수 하나를 공유한다.
export function timelinePeriods(timeline) {
  return Array.from(new Set(
    SOURCE_ORDER.flatMap(s => (timeline[s] || []).map(p => p.period)))).sort();
}

export const TIMELINE_PAD = { l: 8, r: 8, t: 10, b: 18 };

// SVG 가로 비율(0~1)을 기간으로. 좌표 계산을 화면 코드에 두면 그림과 어긋나는
// 날이 오므로 여기 둔다 — 순수 함수라 테스트도 된다.
export function periodAtRatio(periods, ratio, { width = 320 } = {}) {
  if (!periods.length) return null;
  const plotW = width - TIMELINE_PAD.l - TIMELINE_PAD.r;
  const step = plotW / Math.max(1, periods.length - 1);
  const idx = Math.round((ratio * width - TIMELINE_PAD.l) / step);
  return periods[Math.min(periods.length - 1, Math.max(0, idx))];
}

export function timelineSvg(timeline, { width = 320, height = 160, selected = null } = {}) {
  const periods = timelinePeriods(timeline);
  if (!periods.length) return '';

  const pad = TIMELINE_PAD;
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const values = SOURCE_ORDER.flatMap(s => (timeline[s] || []).map(p => p.yoy)).filter(v => v !== null);
  const max = Math.max(1, ...values.map(Math.abs));
  const x = period => pad.l + (periods.indexOf(period) / Math.max(1, periods.length - 1)) * plotW;
  const y = value => pad.t + plotH / 2 - (value / max) * (plotH / 2);

  const parts = [
    `<line x1="${pad.l}" y1="${y(0)}" x2="${width - pad.r}" y2="${y(0)}" stroke="#e2e5ea" stroke-width="1"></line>`,
  ];

  if (selected && periods.includes(selected)) {
    const mx = x(selected);
    parts.push(
      `<line class="chart__marker" x1="${mx}" y1="${pad.t}" x2="${mx}" y2="${pad.t + plotH}" stroke="#667085" stroke-width="1" stroke-dasharray="3 3"></line>`,
      // 끌 수 있다는 것을 알리는 손잡이. 선만 있으면 잡을 수 있는지 보이지 않는다.
      `<circle class="chart__grip" cx="${mx}" cy="${pad.t}" r="4" fill="#667085"></circle>`,
    );
  }

  for (const source of SOURCE_ORDER) {
    const points = (timeline[source] || []).filter(p => p.yoy !== null);
    if (!points.length) continue;   // 출처가 빠져도 남은 색은 바뀌지 않는다
    const d = points.map(p => `${x(p.period).toFixed(1)},${y(p.yoy).toFixed(1)}`).join(' ');
    parts.push(`<polyline points="${d}" fill="none" stroke="${SOURCE_COLORS[source]}" stroke-width="2" stroke-linejoin="round"></polyline>`);
    const hit = selected && points.find(p => p.period === selected);
    if (hit) {
      parts.push(`<circle cx="${x(hit.period).toFixed(1)}" cy="${y(hit.yoy).toFixed(1)}" r="4.5" fill="${SOURCE_COLORS[source]}"></circle>`);
    }
  }

  parts.push(
    `<text x="${pad.l}" y="${height - 4}" font-size="10" fill="#98a2b3">${esc(monthLabel(periods[0]))}</text>`,
    `<text x="${width - pad.r}" y="${height - 4}" font-size="10" fill="#98a2b3" text-anchor="end">${esc(monthLabel(periods[periods.length - 1]))}</text>`,
  );

  return `<svg class="chart chart--line" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img">${parts.join('')}</svg>`;
}

// 대체 뷰는 그래프가 말하는 것을 다 말해야 한다 — 수준과 증감 둘 다.
// 빈 상태 행은 그래프와 같은 문구로 자리를 지킨다.
export function sheetTable(snapshot, { sourceNames = {} } = {}) {
  const rows = snapshot.map(s => {
    const empty = esc(emptyLabel(s.state));
    const level = s.value === null || s.value === undefined ? empty : esc(fmtLevel(s.value));
    const delta = s.state === 'value' ? esc(fmtDelta(s.yoy)) : empty;
    return `<tr><th scope="row">${esc(sourceNames[s.source] || s.source)}</th>` +
      `<td class="num">${level}</td><td class="num">${delta}</td></tr>`;
  }).join('');
  return `<table class="sheet__table"><caption class="sr-only">출처별 수준과 전년동월대비 증감</caption>` +
    `<thead><tr><th scope="col">출처</th><th scope="col">수준</th><th scope="col">증감</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}
