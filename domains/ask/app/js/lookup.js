// 출처 탐색 화면. **문장형 답변 영역이 없다** — 이 기능은 문장을 만들지 않는다.
//
// 순수 함수로 둔다(문자열 in, 문자열 out). DOM 을 만지지 않아 테스트가 브라우저
// 없이 돌고, `esc` 를 주입받아 이스케이프 규칙을 두 벌 두지 않는다.

export const 도메인이름 = {
  employment: '고용동향',
  forecast: '고용전망',
  reports: '연구보고서',
  press: '행통 모니터링',
  catalog: '출처 카탈로그',
};

const 이름 = (d) => 도메인이름[d] ?? d;

function 한줄(x, esc) {
  const 제목 = `<div class="lk__title">${esc(x.제목 ?? '')}</div>`;
  const 유형 = x.근거유형 ? `<span class="lk__kind">${esc(x.근거유형)}</span>` : '';
  const 조각 = x.스니펫 ? `<div class="lk__snippet">${esc(x.스니펫)}</div>` : '';
  // 갈 곳이 없으면 링크를 그리지 않는다. 빈 링크를 그리면 눌러도 아무 일이 없다 —
  // 카탈로그의 충돌·한계가 그런 항목이다.
  const 링크 = x.링크
    ? `<a class="lk__go" href="${esc(x.링크)}" target="_blank" rel="noopener">원문 보기</a>`
    : '';
  return `<li class="lk__item">${유형}${제목}${조각}${링크}</li>`;
}

export function 묶음HTML(응답, { esc }) {
  const 묶음 = 응답?.묶음 ?? [];
  const 해당없음 = 응답?.해당없음 ?? [];
  if (!묶음.length && !해당없음.length) {
    return '<p class="lk__empty">찾지 못했다 — 질문을 다시 써 보세요.</p>';
  }

  const 절 = [];
  for (const g of 묶음) {
    const 머리 = `<h3 class="lk__head">${esc(이름(g.도메인))}`
      + `<span class="lk__count">${g.결과.length}건</span></h3>`;
    // 걸린 게 없으면 왜 없는지 말한다. 빈 자리만 남기면 화면이 아무 말도 안 한다.
    const 몸 = g.결과.length
      ? `<ul class="lk__list">${g.결과.map((x) => 한줄(x, esc)).join('')}</ul>`
      : `<p class="lk__none">${esc(g.사유 ?? '걸리는 것이 없다')}</p>`;
    절.push(`<section class="lk">${머리}${몸}</section>`);
  }

  // **해당 없는 도메인도 남긴다.** 조용히 빠지면 사용자는 그 도메인이 있는 줄도 모른다.
  for (const x of 해당없음) {
    절.push(`<section class="lk lk--off"><h3 class="lk__head">${esc(이름(x.도메인))}`
      + `<span class="lk__count">해당 없음</span></h3>`
      + `<p class="lk__none">${esc(x.사유 ?? '')}</p></section>`);
  }
  return 절.join('');
}
