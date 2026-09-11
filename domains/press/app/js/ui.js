// 여러 화면이 같이 쓰는 조각. 문자열을 만들고 붙이는 일만 한다.
import { esc, scale, timeLabel, dayLabel } from './data.js';

/** 회차 스위치. 셸이 한 번만 그리고 네 화면이 같은 것을 본다.
    회차가 매달 늘어나므로 버튼이 아니라 select 다. */
export function roundSwitchHtml(ctx) {
  const opts = ctx.rounds.map((r) => {
    const sel = r.release === ctx.state.release ? ' selected' : '';
    return `<option value="${esc(r.release)}"${sel}>${esc(r.label)} · ${esc(dayLabel(r.release))} 배포</option>`;
  }).join('');
  return `<select aria-label="회차 선택">${opts}</select>`;
}

export function bindRoundSwitch(el, ctx) {
  const sel = el.querySelector('select');
  if (!sel) return;
  sel.addEventListener('change', (e) => {
    ctx.state.release = e.target.value;
    ctx.rerender();
  });
}

/** 세로 막대 한 축. 0건은 빗금 기둥으로 남긴다 — 빈 칸은 사실을 안 보여준다.
 *
 * 가로 막대에서 바꿨다(2026-09-11). 축이 셋이면 가로 막대는 15줄이 되어
 * 휴대폰에서 한 화면에 안 들어오고, 스크롤하는 동안 축이 머리에서 흩어진다.
 * 기둥은 한 축이 한 줄이라 셋을 나란히 볼 수 있다.
 *
 * 계열이 하나라 범례가 없다. 대신 값을 기둥마다 직접 적는다 — 기둥이 일곱 개
 * 안쪽이라 숫자가 붙어도 안 겹친다.
 */
export function columnChart(title, rows, opts = {}) {
  const { unit = '건' } = opts;
  const body = scale(rows).map((r) => `
    <div class="vcol" title="${esc(r.name)} ${r.n}${esc(unit)}">
      <div class="vcol__n num">${r.n}</div>
      <div class="vcol__track${r.n === 0 ? ' vcol__track--zero' : ''}">
        ${r.n > 0 ? `<div class="vcol__fill" style="height:${r.pct}%;"></div>` : ''}
      </div>
      <div class="vcol__name">${esc(r.name)}</div>
    </div>`).join('');
  return `<div class="vchart">
    <div class="sec-title">${esc(title)}</div>
    <div class="vchart__plot">${body}</div>
  </div>`;
}

/** 기사 한 줄. 인용이 아닌 기사는 흐리게 두되 지우지는 않는다.
 *
 * 제목은 한 줄로 자른다(CSS 가 … 를 붙인다). 줄마다 높이가 같아야 목록을
 * 훑을 때 눈이 일정한 간격으로 떨어진다 — 두 줄짜리가 섞이면 스크롤하면서
 * 몇 건을 지났는지 감각이 끊긴다. 전문은 눌러서 원문으로 간다.
 *
 * 태그는 제목 줄에서 아래 줄로 내렸다. 제목을 한 줄로 자르면 태그가 먼저
 * 잘려 나가 붙여 둔 뜻이 없다.
 */
export function articleRow(a) {
  const tags = (a.kw || []).slice(0, 2)
    .map((w) => `<span class="art__tag">${esc(w)}</span>`).join('');
  const why = !a.cites && a.why ? `<span>· ${esc(a.why)}</span>` : '';
  const inner = `
    <div class="art__title" title="${esc(a.title)}">${esc(a.title)}</div>
    <div class="art__meta"><span>${esc(a.press)}</span><span class="num">${esc(timeLabel(a.pub))}</span>${why}${tags}</div>`;
  return a.url
    ? `<a class="art${a.cites ? '' : ' art--other'}" href="${esc(a.url)}" target="_blank" rel="noopener">${inner}</a>`
    : `<div class="art${a.cites ? '' : ' art--other'}">${inner}</div>`;
}

/** 파이 조각 색. **축마다 항목 순서가 고정**이라(SECTIONS·AGES·INDUSTRIES)
 *  n번째 항목은 늘 n번째 색이다 — 회차가 바뀌어 크기 순서가 달라져도 제조업은
 *  계속 같은 색이다. 색이 순위를 따라가면 지난달과 비교할 수 없다.
 *
 *  앞 여섯은 색각 검증을 통과한 조합이다(protan·deutan·tritan 전 구간).
 *  일곱 색이 되는 순간 어떤 조합도 통과하지 못해서, 일곱째 칸은 회색으로 둔다
 *  — 보건복지업 자리이고 세 회차 내내 0건이라 조각으로 그려진 적이 없다.
 *  색만으로 읽히지 않게 범례가 이름·건수·비율을 직접 적는다.
 */
export const PIE_COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7',
                           '#56B4E9', '#E69F00', '#98a2b3'];

