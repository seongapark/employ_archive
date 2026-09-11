// 구역별 HTML 조립. render.js 도 DOM 을 안 만진다 — 문자열만 만들어서
// 호출부(app.js, 다음 과업)가 innerHTML 에 꽂는다.
import { 이름, 증감, 퍼센트, esc } from './model.js';

const 없음 = (무엇) => `<p class="empty">아직 기록이 없다 — ${esc(무엇)}</p>`;

const 델타 = (현재, 직전) => {
  const d = 증감(현재, 직전);
  return d ? `<span class="delta delta-${d.방향}">${d.라벨}</span>` : '';
};

const 수 = (n) => Number(n ?? 0).toLocaleString('ko-KR');

export function 요약HTML(s) {
  const 칸 = [['방문자', s.요약.방문자, s.직전?.방문자], ['세션', s.요약.세션, s.직전?.세션],
    ['조회', s.요약.조회, s.직전?.조회]];
  return `<section class="summary">${칸.map(([이름표, v, 전]) => `
    <div class="summary__cell">
      <div class="summary__label">${이름표}</div>
      <div class="summary__value num">${수(v)}</div>
      ${델타(v, 전)}
    </div>`).join('')}</section>
    <p class="summary__new">신규 <b class="num">${수(s.요약.신규)}</b> ·
      재방문 <b class="num">${수(s.요약.재방문)}</b></p>`;
}

export function 도메인HTML(s) {
  if (!s.도메인.length) return 없음('도메인별 방문');
  const 전체 = s.도메인.reduce((a, d) => a + d.조회, 0);
  const 정렬 = [...s.도메인].sort((a, b) => b.방문자 - a.방문자 || b.조회 - a.조회);
  return `<section class="domains">${정렬.map((d) => `
    <div class="dom">
      <div class="dom__head">
        <span class="dom__dot" style="background:var(--dom-${esc(d.도메인)})"></span>
        <span class="dom__name">${esc(이름[d.도메인] ?? d.도메인)}</span>
        <span class="dom__visitors num">${수(d.방문자)}</span>
        ${'직전방문자' in d ? 델타(d.방문자, d.직전방문자) : ''}
      </div>
      <div class="dom__bar"><i style="width:${퍼센트(d.조회, 전체)}%;
        background:var(--dom-${esc(d.도메인)})"></i></div>
      <div class="dom__meta num">조회 ${수(d.조회)} · 세션 ${수(d.세션)}</div>
    </div>`).join('')}</section>
    <p class="note">한 사람이 두 도메인을 보면 양쪽에 세어진다 — 합계가 전체 방문자보다 크다.</p>`;
}

export function 화면HTML(s) {
  if (!s.화면.length) return 없음('화면별 조회');
  const max = Math.max(...s.화면.map((r) => r.조회), 1);
  return `<table class="rows">${s.화면.map((r) => `
    <tr>
      <td class="rows__tag" style="color:var(--dom-${esc(r.도메인)})">${esc(이름[r.도메인] ?? r.도메인)}</td>
      <td class="rows__key">${esc(r.경로)}</td>
      <td class="rows__bar"><i style="width:${퍼센트(r.조회, max)}%"></i></td>
      <td class="rows__num num">${수(r.조회)}</td>
    </tr>`).join('')}</table>`;
}

const 유입이름 = { direct: '직접', search: '검색', social: '소셜', link: '링크' };

export function 유입HTML(s) {
  if (!s.유입.종류.length && !s.유입.호스트.length) return 없음('유입 경로');
  const 세션합 = s.유입.종류.reduce((a, x) => a + x.세션, 0);
  return `<div class="kinds">${s.유입.종류.map((x) => `
      <div class="kind"><div class="kind__name">${esc(유입이름[x.종류] ?? x.종류)}</div>
        <div class="kind__num num">${수(x.세션)}</div>
        <div class="kind__pct num">${퍼센트(x.세션, 세션합)}%</div></div>`).join('')}</div>
    ${s.유입.호스트.length ? `<table class="rows">${s.유입.호스트.map((h) => `
      <tr><td class="rows__key">${esc(h.호스트)}</td>
        <td class="rows__num num">${수(h.세션)}</td></tr>`).join('')}</table>` : ''}`;
}

const 기기이름 = { mobile: '모바일', tablet: '태블릿', desktop: 'PC' };
const 모드이름 = { standalone: '설치앱', browser: '브라우저' };

export function 분포HTML(s) {
  const 묶음 = [['기기', s.기기, 기기이름], ['표시모드', s.표시모드, 모드이름],
    ['국가', s.국가, {}]];
  return 묶음.map(([제목, 목록, 사전]) => {
    const 합 = 목록.reduce((a, x) => a + x.방문자, 0);
    return `<div class="dist"><h3 class="dist__title">${제목}</h3>
      ${목록.length ? `<table class="rows">${목록.map((x) => `
        <tr><td class="rows__key">${esc(사전[x.값] ?? x.값)}</td>
          <td class="rows__bar"><i style="width:${퍼센트(x.방문자, 합)}%"></i></td>
          <td class="rows__num num">${수(x.방문자)}</td></tr>`).join('')}</table>`
        : 없음(제목)}</div>`;
  }).join('');
}

// 제외 스위치와 토큰 지우기. 정상 화면과 오류 화면(미배포·연결실패) 둘 다에서
// 쓴다 — 오류 화면이라고 이 둘이 사라지면, 토큰을 잘못 넣은 채로 오류 화면에
// 갇혔을 때 잠금 화면으로 돌아갈 길이 없어 localStorage 를 손으로 지워야 한다
// (design §7.4: "지금 켜져 있는지를 화면이 보여 준다").
export function 도구HTML(제외켜짐) {
  return `<div class="tools">
    <label class="toggle"><input id="off" type="checkbox"${제외켜짐 ? ' checked' : ''}>
      내 방문을 통계에서 뺀다</label>
    <button id="logout" class="toggle__btn" type="button">토큰 지우기</button>
  </div>`;
}

export function 잠금HTML() {
  return `<form id="unlock" class="unlock">
    <label class="unlock__label" for="token">관리자 비밀번호</label>
    <input id="token" class="unlock__input" type="password" autocomplete="current-password">
    <button class="unlock__go" type="submit">열기</button>
    <p class="unlock__hint">워커에 넣어 둔 값과 맞아야 한다.</p>
  </form>`;
}
