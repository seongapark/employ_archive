// 동시출현 네트워크. 외부 라이브러리를 쓰지 않는다 — 이 앱은 지금 외부 JS 가
// 하나도 없고(구글 폰트 CSS 뿐), CDN 을 하나 들이는 순간 서비스워커의 오프라인
// 캐시가 깨져 폐쇄망에서 빈 화면이 된다. 노드가 스물 남짓이라 직접 배치해도 된다.
//
// 3D 로 하지 않은 이유도 같은 자리에 적어 둔다: 노드 14~23개는 2D 평면에서 안
// 겹친다. 3D 는 노드가 수백 개라 2D 에서 겹칠 때 값을 하고, 그 아래에서는
// 앞뒤 가려짐만 늘린다. 모바일에서 회전·확대·선택 세 조작이 필요한 것도 나쁘다.

import { esc } from './data.js';

// 축마다 색을 준다. 보도자료 밖 표현만 주황으로 튀게 해서, 뭉치 안에 섞여
// 있어도 눈에 먼저 들어오게 한다.
export const AXIS_COLOR = {
  지표: '#98a2b3',
  산업: '#23508f',
  연령: '#17714a',
  밖: '#b3400c',
  논조: '#9a6b15',
};

/** '반도체(전자·통신)' → '반도체'. 괄호는 항목사전이 붙인 표준분류다. */
export function labelOf(id) {
  return String(id).replace(/\s*\(.*\)\s*$/, '');
}

/** 힘기반 배치(Fruchterman–Reingold).
 *
 * 난수를 쓰지 않는다 — 초기 위치를 원 위에 index 순으로 놓아서, 같은 데이터면
 * 언제 그려도 같은 그림이 나온다. 회차를 오갈 때 그림이 매번 달라지면
 * 「지난달과 뭐가 달라졌나」를 볼 수 없다.
 */
export function layout(nodes, edges, opts = {}) {
  const { width = 420, height = 360, iterations = 400, margin = 28 } = opts;
  const n = nodes.length;
  if (!n) return [];

  // 1.15 를 곱해 노드를 조금 더 벌린다. 라벨이 점 아래에 붙으므로
  //  점끼리만 안 겹치게 잡으면 글자가 겹친다.
  const k = Math.sqrt((width * height) / n) * 1.15;
  const pos = nodes.map((_, i) => {
    const t = (2 * Math.PI * i) / n;
    return { x: width / 2 + Math.cos(t) * width * 0.34,
             y: height / 2 + Math.sin(t) * height * 0.34 };
  });

  let temp = width * 0.12;
  for (let step = 0; step < iterations; step += 1) {
    const disp = pos.map(() => ({ x: 0, y: 0 }));

    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const dx = pos[i].x - pos[j].x;
        const dy = pos[i].y - pos[j].y;
        const d = Math.hypot(dx, dy) || 0.01;
        const f = (k * k) / d;
        disp[i].x += (dx / d) * f; disp[i].y += (dy / d) * f;
        disp[j].x -= (dx / d) * f; disp[j].y -= (dy / d) * f;
      }
    }

    for (const [a, b, w] of edges) {
      const dx = pos[a].x - pos[b].x;
      const dy = pos[a].y - pos[b].y;
      const d = Math.hypot(dx, dy) || 0.01;
      // 같이 나온 횟수가 많을수록 세게 당긴다. 상한을 두지 않으면 가장 센
      // 연결 하나가 그래프 전체를 한 점으로 접어버린다.
      const f = ((d * d) / k) * (Math.min(w, 6) / 3);
      disp[a].x -= (dx / d) * f; disp[a].y -= (dy / d) * f;
      disp[b].x += (dx / d) * f; disp[b].y += (dy / d) * f;
    }

    for (let i = 0; i < n; i += 1) {
      const d = Math.hypot(disp[i].x, disp[i].y) || 0.01;
      pos[i].x += (disp[i].x / d) * Math.min(d, temp);
      pos[i].y += (disp[i].y / d) * Math.min(d, temp);
      pos[i].x = Math.max(margin, Math.min(width - margin, pos[i].x));
      pos[i].y = Math.max(margin, Math.min(height - margin, pos[i].y));
    }
    temp *= 0.97;
  }

  return fit(pos, width, height, margin);
}

