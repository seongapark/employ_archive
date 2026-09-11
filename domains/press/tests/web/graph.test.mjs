import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  layout, spreadLabels, labelOf, radiusOf, graphSvg, legendHtml, AXIS_COLOR,
  neighborsOf, indexOfLabel,
} from '../../app/js/graph.js';

const NODES = [
  { id: '제조업', axis: '산업', n: 51 },
  { id: '반도체(전자·통신)', axis: '산업', n: 27 },
  { id: '반등', axis: '밖', n: 16 },
  { id: '청년', axis: '연령', n: 10 },
  { id: '고용보험', axis: '지표', n: 31 },
];
const EDGES = [[0, 1, 24], [0, 2, 16], [0, 4, 21], [3, 4, 8]];
const G = { nodes: NODES, edges: EDGES, trimmed: 1 };

test('labelOf는 항목사전이 붙인 표준분류 괄호를 뗀다', () => {
  assert.equal(labelOf('반도체(전자·통신)'), '반도체');
  assert.equal(labelOf('제조업'), '제조업');
});

test('배치는 난수를 쓰지 않아 같은 데이터면 같은 그림이 나온다', () => {
  const a = layout(NODES, EDGES);
  const b = layout(NODES, EDGES);
  assert.deepEqual(a, b);
});

test('배치는 화면 밖으로 나가지 않는다', () => {
  const pos = layout(NODES, EDGES, { width: 420, height: 360, margin: 28 });
  for (const p of pos) {
    assert.ok(p.x >= 0 && p.x <= 420, `x=${p.x}`);
    assert.ok(p.y >= 0 && p.y <= 360, `y=${p.y}`);
  }
});

test('노드가 서로 겹치지 않는다 — 점끼리 최소한 반지름 합만큼은 떨어진다', () => {
  const pos = layout(NODES, EDGES);
  for (let i = 0; i < NODES.length; i += 1) {
    for (let j = i + 1; j < NODES.length; j += 1) {
      const d = Math.hypot(pos[i].x - pos[j].x, pos[i].y - pos[j].y);
      assert.ok(d > radiusOf(NODES[i].n) + radiusOf(NODES[j].n),
        `${NODES[i].id}—${NODES[j].id} 가 겹친다 (d=${d.toFixed(1)})`);
    }
  }
});

test('라벨은 가로로 겹치는 것끼리 세로로 벌어진다', () => {
  // 두 점을 같은 x 에 아주 가깝게 두면 라벨이 반드시 겹친다.
  const nodes = [{ id: '반도체', axis: '산업', n: 4 }, { id: '제조업', axis: '산업', n: 4 }];
  const pos = [{ x: 200, y: 180 }, { x: 202, y: 184 }];
  const y = spreadLabels(pos, nodes);
  assert.ok(Math.abs(y[0] - y[1]) >= 11, `벌어지지 않았다: ${y}`);
});

test('빈 그래프는 빈 문자열이지 깨진 svg 가 아니다', () => {
  assert.equal(graphSvg({ nodes: [], edges: [] }), '');
  assert.equal(graphSvg(null), '');
  assert.deepEqual(layout([], []), []);
});

test('svg 는 노드마다 기사 목록으로 가는 링크를 단다', () => {
  const h = graphSvg(G);
  assert.match(h, /href="#\/articles\/%EB%B0%98%EB%93%B1"/);   // '반등'
  // 점마다 원이 둘이다: 보이는 점과, 손가락이 짚을 수 있게 겹쳐 둔 안 보이는 원.
  // 보이는 점을 키우면 '점 크기 = 기사 수'가 거짓말이 된다.
  assert.equal((h.match(/gnode__dot/g) || []).length, NODES.length);
  assert.equal((h.match(/gnode__hit/g) || []).length, NODES.length);
  assert.equal((h.match(/<line/g) || []).length, EDGES.length);
});

test('산업과 연령은 서로 다른 색이다 — 같은 계열이면 축을 못 가른다', () => {
  assert.notEqual(AXIS_COLOR.산업, AXIS_COLOR.연령);
  assert.equal(AXIS_COLOR.밖, '#b3400c');
});

test('범례는 실제로 쓰인 축만 싣는다', () => {
  const h = legendHtml(G);
  assert.match(h, /보도자료 밖/);
  assert.ok(!h.includes('논조'));      // G 에 논조 노드가 없다
});


test('neighborsOf: 고른 점과 직접 이어진 점만 남는다', () => {
  // 0(제조업)은 1·2·4 와 이어져 있고 3(청년)과는 안 이어져 있다.
  assert.deepEqual([...neighborsOf(G, 0)].sort((a, b) => a - b), [0, 1, 2, 4]);
  assert.deepEqual([...neighborsOf(G, 3)].sort((a, b) => a - b), [3, 4]);
});

test('indexOfLabel 은 괄호를 뗀 이름으로 찾는다 — 링크가 그 이름으로 걸린다', () => {
  assert.equal(indexOfLabel(G, '반도체'), 1);
  assert.equal(indexOfLabel(G, '반도체(전자·통신)'), -1);
  assert.equal(indexOfLabel(G, null), -1);
});

test('고른 점 없이 그리면 아무것도 옅어지지 않는다', () => {
  const h = graphSvg(G);
  assert.ok(!h.includes('gnode--dim'));
  assert.ok(!h.includes('gedge--dim'));
  assert.ok(!h.includes('gnet--picked'));
});

test('점을 고르면 이웃이 아닌 점과 안 닿는 선이 옅어진다', () => {
  const h = graphSvg(G, { selected: '청년' });
  assert.ok(h.includes('gnet--picked'));
  // 청년(3)의 이웃은 4 뿐 — 0·1·2 는 옅어진다.
  assert.equal((h.match(/gnode--dim/g) || []).length, 3);
  assert.equal((h.match(/gnode--on/g) || []).length, 1);
  // 청년에 닿는 선은 [3,4] 하나, 나머지 셋은 옅어진다.
  assert.equal((h.match(/gedge--dim/g) || []).length, 3);
  assert.equal((h.match(/gedge--on/g) || []).length, 1);
});

test('없는 이름을 고르면 고르지 않은 것과 같다 — 깨진 해시로 그림이 비지 않는다', () => {
  const h = graphSvg(G, { selected: '없는말' });
  assert.ok(!h.includes('gnode--dim'));
  assert.ok(!h.includes('gnet--picked'));
});

test('노드와 선은 번호를 달고 나온다 — 다시 그리지 않고 class 만 바꾸기 위해서다', () => {
  const h = graphSvg(G);
  assert.ok(h.includes('data-node="0"'));
  assert.ok(h.includes('data-edge="0,1"'));
  assert.ok(h.includes('data-kw="반도체"'));
});
