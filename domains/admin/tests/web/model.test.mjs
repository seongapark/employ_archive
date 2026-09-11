import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 이름, 순서, 기간선택, 증감, 퍼센트 } from '../../app/js/model.js';

// 관리자 앱은 hub/js/state.js 를 끌어 쓸 수 없다 — 빌드가 도메인 폴더에 복사하는
// 것은 core/ 뿐이고, 그 목록에는 hub·ask 가 애초에 없다.
test('여섯 도메인의 한글 이름을 자기가 들고 있다', () => {
  assert.deepEqual(순서, ['employment', 'press', 'forecast', 'reports', 'ask', 'hub']);
  for (const s of 순서) assert.ok(이름[s], s);
  assert.equal(이름.employment, '고용동향');
  assert.equal(이름.hub, '허브');
});

test('기간은 넷이고 기본이 30일이다', () => {
  assert.deepEqual(기간선택.map((x) => x.days), [7, 30, 90, 0]);
  assert.equal(기간선택.find((x) => x.기본).days, 30);
});

test('증감은 방향과 라벨을 함께 준다', () => {
  assert.deepEqual(증감(120, 100), { 값: 20, 방향: 'up', 라벨: '+20%' });
  assert.deepEqual(증감(80, 100), { 값: -20, 방향: 'down', 라벨: '-20%' });
  assert.deepEqual(증감(100, 100), { 값: 0, 방향: 'flat', 라벨: '0%' });
});

// 직전이 0 이면 배수가 무한대다 — 숫자를 지어내지 않고 비교를 포기한다.
test('직전이 없거나 0 이면 비교하지 않는다', () => {
  assert.equal(증감(10, 0), null);
  assert.equal(증감(10, null), null);
});

test('퍼센트는 전체가 0 이어도 안 터진다', () => {
  assert.equal(퍼센트(25, 100), 25);
  assert.equal(퍼센트(1, 3), 33.3);
  assert.equal(퍼센트(5, 0), 0);
});
