import { test } from 'node:test';
import assert from 'node:assert/strict';
import { homeRows, headHtml, bodyHtml } from '../../app/js/screens/home.js';
import { topicChips, reportsForTopic } from '../../app/js/screens/topics.js';
import { shelf } from '../../app/js/screens/orgs.js';
import { detailModel } from '../../app/js/screens/report.js';

const BOARDS = [{ id: 'b1', series: '연구보고서', collapse: true }];
const CTX = {
  boards: BOARDS,
  reports: [
    { id: 'a', org: 'kli', board: 'b1', series: '연구보고서', title: '청년고용 연구',
      published: '2026-01-05', date_precision: 'day', authors: [], matched: ['청년고용'] },
    { id: 'b', org: 'kdi', board: 'b1', series: '연구보고서', title: '수출 동향',
      published: '2025-06-30', date_precision: 'month', authors: [], matched: [] },
  ],
  abstracts: {},
};

// ── 홈 ────────────────────────────────────────────────────────────────

test('검색어가 없으면 타임라인이다', () => {
  const rows = homeRows({ q: '', orgs: [], years: [] }, CTX);
  assert.equal(rows.mode, 'timeline');
  assert.ok(rows.groups.length >= 1);
});

test('검색어를 치면 결과로 바뀐다', () => {
  const rows = homeRows({ q: '청년고용', orgs: [], years: [] }, CTX);
  assert.equal(rows.mode, 'search');
  assert.deepEqual(rows.hits.map((h) => h.report.id), ['a']);
});

test('검색어를 지우면 타임라인으로 돌아온다', () => {
  assert.equal(homeRows({ q: '  ', orgs: [], years: [] }, CTX).mode, 'timeline');
});

test('기관 칩이 타임라인에 걸린다', () => {
  const rows = homeRows({ q: '', orgs: ['kdi'], years: [] }, CTX);
  const ids = rows.groups.flatMap((g) => g.rows).map((r) => r.report && r.report.id);
  assert.ok(!ids.includes('a'));
  assert.ok(ids.includes('b'));
});

test('기관 칩이 검색 결과에도 똑같이 걸린다', () => {
  const rows = homeRows({ q: '청년고용', orgs: ['kdi'], years: [] }, CTX);
  assert.deepEqual(rows.hits, []);
});

test('연도 칩도 양쪽에 걸린다', () => {
  assert.equal(homeRows({ q: '', orgs: [], years: [2025] }, CTX)
    .groups.flatMap((g) => g.rows).length, 1);
});

// ── 홈: 한글 입력이 깨지지 않게 하는 경계 ─────────────────────────────

test('머리는 검색어가 바뀌어도 그대로다', () => {
  // 이 불변식이 곧 '입력창 DOM 이 살아남는다' 이다. 머리가 검색어를 읽기
  // 시작하면 타이핑마다 머리를 다시 그려야 하고, 그러면 한글 조합이 끊겨
  // '사무직' 이 'ㅅㅏㅁㅜㅈㅣㄱ' 으로 들어간다.
  const a = headHtml({ q: '', orgs: [], years: [] }, CTX);
  const b = headHtml({ q: '청년', orgs: [], years: [] }, CTX);
  assert.equal(a, b);
});

test('머리에 검색어 값을 박아 넣지 않는다', () => {
  // value="..." 로 박으면 머리를 다시 그려야만 글자가 보인다.
  const html = headHtml({ q: '청년', orgs: [], years: [] }, CTX);
  assert.ok(!html.includes('청년'));
  assert.ok(html.includes('id="q"'));
});

test('본문은 검색어를 따라 바뀐다', () => {
  const timeline = bodyHtml({ q: '', orgs: [], years: [] }, CTX);
  const search = bodyHtml({ q: '청년고용', orgs: [], years: [] }, CTX);
  assert.notEqual(timeline, search);
  assert.ok(search.includes('관련도순'));
});

test('머리는 기관·연도 칩 상태는 반영한다', () => {
  // 칩은 눌린 표시를 클래스로 바꾸므로 머리를 다시 그리지 않는다. 다만 첫
  // 그림에서는 상태가 맞아야 한다.
  const on = headHtml({ q: '', orgs: ['kli'], years: [] }, CTX);
  assert.ok(on.includes('chip--active'));
});

