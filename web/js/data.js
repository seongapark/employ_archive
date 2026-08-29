const INDICATOR_ORDER = ['emp_change', 'unemp_rate', 'gdp_growth', 'cpi', 'emp_rate', 'emp_rate_youth', 'labor_force'];
const INTL_ORGS = new Set(['IMF', 'OECD', 'ADB']);

// 화면 전반(홈 필/기관 요약카드·필/타임라인 요약줄)에서 공유하는 지표 축약 라벨.
// 각 화면이 자체적으로 라벨 테이블을 두면 표기가 어긋나므로 여기 한 곳에서만 관리한다.
export const SHORT_LABELS = {
  emp_change: '취업자',
  emp_rate: '고용률',
  unemp_rate: '실업률',
  gdp_growth: '성장률',
  cpi: '물가',
  emp_rate_youth: '청년고용률',
  labor_force: '경활률',
};

function dayDiff(dateStrA, dateStrB) {
  const msA = Date.parse(dateStrA + 'T00:00:00Z');
  const msB = Date.parse(dateStrB + 'T00:00:00Z');
  return (msA - msB) / (24 * 60 * 60 * 1000);
}

function isAnnual(r) {
  return (r.target_period ?? 'annual') === 'annual';
}

// 같은 org의 레코드들 중 (Map 삽입 순서와 무관하게) published_at 최대값 하나만 남긴다.
// latestRecords/compareSet이 같은 규칙을 공유해야 회차가 늘어도 기관당 1건으로 축약된다.
function reduceLatestPerOrg(records) {
  const latest = new Map();
  for (const r of records) {
    const existing = latest.get(r.org);
    if (!existing || r.published_at > existing.published_at) {
      latest.set(r.org, r);
    }
  }
  return latest;
}

export function latestRecords(records, { indicator, targetYear }) {
  const filtered = records.filter(r => r.indicator === indicator && r.target_year === targetYear && isAnnual(r));
  const latest = reduceLatestPerOrg(filtered);

  return Array.from(latest.values()).sort((a, b) => b.published_at.localeCompare(a.published_at));
}

export function summarize(latest) {
  if (latest.length === 0) return null;

  const values = latest.map(r => r.value);
  const sum = values.reduce((a, b) => a + b, 0);
  const avg = Math.round((sum / latest.length) * 10) / 10;

  let max = latest[0];
  let min = latest[0];
  for (const r of latest) {
    if (r.value > max.value) max = r;
    if (r.value < min.value) min = r;
  }

  return {
    count: latest.length,
    avg,
    max,
    min,
  };
}

export function seriesFor(records, { org, indicator, targetYear }) {
  return records
    .filter(r => r.org === org && r.indicator === indicator && r.target_year === targetYear && isAnnual(r))
    .sort((a, b) => a.published_at.localeCompare(b.published_at));
}

export function orgIndicators(records, org) {
  const indicators = new Set();
  for (const r of records) {
    if (r.org === org) {
      indicators.add(r.indicator);
    }
  }

  return INDICATOR_ORDER.filter(ind => indicators.has(ind));
}

export function compareSet(records, { indicator, targetYear, today, orgsMeta, filter }) {
  const filtered = records.filter(r => r.indicator === indicator && r.target_year === targetYear && isAnnual(r));

  // 기관당 최신 회차 1건으로 축약 (같은 org에 개정판이 여러 건 쌓여도 중복 표시/집계되지 않도록)
  const latestPerOrg = Array.from(reduceLatestPerOrg(filtered).values());

  // Apply org filter
  let filtered2 = latestPerOrg;
  if (filter === 'domestic') {
    filtered2 = latestPerOrg.filter(r => !INTL_ORGS.has(r.org));
  } else if (filter === 'intl') {
    filtered2 = latestPerOrg.filter(r => INTL_ORGS.has(r.org));
  }

  // Map to result format and sort by value desc
  const result = filtered2.map(rec => {
    const daysSince = dayDiff(today, rec.published_at);
    const stale = daysSince > 90;
    const [year, month, day] = rec.published_at.split('-');
    const monthLabel = `${month}.${day}`;

    return { rec, stale, monthLabel };
  }).sort((a, b) => b.rec.value - a.rec.value);

  return result;
}

export function timelineGroups(records) {
  const annualRecords = records.filter(isAnnual);

  // Group by month
  const monthMap = new Map();
  for (const r of annualRecords) {
    const month = r.published_at.substring(0, 7).replace('-', '.');
    if (!monthMap.has(month)) {
      monthMap.set(month, []);
    }
    monthMap.get(month).push(r);
  }

  // Sort months desc (newest first)
  const months = Array.from(monthMap.keys()).sort().reverse();

  const groups = [];
  for (const month of months) {
    const monthRecords = monthMap.get(month);

    // Group by (org, published_at)
    const eventMap = new Map();
    for (const r of monthRecords) {
      const key = `${r.org}|${r.published_at}`;
      if (!eventMap.has(key)) {
        eventMap.set(key, {
          org: r.org,
          org_name_ko: r.org_name_ko,
          published_at: r.published_at,
          report_title: r.report_title,
          items: [],
        });
      }
      eventMap.get(key).items.push(r);
    }

    const events = Array.from(eventMap.values())
      .sort((a, b) => b.published_at.localeCompare(a.published_at));

    // Sort items in each event by INDICATOR_ORDER
    for (const event of events) {
      event.items.sort((a, b) => {
        const aIdx = INDICATOR_ORDER.indexOf(a.indicator);
        const bIdx = INDICATOR_ORDER.indexOf(b.indicator);
        return (aIdx >= 0 ? aIdx : Infinity) - (bIdx >= 0 ? bIdx : Infinity);
      });
    }

    groups.push({ month, events });
  }

  return groups;
}

export function fmtValue(rec) {
  const suffix = rec.unit || '%';
  return `${rec.value}${suffix}`;
}

export function fmtDelta(rec) {
  if (rec.revision === null || rec.revision === undefined || rec.revision === 0) {
    return { dir: 'flat', text: '—' };
  }

  const isPositive = rec.revision > 0;
  const dir = isPositive ? 'up' : 'down';

  const suffix = rec.unit === '만명' ? '만명' : '%p';
  const absRevision = Math.abs(rec.revision);
  const sign = isPositive ? '+' : '-';
  const text = `${sign}${absRevision}${suffix}`;

  return { dir, text };
}

export function dateLabel(rec, orgsMeta) {
  const orgMeta = orgsMeta.find(o => o.org === rec.org);
  const isApi = orgMeta && orgMeta.method === 'api';

  const [year, month, day] = rec.published_at.split('-');
  const label = `${year}.${month}.${day}`;

  if (isApi) {
    return `${label} 수집`;
  } else {
    return `${label} 발표`;
  }
}

export function isNew(rec, today) {
  const daysSince = dayDiff(today, rec.published_at);
  return daysSince <= 7;
}

export function esc(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
