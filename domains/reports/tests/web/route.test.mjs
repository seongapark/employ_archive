import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRoute } from '../../app/js/route.js';

test('홈', () => {
  assert.deepEqual(parseRoute(''), { name: 'home', params: [], tab: 'home' });
  assert.deepEqual(parseRoute('#/'), { name: 'home', params: [], tab: 'home' });
});

test('한글 주제가 디코드되어 온다', () => {
  // 이게 안 되면 화면에 '%EC%B2%AD...' 가 뜨고 목록이 0건이 된다.
  const r = parseRoute('#/topics/' + encodeURIComponent('청년고용'));
  assert.equal(r.name, 'topics');
  assert.deepEqual(r.params, ['청년고용']);
});

test('기관·시리즈 두 조각이 각각 디코드된다', () => {
  const r = parseRoute(`#/orgs/kli/${encodeURIComponent('연구보고서')}`);
  assert.equal(r.name, 'orgs');
  assert.deepEqual(r.params, ['kli', '연구보고서']);
});

test('이름에 슬래시가 있어도 세그먼트가 늘지 않는다', () => {
  // 나누기 전에 디코드하면 %2F 가 진짜 '/' 가 되어 조각이 하나 더 생긴다.
  const r = parseRoute(`#/orgs/kli/${encodeURIComponent('가/나')}`);
  assert.deepEqual(r.params, ['kli', '가/나']);
});

test('보고서 상세도 같은 규칙을 쓴다', () => {
  assert.deepEqual(parseRoute('#/r/kli-10299'),
    { name: 'report', params: ['kli-10299'], tab: null });
});

test('탭 표시는 라우트를 따른다', () => {
  assert.equal(parseRoute('#/topics').tab, 'topics');
  assert.equal(parseRoute('#/orgs').tab, 'orgs');
  assert.equal(parseRoute('#/r/kli-1').tab, null, '상세는 어느 탭도 켜지 않는다');
});

test('모르는 주소는 홈으로 떨어진다', () => {
  assert.equal(parseRoute('#/없는화면/x').name, 'home');
});

test('손상된 퍼센트 인코딩이 화면을 죽이지 않는다', () => {
  assert.deepEqual(parseRoute('#/topics/%E0%A4%A').params, ['%E0%A4%A']);
});