// ── 주제 ──────────────────────────────────────────────────────────────

const TOPIC_ROWS = [
  { id: 'a', org: 'kli', matched: ['청년고용', '임금'], published: '2026-01-01' },
  { id: 'b', org: 'kdi', matched: ['청년고용'], published: '2025-01-01' },
  { id: 'c', org: 'kiet', matched: [], published: '2025-01-01' },
];

test('주제 칩은 matched 에서 나오고 건수순이다', () => {
  assert.deepEqual(topicChips(TOPIC_ROWS),
    [{ topic: '청년고용', count: 2 }, { topic: '임금', count: 1 }]);
});

test('주제 칩은 네 기관을 덮는다', () => {
  // KLI 에도 matched 가 있어야 이게 성립한다 — 매칭과 판정을 나눈 이유.
  const orgs = new Set(reportsForTopic(TOPIC_ROWS, '청년고용').map((r) => r.org));
  assert.deepEqual([...orgs].sort(), ['kdi', 'kli']);
});

test('주제 목록은 최신순이다', () => {
  assert.deepEqual(reportsForTopic(TOPIC_ROWS, '청년고용').map((r) => r.id), ['a', 'b']);
});

// ── 기관 ──────────────────────────────────────────────────────────────

const ORGS = [{ code: 'kli', name: '한국노동연구원' }, { code: 'kdi', name: '한국개발연구원' }];
const SHELF_ROWS = [
  { id: 'a', org: 'kli', series: '연구보고서', published: '2026-01-01' },
  { id: 'b', org: 'kli', series: '연구보고서', published: '2025-01-01' },
  { id: 'c', org: 'kli', series: '노동리뷰', published: '2025-01-01' },
];

test('기관별 시리즈 건수를 센다', () => {
  const kli = shelf(SHELF_ROWS, ORGS).find((x) => x.org === 'kli');
  assert.equal(kli.total, 3);
  assert.deepEqual(kli.series,
    [{ series: '연구보고서', count: 2 }, { series: '노동리뷰', count: 1 }]);
});

test('한 건도 없는 기관은 0으로 남는다', () => {
  // 수집이 아직 안 닿은 기관을 숨기면 왜 없는지 알 수 없다.
  assert.equal(shelf(SHELF_ROWS, ORGS).find((x) => x.org === 'kdi').total, 0);
});

// ── 상세 ──────────────────────────────────────────────────────────────

const DETAIL_CTX = {
  reports: [{
    id: 'kli-1', org: 'kli', series: '연구보고서', title: '청년고용 연구',
    authors: ['홍길동'], published: '2025-12-31', date_precision: 'month',
    pages: 214, matched: ['청년고용'],
    landing_url: 'https://www.kli.re.kr/kli/x', file_url: 'https://www.kli.re.kr/f.pdf',
  }],
  abstracts: { 'kli-1': { abstract: '초록이다', toc: ['제1장 서론'] } },
};

test('두 링크를 다 준다', () => {
  assert.deepEqual(detailModel('kli-1', DETAIL_CTX).links.map((l) => l.label),
    ['원문 PDF 열기', '기관 페이지 열기']);
});

test('원문이 없으면 기관 페이지만 준다', () => {
  const ctx = { ...DETAIL_CTX, reports: [{ ...DETAIL_CTX.reports[0], file_url: null }] };
  assert.deepEqual(detailModel('kli-1', ctx).links.map((l) => l.label), ['기관 페이지 열기']);
});

test('링크는 기관 서버를 가리킨다 — 원문을 재배포하지 않는다', () => {
  for (const l of detailModel('kli-1', DETAIL_CTX).links) {
    assert.ok(l.href.startsWith('https://www.kli.re.kr/'));
  }
});

test('초록을 아직 안 받았으면 빈 문자열이지 오류가 아니다', () => {
  const m = detailModel('kli-1', { ...DETAIL_CTX, abstracts: null });
  assert.equal(m.abstract, '');
  assert.deepEqual(m.toc, []);
});

test('없는 id 는 null 이다', () => {
  assert.equal(detailModel('없다', DETAIL_CTX), null);
});
