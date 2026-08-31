import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderSummaryCard, renderRow } from '../../app/js/screens/org.js';

const ORGS = [
  { org: 'OECD', name_ko: 'OECD', method: 'api', track: 'A' },
  { org: 'KEIS', name_ko: '한국고용정보원', method: 'ocr', track: 'B' },
];

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

test('renderSummaryCard shows the OCR badge once for an OCR-sourced org', () => {
  const ctx = { orgs: ORGS };
  const records = [rec({
    org: 'KEIS', org_name_ko: '한국고용정보원', indicator: 'emp_change',
    value: 14.6, unit: '만명', target_year: 2026,
  })];
  const html = renderSummaryCard(ctx, 'KEIS', ['emp_change'], 2026, records);
  assert.ok(html.includes('badge--ocr'));
  assert.ok(html.includes('확인필요'));
});

test('renderSummaryCard does not show the OCR badge for a non-OCR org', () => {
  const ctx = { orgs: ORGS };
  const records = [rec()]; // org: OECD (method: api)
  const html = renderSummaryCard(ctx, 'OECD', ['gdp_growth'], 2027, records);
  assert.equal(html.includes('badge--ocr'), false);
});

test('renderRow collapsed row carries the OCR badge for an OCR-sourced record', () => {
  const r = rec({ org: 'KEIS', org_name_ko: '한국고용정보원', indicator: 'emp_change', value: 14.6, unit: '만명' });
  // isExpanded: false — 접힌 행. 회차가 둘 이상이면 이게 기본 표시 상태다.
  const html = renderRow(r, false, ORGS, [r]);
  assert.ok(html.includes('badge--ocr'));
  assert.ok(html.includes('확인필요'));
});

test('renderRow collapsed row does not carry the OCR badge for a non-OCR record', () => {
  const r = rec(); // org: OECD (method: api)
  const html = renderRow(r, false, ORGS, [r]);
  assert.equal(html.includes('badge--ocr'), false);
});
