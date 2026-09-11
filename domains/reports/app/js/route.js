// 해시 주소를 화면 이름과 조각으로 나눈다. DOM 도 네트워크도 모른다 —
// app.js 안에 두면 테스트가 조립 전 트리에서 ../core/ 를 못 찾아 못 돈다.

// 세그먼트를 나눈 뒤 각각 디코드해 `params` 로 준다. 화면은 그대로 쓴다.
//
// 디코드를 화면마다 알아서 하게 뒀더니 주제 화면만 빠져서, 제목이
// '%EC%B2%AD...' 로 뜨고 목록이 0건이 됐다. 책임을 여기 한 곳으로 모은다.
// 나눈 뒤에 디코드하는 순서가 중요하다 — 먼저 디코드하면 이름 안의 %2F 가
// 진짜 '/' 가 되어 세그먼트가 하나 더 생긴다.
export function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'home', params: [], tab: 'home' };
  const [, head, ...rest] = h.split('/');
  const params = rest.filter((s) => s !== '').map(decodeSegment);
  if (head === 'picks') return { name: 'picks', params, tab: 'picks' };
  if (head === 'topics') return { name: 'topics', params, tab: 'topics' };
  if (head === 'orgs') return { name: 'orgs', params, tab: 'orgs' };
  if (head === 'r') return { name: 'report', params, tab: null };
  return { name: 'home', params: [], tab: 'home' };
}

function decodeSegment(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;              // 손상된 주소로 화면을 죽이지 않는다
  }
}
