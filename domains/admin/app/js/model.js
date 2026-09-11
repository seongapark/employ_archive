// 관리자 화면의 순수 로직. DOM 도 네트워크도 건드리지 않는다.

// **hub/js/state.js 의 DOMAINS 를 끌어 쓸 수 없다.** 빌드가 도메인 폴더에 복사하는
// 것은 core/ 뿐이라 배포본에 그 경로가 없고, 그 목록에는 hub·ask 가 애초에 빠져
// 있다(허브는 자기 카드를 안 그리고, 질의응답은 카드가 아니라 검색창이라서).
export const 이름 = {
  employment: '고용동향',
  press: '행통 모니터링',
  forecast: '고용전망',
  reports: '연구보고서',
  ask: '질의응답',
  hub: '허브',
};

// 색과 범례의 순서. 허브 카드 순서(사용자가 정한 것)를 따르고 허브를 끝에 둔다 —
// 허브는 도메인이 아니라 통로다.
export const 순서 = ['employment', 'press', 'forecast', 'reports', 'ask', 'hub'];

export const 기간선택 = [
  { days: 7, label: '7일' },
  { days: 30, label: '30일', 기본: true },
  { days: 90, label: '90일' },
  { days: 0, label: '전체' },
];

// 직전이 0 이면 배수가 무한대다. 숫자를 지어내느니 비교를 포기한다.
export function 증감(현재, 직전) {
  if (!직전) return null;
  const 값 = Math.round(((현재 - 직전) / 직전) * 100);
  const 방향 = 값 > 0 ? 'up' : (값 < 0 ? 'down' : 'flat');
  return { 값, 방향, 라벨: `${값 > 0 ? '+' : ''}${값}%` };
}

export const 퍼센트 = (n, 전체) =>
  (전체 ? Math.round((n / 전체) * 1000) / 10 : 0);

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
