import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderSummaryCard, renderRow } from '../../app/js/screens/org.js';

const ORGS = [
  { org: 'OECD', name_ko: 'OECD', short_ko: 'OECD', method: 'api', track: 'A' },
  { org: 'KEIS', name_ko: '한국고용정보원', short_ko: '고용정보원', method: 'ocr', track: 'B' },
];

const RATIONALES = [{
  org: 'OECD', published_at: '2026-08-29', indicator: 'gdp_growth',
  text: '내수 개선세가 파급되면서 성장세가 완만해질 전망이다.', tags: ['내수'],
}];

function rec(over = {}) {
  return {
    id: 'oecd-2026-08-gdp_growth-2027', org: 'OECD', org_name_ko: 'OECD',
    report_title: 'Economic Outlook 119', published_at: '2026-08-29',
    target_year: 2027, target_period: 'annual', indicator: 'gdp_growth',
    value: 1.9, unit: '%', prev_value: null, revision: null,
    rationale: '', rationale_tags: [], source_url: 'https://x/a',
    source_page: null, landing_url: 'https://x', confidence: 'verified',
    collected_at: '2026-08-29T16:00:00+09:00', ...over,
  };
}

// 수집 상태는 어느 화면에도 싣지 않기로 했다(2026-09-10 사용자 결정).
// OCR 기관이라도 '확인필요'가 붙지 않아야 한다 — 붙는 순간 그 결정이 조용히 뒤집힌다.
test('요약카드는 OCR 기관이라도 확인필요를 달지 않는다', () => {
  const ctx = { orgs: ORGS };
  const records = [rec({
    org: 'KEIS', org_name_ko: '한국고용정보원', indicator: 'emp_change',
    value: 14.6, unit: '만명', target_year: 2026,
  })];
  const html = renderSummaryCard(ctx, 'KEIS', ['emp_change'], 2026, records);
  assert.equal(html.includes('확인필요'), false);
  assert.equal(html.includes('badge'), false);
});

test('요약카드 격자는 좁아지면 1열로 떨어진다(고정 2열이 아니다)', () => {
  const ctx = { orgs: ORGS };
  const records = [rec({ target_year: 2027 })];
  const html = renderSummaryCard(ctx, 'OECD', ['gdp_growth'], 2027, records);
  assert.ok(html.includes('auto-fit'));
  // 지표명·수치가 중간에서 쪼개지지 않아야 한다
  assert.ok(html.includes('white-space:nowrap'));
});

test('접힌 행에는 전망치와 증감만 있고 근거 문장은 없다', () => {
  const r = rec();
  const html = renderRow(r, false, [r], RATIONALES);
  assert.ok(html.includes('1.9%'));
  assert.ok(html.includes('08.29'));
  assert.equal(html.includes('내수 개선세'), false);
  // 보고서 제목도 근거 자리에 대신 들어오면 안 된다(예전 폴백 경로)
  assert.equal(html.includes('Economic Outlook 119'), false);
});

test('펼친 행에서 근거 문장이 나온다', () => {
  const r = rec();
  const html = renderRow(r, true, [r], RATIONALES);
  assert.ok(html.includes('내수 개선세'));
  assert.ok(html.includes('원문 보기'));
});

test('펼친 행에도 수집 상태 배지는 없다', () => {
  const r = rec({ org: 'KEIS', org_name_ko: '한국고용정보원', indicator: 'emp_change', value: 14.6, unit: '만명' });
  const html = renderRow(r, true, [r], RATIONALES);
  assert.equal(html.includes('확인필요'), false);
  assert.equal(html.includes('badge--'), false);
  assert.equal(html.includes('검증'), false);
});

// 근거가 없으면 근거 문단을 그리지 않는다. 보고서 제목으로 떨어지면
// 바로 아래 '원문 보기' 줄이 같은 제목을 또 적어 펼친 칸이 중복으로 찬다.
test('근거가 없는 회차는 보고서 제목을 근거 자리에 대신 넣지 않는다', () => {
  const r = rec({ published_at: '2026-05-13' });
  const html = renderRow(r, true, [r], RATIONALES);
  // 제목은 '원문 보기' 줄에 한 번만 나온다
  assert.equal(html.split('Economic Outlook 119').length - 1, 1);
  assert.ok(html.includes('원문 보기'));
});