/** 배치가 한쪽에 쏠려도 화면을 꽉 채우게 늘린다. */
function fit(pos, width, height, margin) {
  const xs = pos.map((p) => p.x);
  const ys = pos.map((p) => p.y);
  const x0 = Math.min(...xs); const x1 = Math.max(...xs);
  const y0 = Math.min(...ys); const y1 = Math.max(...ys);
  const sx = (x1 - x0) > 1 ? (width - margin * 2) / (x1 - x0) : 1;
  const sy = (y1 - y0) > 1 ? (height - margin * 2) / (y1 - y0) : 1;
  const s = Math.min(sx, sy);
  return pos.map((p) => ({
    x: margin + (p.x - x0) * s,
    y: margin + (p.y - y0) * s,
  }));
}

/** 라벨끼리 겹치면 세로로 밀어낸다.
 *
 * 점을 안 겹치게 놓는 것만으로는 부족하다 — 라벨은 점보다 훨씬 넓어서
 * '반도체'와 '제조업'처럼 위아래로 가까운 두 점의 글자가 서로를 덮는다.
 * 점은 그대로 두고 글자만 움직인다(점 위치가 곧 구조라 건드리면 안 된다).
 */
export function spreadLabels(pos, nodes, opts = {}) {
  const { height = 360, margin = 28, lineH = 11.5, charW = 5.4, passes = 40 } = opts;
  const y = nodes.map((nd, i) => pos[i].y + radiusOf(nd.n) + 9);
  const w = nodes.map((nd) => labelOf(nd.id).length * charW + 4);

  for (let p = 0; p < passes; p += 1) {
    let moved = false;
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const dx = Math.abs(pos[i].x - pos[j].x);
        if (dx > (w[i] + w[j]) / 2) continue;      // 가로로 안 겹치면 상관없다
        const dy = y[i] - y[j];
        const need = lineH - Math.abs(dy);
        if (need <= 0) continue;
        const shift = (need / 2) + 0.2;
        if (dy >= 0) { y[i] += shift; y[j] -= shift; } else { y[i] -= shift; y[j] += shift; }
        moved = true;
      }
    }
    if (!moved) break;
  }
  return y.map((v) => Math.max(margin * 0.5, Math.min(height - 4, v)));
}

export function radiusOf(n) {
  return Math.min(4 + Math.sqrt(n) * 1.7, 15);
}

/** 노드를 누르면 그 말이 든 기사로 간다. 그림만 보여주고 끝내지 않는다. */
export function graphSvg(g, opts = {}) {
  const { width = 420, height = 360 } = opts;
  const nodes = (g && g.nodes) || [];
  const edges = (g && g.edges) || [];
  if (!nodes.length) return '';

  const pos = layout(nodes, edges, { width, height });
  const labelY = spreadLabels(pos, nodes, { height });
  const maxW = edges.reduce((m, e) => Math.max(m, e[2]), 1);

  const lines = edges.map(([a, b, w]) => {
    const o = 0.18 + 0.42 * (w / maxW);
    return `<line x1="${pos[a].x.toFixed(1)}" y1="${pos[a].y.toFixed(1)}"
      x2="${pos[b].x.toFixed(1)}" y2="${pos[b].y.toFixed(1)}"
      stroke="#c9ccd2" stroke-opacity="${o.toFixed(2)}"
      stroke-width="${(0.6 + (w / maxW) * 2.4).toFixed(2)}"></line>`;
  }).join('');

  const dots = nodes.map((nd, i) => {
    const label = labelOf(nd.id);
    const r = radiusOf(nd.n);
    const color = AXIS_COLOR[nd.axis] || AXIS_COLOR.밖;
    return `<a href="#/articles/${encodeURIComponent(label)}" aria-label="${esc(label)} ${nd.n}건">
      <circle cx="${pos[i].x.toFixed(1)}" cy="${pos[i].y.toFixed(1)}" r="${r.toFixed(1)}"
        fill="${color}" fill-opacity="0.9"></circle>
      <text x="${pos[i].x.toFixed(1)}" y="${labelY[i].toFixed(1)}"
        text-anchor="middle" class="gnode__label">${esc(label)}</text>
    </a>`;
  }).join('');

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}"
    role="img" class="gnet">${lines}${dots}</svg>`;
}

/** 범례. 색이 무엇을 뜻하는지 화면이 직접 말한다. */
export function legendHtml(g) {
  const used = new Set((g.nodes || []).map((n) => n.axis));
  const order = ['산업', '연령', '지표', '논조', '밖'];
  const name = { 밖: '보도자료 밖' };
  return order.filter((a) => used.has(a)).map((a) => `
    <span style="display:inline-flex;align-items:center;gap:4px;margin-right:9px;">
      <span style="width:8px;height:8px;border-radius:50%;background:${AXIS_COLOR[a]};"></span>
      ${esc(name[a] || a)}</span>`).join('');
}
