// 일별 추이 그림. **SVG 문자열만 만든다** — DOM 을 안 만지므로 좌표 불변식을
// 테스트가 지킨다. domains/employment/app/js/chart.js 와 같은 규율이다.

export const BAR_PAD = { l: 4, r: 4, t: 8, b: 14 };

// 막대 높이는 **조회수**로 그린다. 일별 방문자는 도메인별 최댓값이라 하한이고
// (설계 Task 4 주석), 누적 막대의 조각 합과 어긋나면 그림이 거짓말을 한다.
export function 막대SVG(일별, 순서, { width = 320, height = 120 } = {}) {
  const W = width - BAR_PAD.l - BAR_PAD.r;
  const H = height - BAR_PAD.t - BAR_PAD.b;
  const 합 = (d) => 순서.reduce((a, s) => a + (d.도메인별[s] ?? 0), 0);
  const max = Math.max(1, ...일별.map(합));
  const 칸 = 일별.length ? W / 일별.length : W;
  const 폭 = Math.max(1, 칸 * 0.72);

  const 묶음 = 일별.map((d, i) => {
    const x = BAR_PAD.l + i * 칸 + (칸 - 폭) / 2;
    let 아래 = BAR_PAD.t + H;
    const 조각 = 순서.flatMap((s) => {
      const v = d.도메인별[s] ?? 0;
      if (!v) return [];
      const h = (v / max) * H;
      아래 -= h;
      return [`<rect x="${x.toFixed(1)}" y="${아래.toFixed(1)}" width="${폭.toFixed(1)}"`
        + ` height="${h.toFixed(1)}" fill="var(--dom-${s})"></rect>`];
    });
    return `<g class="bar" data-day="${d.날짜}">${조각.join('')}</g>`;
  });

  const 축 = `<line x1="${BAR_PAD.l}" y1="${BAR_PAD.t + H}" x2="${width - BAR_PAD.r}"`
    + ` y2="${BAR_PAD.t + H}" stroke="var(--border)" stroke-width="1"></line>`;

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}"`
    + ` role="img" aria-label="일별 조회수 추이">${축}${묶음.join('')}</svg>`;
}
