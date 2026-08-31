// 허브의 순수 로직. DOM도 네트워크도 건드리지 않는다.

// 허브는 도메인 목록만 알고 내용은 모른다. 도메인이 사라지면 last_run.json이
// 404가 되어 자동으로 '준비중'이 되고, 붙으면 자동으로 살아난다.
export const DOMAINS = [
  { slug: 'forecast', name: '전망', desc: '기관별 고용 전망치' },
  { slug: 'employment', name: '고용동향', desc: '경활·사업체·고용행정통계 비교' },
  { slug: 'supply', name: '인력수급', desc: '중장기 인력수급전망' },
  { slug: 'economy', name: '경제동향', desc: '거시 지표 동향' },
];

export function domainState(lastRun) {
  return lastRun ? 'ready' : 'pending';
}

// last_run.json의 실제 필드명은 run_at 이다 (수집기가 기록하는 실행 시각).
export function updatedLabel(lastRun) {
  const at = lastRun && lastRun.run_at;
  if (!at) return '준비중';
  return `${at.slice(5, 7)}.${at.slice(8, 10)} 갱신`;
}
