// 고용동향 순수 로직. DOM 도 네트워크도 모른다.
// 원자료 단위는 천명이고 yoy 는 비율이 아니라 천명 단위 증감량이다.

export const SOURCE_ORDER = ['eaps', 'est', 'ei'];

// 색은 출처 정체성만 나른다. 부호는 0선 기준 막대 방향이 말한다.
// 고정 배정이며 순환하지 않는다 — 출처가 빠져도 남은 색은 그대로다.
export const SOURCE_COLORS = { eaps: '#2a78d6', est: '#eb6834', ei: '#1baf7a' };

export function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function monthLabel(period) {
  return `${period.slice(0, 4)}.${period.slice(5, 7)}`;
}

function toMan(cheon) {
  return Math.round(cheon) / 10;
}

export function fmtLevel(cheon) {
  const man = toMan(cheon);
  return `${man.toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}만명`;
}

export function fmtDelta(cheon) {
  const man = toMan(cheon);
  const sign = man > 0 ? '+' : man < 0 ? '-' : '';
  return `${sign}${Math.abs(man).toFixed(1)}만명`;
}

// 증감의 색 토큰. 0 은 증가도 감소도 아니므로 중립이다 —
// `yoy >= 0` 로 묶으면 변동 없음이 증가색(빨강)으로 나간다.
export function deltaTone(yoy) {
  return yoy > 0 ? 'is-up' : yoy < 0 ? 'is-down' : 'is-flat';
}

function nextPeriod(period) {
  let year = Number(period.slice(0, 4));
  let month = Number(period.slice(5, 7)) + 1;
  if (month > 12) { month = 1; year += 1; }
  return `${year}-${String(month).padStart(2, '0')}`;
}

// 기준월 하한은 세 출처의 total 이 모두 있는 첫 달이다. 속성으로 재면
// 성·연령에는 사업체노동력조사가 아예 없어 하한이 속성마다 달라진다.
// 스위처는 하한부터 최신월까지 달마다 연속으로 채운다 — 특정 달에 아무 출처도
// 값을 내지 않았더라도(수집 공백) 사용자는 그 달을 선택할 수 있어야 한다.
export function monthOptions(series) {
  const totals = series.filter(r => r.breakdown === 'total');
  const bySources = new Map();
  for (const r of totals) {
    if (!bySources.has(r.period)) bySources.set(r.period, new Set());
    bySources.get(r.period).add(r.source);
  }
  const allPeriods = Array.from(bySources.keys()).sort();
  if (allPeriods.length === 0) {
    return { years: [], monthsByYear: {}, latest: null };
  }
  const complete = allPeriods.filter(p => SOURCE_ORDER.every(s => bySources.get(p).has(s)));
  const floor = complete[0];
  if (!floor) {
    return { years: [], monthsByYear: {}, latest: null };
  }
  const latestPeriod = allPeriods[allPeriods.length - 1];

  const periods = [];
  for (let cursor = floor; cursor <= latestPeriod; cursor = nextPeriod(cursor)) {
    periods.push(cursor);
  }

  const monthsByYear = {};
  for (const p of periods) {
    const year = Number(p.slice(0, 4));
    (monthsByYear[year] ||= []).push(Number(p.slice(5, 7)));
  }
  for (const year of Object.keys(monthsByYear)) {
    monthsByYear[year] = Array.from(new Set(monthsByYear[year])).sort((a, b) => a - b);
  }
  return {
    years: Object.keys(monthsByYear).map(Number).sort((a, b) => a - b),
    monthsByYear,
    latest: periods.length ? periods[periods.length - 1] : null,
  };
}

