// 렌더 순수 함수 테스트. DOM 없이 돈다 — badge.js 는 문자열/객체만 다룬다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  badgeLabel, understandLine, evidenceColumns, isSampleErrorText,
} from '../../app/js/badge.js';

const 배지코드8종 = [
  '저확신', '검증실패', '한도초과', '할당량확인불가', '반증미설계',
  '데이터미보유', '근거 미확인', '유의성: 불명',
];

test('배지는 색만이 아니라 텍스트 라벨을 갖는다', () => {
  // 공공 사이트라 색만으로 구분되면 안 된다
  for (const c of 배지코드8종) {
    const b = badgeLabel(c);
    assert.ok(b.라벨 && b.라벨.length > 0, c);
    assert.ok(b.색, c);
  }
});

test('배지 8종이 서로 다른 라벨을 갖는다', () => {
  const 라벨들 = 배지코드8종.map((c) => badgeLabel(c).라벨);
  assert.equal(new Set(라벨들).size, 배지코드8종.length);
});

test('반증미설계와 데이터미보유는 다른 라벨이다', () => {
  // 사용자가 할 수 있는 일이 다르다 — 앞은 카탈로그, 뒤는 수집기
  assert.notEqual(badgeLabel('반증미설계').라벨, badgeLabel('데이터미보유').라벨);
  assert.match(badgeLabel('데이터미보유').라벨, /수집/);
  assert.doesNotMatch(badgeLabel('반증미설계').라벨, /수집/);
});

test('한도초과와 할당량확인불가는 다른 라벨이다 — 사용자가 할 수 있는 일이 다르다', () => {
  // 한도는 내일 다시, 장애는 잠시 뒤 다시 — 같은 문구면 안 된다
  assert.notEqual(badgeLabel('한도초과').라벨, badgeLabel('할당량확인불가').라벨);
});

test('모르는 배지 코드가 와도 죽지 않고 코드 자체를 라벨로 쓴다', () => {
  const b = badgeLabel('미래에추가될배지');
  assert.equal(b.라벨, '미래에추가될배지');
  assert.ok(b.색);
});

test('이해 카드는 평시 한 줄이다', () => {
  assert.equal(understandLine('원인탐색'), '원인탐색으로 이해함 · 수정');
});

test('이해 카드 문구는 유형마다 다르다', () => {
  assert.notEqual(understandLine('수치조회'), understandLine('전망'));
});

test('지지와 반증을 좌우 두 열로 가른다', () => {
  const c = evidenceColumns({ 지지: [{ 지표: 'A' }], 반증: [] });
  assert.equal(c.지지.length, 1);
  assert.deepEqual(c.반증, []);
  assert.equal(c.반증비었음, true); // 숨기지 않고 비었다고 그린다
  assert.equal(c.지지비었음, false);
});

test('지지도 반증도 없으면 둘 다 비었다고 그린다', () => {
  const c = evidenceColumns({});
  assert.equal(c.지지비었음, true);
  assert.equal(c.반증비었음, true);
  assert.deepEqual(c.지지, []);
  assert.deepEqual(c.반증, []);
});

test('가설 자체가 없어도 죽지 않는다', () => {
  const c = evidenceColumns(undefined);
  assert.equal(c.지지비었음, true);
  assert.equal(c.반증비었음, true);
});

// 규칙 3: RSE 는 표본오차이지 관측값이 아니다 — 근거 표와 같은 자리에 그리면 안 된다.
// 렌더 쪽에서 이 판정을 쓸 수 있도록 순수 함수로 노출한다.
test('유의성사유 문자열은 RSE(표본오차) 문구로 식별된다', () => {
  assert.equal(isSampleErrorText('RSE 12.3%'), true);
  assert.equal(isSampleErrorText('RSE 미보유'), true);
  assert.equal(isSampleErrorText('RSE 미공표(*)'), true);
});

test('RSE 로 시작하지 않는 문구는 표본오차 문구로 식별하지 않는다', () => {
  assert.equal(isSampleErrorText('선후관계는 검정하지 않음'), false);
  assert.equal(isSampleErrorText(''), false);
  assert.equal(isSampleErrorText(null), false);
  assert.equal(isSampleErrorText(undefined), false);
});
