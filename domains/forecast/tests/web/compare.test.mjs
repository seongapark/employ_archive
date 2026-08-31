import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTableText } from '../../app/js/screens/compare.js';

const ORGS = [
  { org: 'OECD', name_ko: 'OECD', method: 'api', track: 'A' },
  { org: 'BOK', name_ko: '한국은행', method: 'pdf', track: 'A' },
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

test('buildTableText leaves a table with no OCR source unmarked', () => {
  const set = [
    { rec: rec({ org: 'OECD', org_name_ko: 'OECD', value: 1.9 }) },
    { rec: rec({ org: 'BOK', org_name_ko: '한국은행', published_at: '2026-08-28', value: 2.1 }) },
  ];
  const text = buildTableText(set, ORGS);
  assert.equal(text.includes('*'), false);
  assert.deepEqual(text.split('\n'), [
    '기관\t값\t발표일',
    'OECD\t1.9%\t2026.08.29 수집',
    '한국은행\t2.1%\t2026.08.28 발표',
  ]);
});

test('buildTableText marks an OCR-sourced row and appends a footnote', () => {
  const set = [
    { rec: rec({ org: 'OECD', org_name_ko: 'OECD', value: 1.9 }) },
    { rec: rec({
      org: 'KEIS', org_name_ko: '한국고용정보원', published_at: '2026-08-03',
      value: 14.6, unit: '만명', indicator: 'emp_change',
    }) },
  ];
  const text = buildTableText(set, ORGS);
  const lines = text.split('\n');
  assert.equal(lines[0], '기관\t값\t발표일');
  assert.equal(lines[1], 'OECD\t1.9%\t2026.08.29 수집');
  // OCR 출처 행만 기관명 옆에 별표가 붙는다 — 값·발표일 칸의 형식은 그대로.
  assert.equal(lines[2], '한국고용정보원*\t14.6만명\t2026.08.03 발표');
  assert.equal(lines.at(-1), '* PDF 이미지를 OCR로 읽은 수치입니다. 원문과 대조해 확인하세요.');
  assert.equal(lines.at(-2), '');
});

test('buildTableText adds only one footnote even when several rows are OCR-sourced', () => {
  const set = [
    { rec: rec({ org: 'KEIS', org_name_ko: '한국고용정보원', value: 14.6, unit: '만명' }) },
    { rec: rec({ org: 'KEIS', org_name_ko: '한국고용정보원', value: 16.2, unit: '만명', published_at: '2025-12-31' }) },
  ];
  const text = buildTableText(set, ORGS);
  const noteCount = text.split('\n').filter(line => line.startsWith('* ')).length;
  assert.equal(noteCount, 1);
});

test('buildTableText does not throw when the org list is missing an entry', () => {
  const set = [{ rec: rec({ org: 'UNKNOWN', org_name_ko: '미상 기관' }) }];
  const text = buildTableText(set, ORGS);
  assert.equal(text.includes('*'), false);
});
