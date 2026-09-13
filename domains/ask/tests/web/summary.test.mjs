// 요약 재료와 검증 집합. **한 함수가 둘을 같이 내는 것이 요점**이라, 재료에 담긴
// 것과 허용 집합이 어긋나지 않는지를 여기서 못박는다.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { 요약재료 } from '../../worker/src/lookup/summary.mjs';
import { verify } from '../../worker/src/core/verify.mjs';

const 응답 = {
  질문: '최근 고용상황은?',
  슬롯: { 주제: '취업자수', 집단축: [], category: {}, 기간: { from: '', to: '' } },
  묶음: [
    {
      도메인: 'employment',
      사유: '2025-08~2026-08 추세를 본다',
      결과: [{ 제목: '2026-08 전체', 스니펫: '29151천명 (전년대비 12.3)', 링크: '', 근거유형: '관측' }],
      관측: [{ period: '2025-08', value: 28000, unit: '천명', yoy: 5.1, release_url: '' },
             { period: '2026-08', value: 29151, unit: '천명', yoy: 12.3, release_url: '' }],
      파생: { 단위: '천명', 차이: 1151, 증감률: 4.1, 기준기간: '2025-08→2026-08' },
    },
    {
      도메인: 'press',
      결과: [{ 제목: '2026-09-07 한국일보 정규', 스니펫: '취업자 증가폭 확대',
              링크: 'https://x/1', 근거유형: '기사', 날짜: '2026-09-07', 점수: 3 }],
    },
  ],
  해당없음: [],
};

test('재료는 도메인·출처·관측·파생을 담는다', () => {
  const { 재료 } = 요약재료(응답);
  assert.equal(재료.질문, '최근 고용상황은?');
  const 고용 = 재료.도메인.find((d) => d.도메인 === 'employment');
  assert.equal(고용.관측.length, 2);
  assert.equal(고용.파생.차이, 1151);
  assert.equal(재료.도메인.find((d) => d.도메인 === 'press').출처[0].종류, '기사');
});

test('점수는 재료에 넣지 않는다 — 뜻 없는 수가 허용 집합에 섞인다', () => {
  const { 재료, 허용숫자 } = 요약재료(응답);
  assert.equal(JSON.stringify(재료).includes('점수'), false);
  assert.equal(허용숫자.includes(3), false, JSON.stringify(허용숫자));
});

test('재료의 숫자를 인용한 문장은 통과한다', () => {
  const { 허용텍스트, 허용숫자 } = 요약재료(응답);
  const 문장 = '2026년 8월 취업자는 29,151천명으로 1년 전보다 1151천명 늘었다. 증감률은 4.1%다.';
  assert.equal(verify({ 답변: 문장 }, [], 허용텍스트, 허용숫자).ok, true);
});

test('재료에 없는 숫자는 걸린다 — 환각이 문장을 버리게 한다', () => {
  const { 허용텍스트, 허용숫자 } = 요약재료(응답);
  const v = verify({ 답변: '취업자는 31,400천명이다.' }, [], 허용텍스트, 허용숫자);
  assert.equal(v.ok, false);
  assert.deepEqual(v.위반, [31400]);
});

test('빈 응답에도 모양을 지킨다', () => {
  const { 재료, 허용텍스트, 허용숫자 } = 요약재료({});
  assert.deepEqual(재료.도메인, []);
  assert.ok(Array.isArray(허용텍스트) && Array.isArray(허용숫자));
});