export function overviewCards(series, sources, period) {
  const byCode = new Map(sources.map(s => [s.code, s]));
  return SOURCE_ORDER.filter(code => byCode.has(code)).map(code => {
    const meta = byCode.get(code);
    const totals = series.filter(r => r.source === code && r.breakdown === 'total');
    const here = totals.find(r => r.period === period) || null;
    const newest = totals.slice().sort((a, b) => a.period.localeCompare(b.period)).pop() || null;
    const base = {
      code,
      name_ko: meta.name_ko,
      headline_ko: meta.headline_ko,
      coverage: meta.coverage,
      caveat: meta.caveat,
      boardUrl: meta.board_url,
      kosisUrl: meta.kosis_url || null,
    };
    if (here) {
      // 레코드가 있다고 곧 'value' 가 아니다. yoy 가 null 이면 noDelta 다 —
      // 그 판정은 cellState 한 곳에서만 한다. 여기서 state:'value' 로 못박으면
      // 화면이 fmtDelta(null) 을 `0.0만명` 증가로 그려 없는 숫자를 지어낸다
      // (실제 사례: 사업체노동력조사 2024-01~12 의 total).
      const { state, yoy } = cellState(here, true);
      // 첨부는 수집한 회차(=최신월)의 파일이다. 과거 달을 보면서 그 버튼을 누르면
      // 엉뚱한 달의 문서가 내려온다 — 그 달의 것일 때만 내보낸다. 월별 첨부는
      // 게시판 목록에서 달마다 게시글을 찾아와야 생긴다(아직 없다).
      const isLatest = !!newest && newest.period === here.period;
      return {
        ...base, period, state, value: here.value, yoy, status: here.status,
        releasedAt: here.released_at, releaseUrl: here.release_url,
        attachments: isLatest ? (here.attachments || []) : [], fallback: null,
      };
    }
    return {
      ...base, period, state: 'unpublished', value: null, yoy: null, status: null,
      releasedAt: null, releaseUrl: meta.board_url, attachments: [],
      // 폴백 줄도 같은 판정을 탄다 — 최근 발표월의 yoy 가 null 인데 fmtDelta 로
      // 그리면 카드가 또 없는 숫자를 지어낸다.
      fallback: newest && {
        period: newest.period, value: newest.value, yoy: newest.yoy,
        state: cellState(newest, true).state,
        releasedAt: newest.released_at, releaseUrl: newest.release_url,
      },
    };
  });
}

export function segmentsOf(industries, segments) {
  return [
    { breakdown: 'industry', name_ko: '산업별', categories: industries },
    ...segments,
  ];
}

// 좁은 표 머리에 들어갈 이름. 산업 대분류의 정식명은 "보건업 및 사회복지 서비스업"
// 처럼 길어서 휴대폰 매트릭스에서 한 글자씩 세로로 접힌다 — 행 하나가 화면을 다
// 먹는다. 약칭은 데이터가 갖고(industries.json·sources.json 의 short_ko), 없을 때
// 정식명으로 떨어지는 규칙만 여기 한 곳에 둔다. 성·연령 분류는 애초에 짧아서
// short_ko 가 없고 이 폴백을 탄다.
export function shortOf(meta) {
  if (!meta) return '';
  return meta.short_ko || meta.name_ko || '';
}

// 네 상태의 표기. 판정(cellState)과 문구를 한곳에 둬야 화면마다 말이 갈라지지
// 않는다 — 예전에는 chart.js 와 breakdown.js 가 각자 갖고 있다가 `미발표` 와
// `― 미발표` 로 어긋났다. 매트릭스 칸은 좁으므로 문구만 쓰고, 막대·시트·펼침
// 목록처럼 "자리를 지킨다"는 뜻이 필요한 곳은 emptyLabel() 로 `― ` 를 붙인다.
export const EMPTY_LABEL = {
  notProvided: '미제공',
  unpublished: '미발표',
  noDelta: '증감없음',
};

export function emptyLabel(state) {
  const text = EMPTY_LABEL[state];
  return text ? `― ${text}` : '―';
}