function arcPath(cx, cy, r, a0, a1) {
  const at = (a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = at(a0);
  const [x1, y1] = at(a1);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} `
    + `A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

/** 한 축을 파이 하나로. **큰 조각부터 시계방향**으로 놓고 레이블을 조각 위에 얹는다.
 *
 *  크기 순으로 놓는 것과 색을 항목에 묶는 것은 서로 다른 일이다 — 그리는 순서만
 *  바뀌고 색은 항목을 따라간다(`PIE_COLORS[원래 자리]`). 색이 순위를 따라가면
 *  회차를 오갈 때 같은 산업이 매달 다른 색이 되어 비교할 수 없다.
 *
 *  조각이 좁으면 글자가 안 들어간다. 9% 아래는 레이블을 얹지 않고 아래 한 줄로
 *  이름을 부른다. **0건 항목도 그 줄에 남긴다** — 조각이 없다고 지우면
 *  「구직급여 보도 0건」이 화면에서 사라지는데, 그게 이 도메인이 잡아야 할 것이다.
 *
 *  조각 합은 인용 기사 수가 아니다. 한 기사가 여러 칸에 들어가기 때문이다
 *  (제조업이 반도체·조선을 품는다). 그래서 축 이름 옆에 「중복 포함」을 붙인다.
 */
export function pieChart(title, rows, opts = {}) {
  const { note = '중복 포함', size = 150, minLabel = 9 } = opts;
  const total = rows.reduce((n, r) => n + r.n, 0);

  const cx = 50;
  const cy = 50;
  const r = 47;
  // 원래 자리를 들고 큰 것부터 — 색은 자리를 따라가고 순서만 크기를 따라간다.
  const drawn = rows.map((x, i) => ({ ...x, i })).filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n || a.i - b.i);

  let a = -Math.PI / 2;                        // 12시에서 시작해 시계방향으로 돈다
  const slices = [];
  const labels = [];
  for (const d of drawn) {
    const color = PIE_COLORS[d.i % PIE_COLORS.length];
    const pct = Math.round((d.n / total) * 100);
    const tip = `<title>${esc(d.name)} ${d.n}건 ${pct}%</title>`;
    const a0 = a;
    a += (d.n / total) * Math.PI * 2;
    if (drawn.length === 1) {                 // 100% 는 호가 아니라 원 하나다
      slices.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}">${tip}</circle>`);
    } else {
      slices.push(`<path d="${arcPath(cx, cy, r, a0, a)}" fill="${color}"
        stroke="var(--card)" stroke-width="1.4">${tip}</path>`);
    }
    if (pct < minLabel) {
      labels.push(null);
      continue;
    }
    // 조각 한가운데. 원 하나뿐이면 가운데에 얹는다.
    const mid = (a0 + a) / 2;
    const away = drawn.length === 1 ? 0 : r * 0.58;
    const lx = cx + Math.cos(mid) * away;
    const ly = cy + Math.sin(mid) * away;
    labels.push(`<text x="${lx.toFixed(1)}" y="${(ly - 1.5).toFixed(1)}"
        text-anchor="middle" class="pie__lab">${esc(d.name)}</text>
      <text x="${lx.toFixed(1)}" y="${(ly + 7).toFixed(1)}"
        text-anchor="middle" class="pie__lab pie__lab--n">${d.n} · ${pct}%</text>`);
  }

  // 레이블을 못 단 조각과 0건 항목은 이름만 한 줄로 부른다.
  const tiny = drawn.filter((d, k) => labels[k] === null).map((d) => `${d.name} ${d.n}`);
  const zero = rows.filter((x) => !x.n).map((x) => x.name);
  const tail = [
    tiny.length ? `작은 조각 ${tiny.join(' · ')}` : '',
    zero.length ? `보도 0건 ${zero.join(' · ')}` : '',
  ].filter(Boolean).join('  ·  ');

  const body = total
    ? `<svg class="pie__svg" viewBox="0 0 100 100" width="${size}" height="${size}"
         role="img" aria-label="${esc(title)} 구성">${slices.join('')}${labels.join('')}</svg>`
    : `<div class="pie__empty" style="width:${size}px;height:${size}px;">0건</div>`;

  return `<div class="pie">
    <div class="sec-title">${esc(title)}
      <span class="pie__note">${esc(note)}</span></div>
    ${body}
    ${tail ? `<div class="pie__tail">${esc(tail)}</div>` : ''}
  </div>`;
}

/** 헤드라인 한 줄. 제목이 길면 제목만 줄이고 언론사는 끝까지 남긴다.
 *
 * 줄바꿈을 허용하면 어떤 기사는 한 줄, 어떤 기사는 세 줄이 되어 묶음의
 * 크기가 제목 길이에 따라 달라 보인다. 어느 매체가 썼는지는 제목만큼
 * 중요하므로, 줄이는 것은 제목 쪽이다.
 */
export function headlineRow(h) {
  const title = h.url
    ? `<a class="hl__t" href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a>`
    : `<span class="hl__t">${esc(h.title)}</span>`;
  return `<div class="hl" title="${esc(h.title)}">
    ${title}<span class="hl__p">(${esc(h.press)})</span></div>`;
}

export function card(inner, style = '') {
  return `<div class="card" style="${style}">${inner}</div>`;
}

export function section(inner) {
  return `<div style="display:flex;flex-direction:column;gap:10px;padding:10px 16px 16px 16px;">${inner}</div>`;
}
