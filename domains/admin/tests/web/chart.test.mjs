import { test } from 'node:test';
import assert from 'node:assert/strict';
import { 막대SVG, BAR_PAD } from '../../app/js/chart.js';

const 일별 = [
  { 날짜: '2026-09-01', 방문자: 2, 도메인별: { employment: 3, press: 1 } },
  { 날짜: '2026-09-02', 방문자: 1, 도메인별: { employment: 1 } },
];
const 순서 = ['employment', 'press', 'forecast', 'reports', 'ask', 'hub'];

test('날짜마다 막대 묶음이 하나씩 나온다', () => {
  const svg = 막대SVG(일별, 순서, { width: 320, height: 120 });
  assert.equal((svg.match(/<g class="bar"/g) ?? []).length, 2);
});

test('누적 조각은 값이 있는 도메인만 그린다', () => {
  const svg = 막대SVG(일별, 순서, { width: 320, height: 120 });
  assert.equal((svg.match(/<rect/g) ?? []).length, 3);
});

// 가장 높은 날의 막대가 그림 안에 들어가야 한다 — 넘치면 잘린다.
// 정규식이 `width` 를 끼고 있어야 한다: rect 의 속성 순서가 x·y·width·height 라
// `y="…" height="…"` 로 맞히면 한 건도 안 걸려 **아무것도 검사하지 않는 테스트**가
// 된다(실제로 돌려 확인했다).
test('막대는 그림 높이를 안 넘는다', () => {
  const svg = 막대SVG(일별, 순서, { width: 320, height: 120 });
  const 좌표 = [...svg.matchAll(/y="([\d.]+)" width="[\d.]+" height="([\d.]+)"/g)];
  assert.equal(좌표.length, 3, '조각을 하나도 못 읽었다 — 정규식이 rect 와 안 맞는다');
  for (const m of 좌표) {
    assert.ok(Number(m[1]) >= BAR_PAD.t - 0.01, `위로 넘쳤다: ${m[1]}`);
    assert.ok(Number(m[1]) + Number(m[2]) <= 120 - BAR_PAD.b + 0.01, `아래로 넘쳤다: ${m[0]}`);
  }
});

test('빈 목록도 유효한 SVG 를 낸다', () => {
  const svg = 막대SVG([], 순서, { width: 320, height: 120 });
  assert.ok(svg.startsWith('<svg'));
  assert.ok(svg.endsWith('</svg>'));
  assert.equal((svg.match(/<rect/g) ?? []).length, 0);
});

test('DOM 없이 문자열만 만든다', () => {
  assert.equal(typeof 막대SVG(일별, 순서, {}), 'string');
});
