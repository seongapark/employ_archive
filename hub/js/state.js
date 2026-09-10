// 허브의 순수 로직. DOM도 네트워크도 건드리지 않는다.

// 허브는 도메인 목록만 알고 내용은 모른다. 도메인이 사라지면 last_run.json이
// 404가 되어 자동으로 '준비중'이 되고, 붙으면 자동으로 살아난다.
// 주요 도메인 넷. **질의응답은 여기 없다** — 카드가 아니라 맨 위 검색창이 됐다.
// 넷의 자료에서 질문에 맞는 출처를 찾아 주는 창구이지, 나란한 다섯째 도메인이
// 아니기 때문이다(2026-09-10 사용자 결정).
//
// `supply`(인력수급)도 뺐다. 카드만 있고 도메인 폴더가 없어 늘 '준비중' 이었다 —
// 중장기 인력수급전망은 `reports` 의 KEIS 인력수급전망으로 들어와 있다.
//
// **순서는 사용자가 정한다**(2026-09-10): 지금 수치 → 그 수치가 어떻게 보도됐나 →
// 앞으로의 전망 → 관련 연구. 알파벳순도 추가순도 아니므로 손대지 말 것.
export const DOMAINS = [
  { slug: 'employment', name: '고용동향', desc: '경활·사업체·고용행정통계 비교' },
  { slug: 'press', name: '행통 모니터링', desc: '고용행정통계 기사 모니터링' },
  { slug: 'forecast', name: '고용전망', desc: '기관별 고용 전망치' },
  { slug: 'reports', name: '연구보고서', desc: 'KLI·KEIS·KDI·KIET 고용 보고서 검색' },
];

export function domainState(lastRun) {
  return 실행시각(lastRun) ? 'ready' : 'pending';
}

// 실행 시각 필드가 도메인마다 다르다 — 셋은 `run_at`, 연구보고서는 `at` 이다.
// 한쪽만 읽으면 그 도메인이 늘 '준비중' 으로 그려진다(2026-09-10 화면에서 확인).
// 이름을 통일하는 편이 낫지만 그건 수집기와 각 앱을 함께 고치는 일이라, 허브는
// 둘 다 받아 준다.
const 실행시각 = (lastRun) => (lastRun && (lastRun.run_at ?? lastRun.at)) || null;

export function updatedLabel(lastRun) {
  const at = 실행시각(lastRun);
  if (!at) return '준비중';
  return `${at.slice(5, 7)}.${at.slice(8, 10)} 갱신`;
}

// 허브는 질문의 내용을 모른다. 문자열을 그대로 넘길 뿐이다.
export function askHref(q) {
  const s = String(q ?? '').trim();
  return s ? `./ask/#/q=${encodeURIComponent(s)}` : null;
}

// 카드 한 장의 내용. **네트워크 없이도 다 정해진다** — 이름·설명은 DOMAINS 에 있고,
// last_run 은 갱신 날짜와 '들어갈 수 있는가' 만 정한다. 그래서 뼈대를 먼저 그리고
// 날짜만 나중에 채울 수 있다.
export function cardModel(d, lastRun) {
  const ready = domainState(lastRun) === 'ready';
  return {
    slug: d.slug, name: d.name, desc: d.desc,
    meta: updatedLabel(lastRun),
    ready,
    href: ready ? `./${d.slug}/` : null,
  };
}

// 네 도메인의 last_run 을 **동시에** 받는다.
//
// 예전에는 for 루프 안에서 하나씩 await 하고 받는 즉시 카드를 붙였다. 왕복이 직렬로
// 네 번 일어나 카드가 뚝뚝 끊어지며 나타났다 — 왕복 200ms 면 마지막 카드가 0.8초
// 뒤에 떴다. 폰처럼 지연이 큰 회선에서 특히 도드라진다.
export function 갱신상태(load, domains = DOMAINS) {
  return Promise.all(domains.map((d) => load(`./${d.slug}/data/last_run.json`)));
}
