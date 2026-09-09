import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchReports, sortByDate, squash } from '../../app/js/search.js';

const R = (id, title, authors = [], published = '2025-01-01') =>
  ({ id, title, authors, org: 'kli', published });

test('공백을 무시하고 부분일치한다', () => {
  assert.equal(squash('청년 고용'), '청년고용');
  assert.equal(searchReports('청년고용', [R('a', '청년 고용 실태 연구')], {}).length, 1);
  assert.equal(searchReports('청년 고용', [R('a', '청년고용 실태 연구')], {}).length, 1);
});

test('제목이 초록보다 위로 온다', () => {
  const reports = [R('a', '산업구조 연구'), R('b', '청년고용 연구')];
  const abstracts = { a: { abstract: '청년고용을 다룬다.', toc: [] }, b: { abstract: '', toc: [] } };
  const hits = searchReports('청년고용', reports, abstracts);
  assert.equal(hits[0].report.id, 'b');
});

test('저자로도 찾는다', () => {
  const hits = searchReports('홍길동', [R('a', '제목', ['홍길동'])], {});
  assert.equal(hits.length, 1);
  assert.equal(hits[0].hit.where, 'authors');
});

test('초록에서 걸리면 그 문장을 잘라 준다', () => {
  const abstracts = { a: { abstract: '앞 문장이다. 청년고용 격차가 커졌다. 뒷 문장이다.', toc: [] } };
  const hits = searchReports('청년고용', [R('a', '무관한 제목')], abstracts);
  assert.equal(hits[0].hit.where, 'abstract');
  assert.ok(hits[0].hit.snippet.includes('청년고용 격차'));
});

test('초록이 없으면 목차에서 걸리고 그 줄을 준다', () => {
  const abstracts = { a: { abstract: '', toc: ['제1장 서론', '제2장 청년고용의 추이'] } };
  const hits = searchReports('청년고용', [R('a', '무관한 제목')], abstracts);
  assert.equal(hits[0].hit.where, 'toc');
  assert.equal(hits[0].hit.snippet, '제2장 청년고용의 추이');
});

test('제목에서만 걸리면 스니펫이 없다', () => {
  const hits = searchReports('청년고용', [R('a', '청년고용 연구')], {});
  assert.equal(hits[0].hit.where, 'title');
  assert.equal(hits[0].hit.snippet, '');
});

test('초록을 아직 안 받았어도 제목 검색은 된다', () => {
  // abstracts 는 검색창 포커스 시점에 온다. 그 전에도 결과가 나와야 한다.
  const hits = searchReports('청년고용', [R('a', '청년고용 연구')], null);
  assert.equal(hits.length, 1);
});

test('빈 질의는 아무것도 주지 않는다', () => {
  assert.deepEqual(searchReports('   ', [R('a', '제목')], {}), []);
  assert.deepEqual(searchReports('', [R('a', '제목')], {}), []);
});

test('안 걸리면 결과에 없다', () => {
  assert.deepEqual(searchReports('반도체', [R('a', '청년고용')], {}), []);
});

test('최신순 토글은 관련도를 무시하고 날짜로만 세운다', () => {
  const reports = [R('a', '청년고용 옛것', [], '2022-01-01'),
                   R('b', '청년고용 새것', [], '2026-01-01')];
  const hits = sortByDate(searchReports('청년고용', reports, {}));
  assert.deepEqual(hits.map((h) => h.report.id), ['b', 'a']);
});