// 없는 이유가 다른 것도 정보다. 미제공이면 발표 여부를 따질 이유가 없으므로
// 이 판정 순서를 지킨다. 이 함수 밖에서 상태를 다시 판정하지 않는다.
function cellState(record, provided) {
  if (provided === false) return { state: 'notProvided', yoy: null };
  if (!record) return { state: 'unpublished', yoy: null };
  if (record.yoy === null || record.yoy === undefined) return { state: 'noDelta', yoy: null };
  return { state: 'value', yoy: record.yoy };
}

export function breakdownMatrix(series, categories, period, { sort = 'delta', breakdown } = {}) {
  const byKey = new Map();
  for (const r of series) {
    if (r.period !== period) continue;
    byKey.set(`${r.source}|${r.breakdown}|${r.category}`, r);
  }
  const rows = categories.map(category => {
    const cells = {};
    for (const source of SOURCE_ORDER) {
      const record = byKey.get(`${source}|${breakdown}|${category.code}`);
      cells[source] = cellState(record, category.provided ? category.provided[source] : true);
    }
    return {
      code: category.code, name_ko: category.name_ko,
      short_ko: category.short_ko, cells,
    };
  });

  if (sort === 'code') return rows;

  const magnitude = row => {
    const values = SOURCE_ORDER
      .map(s => row.cells[s].yoy)
      .filter(v => v !== null);
    return values.length ? Math.max(...values.map(Math.abs)) : -1;
  };
  return rows.slice().sort((a, b) => magnitude(b) - magnitude(a));
}

// 매트릭스 첫 줄에 고정되는 전체 증감. 분류별 숫자는 전체가 얼마나 움직였는지를
// 알아야 크기를 가늠할 수 있다 — 제조업 -6.8만명 이 큰 수인지 작은 수인지는
// 전체가 +10.8만명 이라는 걸 알아야 판단된다. 정렬은 이 줄을 건드리지 않는다:
// 기준선이 순서에 따라 자리를 옮기면 기준선이 아니다.
export function totalRow(series, period) {
  const cells = {};
  for (const source of SOURCE_ORDER) {
    const record = series.find(r => r.source === source
      && r.period === period && r.breakdown === 'total');
    cells[source] = cellState(record, true);
  }
  return { code: null, name_ko: '전체', short_ko: '전체', cells };
}

export function categoryTimeline(series, { breakdown, category, months = 24 } = {}) {
  const out = {};
  for (const source of SOURCE_ORDER) {
    const points = series
      .filter(r => r.source === source
        && r.breakdown === (breakdown || 'total')
        && (r.category ?? null) === (category ?? null))
      .sort((a, b) => a.period.localeCompare(b.period))
      .map(r => ({ period: r.period, value: r.value, yoy: r.yoy }));
    out[source] = points.slice(-months);
  }
  return out;
}

// 시계열은 선택월과 무관하게 항상 최신월까지 그린다. 선택월 수치와 그 이후
// 흐름이 한 화면에 같이 와야 하기 때문이다(스펙 7.6).
export function sheetData(series, {
  period, breakdown = null, category = null, categories = null, months = 24,
} = {}) {
  const meta = categories && categories.find(c => c.code === category);
  const snapshot = SOURCE_ORDER.map(source => {
    const record = series.find(r => r.source === source && r.period === period
      && r.breakdown === (breakdown || 'total')
      && (r.category ?? null) === (category ?? null));
    const provided = meta && meta.provided ? meta.provided[source] : true;
    const cell = cellState(record, provided);
    // 수준도 같이 나른다. `표로 보기` 는 #1baf7a 대비 미달에 대한 의무 완화
    // 조치인데(스펙 7.6) 증감만 있으면 대체 뷰가 원본보다 빈약해진다.
    const value = record && cell.state !== 'notProvided' ? record.value : null;
    return { source, value, ...cell };
  });
  const timeline = categoryTimeline(series, { breakdown, category, months });
  const all = Object.values(timeline).flat().map(p => p.period).sort();
  return { snapshot, timeline, latest: all.length ? all[all.length - 1] : period };
}
