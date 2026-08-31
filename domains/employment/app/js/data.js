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

function nextPeriod(period) {
  let year = Number(period.slice(0, 4));
  let month = Number(period.slice(5, 7)) + 1;
  if (month > 12) { month = 1; year += 1; }
  return `${year}-${String(month).padStart(2, '0')}`;
}

// 기준월 하한은 세 출처의 total 이 모두 있는 첫 달이다. 단면으로 재면
// 성·연령에는 사업체노동력조사가 아예 없어 하한이 단면마다 달라진다.
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
    };
    if (here) {
      return {
        ...base, state: 'value', value: here.value, yoy: here.yoy, status: here.status,
        releasedAt: here.released_at, releaseUrl: here.release_url,
        attachments: here.attachments || [], fallback: null,
      };
    }
    return {
      ...base, state: 'unpublished', value: null, yoy: null, status: null,
      releasedAt: null, releaseUrl: meta.board_url, attachments: [],
      fallback: newest && {
        period: newest.period, value: newest.value, yoy: newest.yoy,
        releasedAt: newest.released_at, releaseUrl: newest.release_url,
      },
    };
  });
}
