import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseRoute } from '../../app/js/route.js';

test('the bare hash is the overview', () => {
  assert.deepEqual(parseRoute(''), { name: 'overview', segment: 'overview', params: {} });
  assert.deepEqual(parseRoute('#/'), { name: 'overview', segment: 'overview', params: {} });
});

test('breakdown routes carry the attribute and the decoded category', () => {
  assert.deepEqual(parseRoute('#/b/industry'),
    { name: 'breakdown', segment: 'breakdown', params: { breakdown: 'industry', category: null } });
  assert.deepEqual(parseRoute('#/b/age/60%2B'),
    { name: 'breakdown', segment: 'breakdown', params: { breakdown: 'age', category: '60+' } });
});

test('a release route names one source', () => {
  assert.deepEqual(parseRoute('#/r/eaps'),
    { name: 'release', segment: 'overview', params: { code: 'eaps' } });
  assert.deepEqual(parseRoute('#/r/est'),
    { name: 'release', segment: 'overview', params: { code: 'est' } });
});

test('an unknown source falls back to the overview', () => {
  // 낡은 북마크가 없어진 출처를 가리키면 빈 화면 대신 총괄로 떨어진다.
  assert.deepEqual(parseRoute('#/r/wat'),
    { name: 'overview', segment: 'overview', params: {} });
});

test('the release screen belongs to the overview segment', () => {
  // 세그먼트바는 화면 이름으로 활성 탭을 고른다. 하위 화면에서 셋 다 꺼지면
  // 사용자는 자기가 어느 탭 아래에 있는지 잃는다.
  assert.equal(parseRoute('#/r/ei').segment, 'overview');
  assert.equal(parseRoute('#/b/industry').segment, 'breakdown');
  assert.equal(parseRoute('#/sources').segment, 'sources');
});
