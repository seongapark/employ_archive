// 해시 라우팅. app.js 에서 떼어 냈다 — app.js 는 import 만 해도 boot() 가 돌아
// 테스트가 부를 수 없었고, 그래서 라우트 파싱만 시험할 길이 없었다.
//
// `segment` 는 세그먼트바가 어느 탭을 켤지다. 화면 이름과 따로 두는 이유는
// **하위 화면** 때문이다. 보도자료 화면(`#/r/…`)은 총괄 카드를 눌러 들어가는
// 총괄의 아래층이므로, 거기 있는 동안 총괄 탭이 켜져 있어야 한다. 화면 이름으로
// 탭을 고르면 셋 다 꺼져서, 사용자는 자기가 어느 탭 아래에 있는지도 밖으로
// 나가는 길도 함께 잃는다.

import { SOURCE_ORDER } from './data.js';

const OVERVIEW = { name: 'overview', segment: 'overview', params: {} };

export function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return OVERVIEW;
  if (h === '/sources') return { name: 'sources', segment: 'sources', params: {} };

  const b = h.match(/^\/b\/(industry|sex|age)(?:\/(.+))?$/);
  if (b) {
    let category = null;
    if (b[2]) { try { category = decodeURIComponent(b[2]); } catch { category = null; } }
    return {
      name: 'breakdown', segment: 'breakdown',
      params: { breakdown: b[1], category },
    };
  }

  const r = h.match(/^\/r\/([a-z]+)$/);
  // 낡은 북마크가 없어진 출처를 가리키면 빈 화면 대신 총괄로 떨어진다.
  if (r && SOURCE_ORDER.includes(r[1])) {
    return { name: 'release', segment: 'overview', params: { code: r[1] } };
  }

  return OVERVIEW;
}
