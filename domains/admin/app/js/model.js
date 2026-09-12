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

// ── 도메인 현황 ──────────────────────────────────────────────────────
// 다섯 도메인이 매일 last_run.json 을 쓴다. 형식이 저마다 다르고(reports 만
// `at`, 나머지는 `run_at`), 판정 실패처럼 조용히 멈춰도 워크플로는 성공으로
// 남는다(domains/reports/pipeline/recommend.py). 이 구역이 유일한 감시망이라
// 형식이 바뀌었는데 0 을 보여주며 "정상"이라 하면 그게 더 위험하다 — 그래서
// 어댑터가 기대한 필드를 못 찾으면 값을 지어내지 않고 형식오류로 표시한다.
export const 도메인목록 = 순서.filter((k) => k !== 'hub');

// 마지막 실행이 얼마나 오래됐는지(시간). `지금` 을 주입받아 테스트가 시계에
// 안 매인다. 못 읽는 시각이면 null — 0시간 전으로 지어내지 않는다.
export function 경과시간(at, 지금 = Date.now()) {
  if (typeof at !== 'string' || !at) return null;
  const t = Date.parse(at);
  if (Number.isNaN(t)) return null;
  return Math.max(0, (지금 - t) / 3_600_000);
}

// 수집기 계열 어댑터(employment·forecast 공용) — 둘 다
// { run_at, collectors:{...}, conflicts:[], errors:[] } 모양이다.
function 어댑터_수집기계열(j) {
  if (!j || typeof j.run_at !== 'string' || typeof j.collectors !== 'object'
      || j.collectors === null || Array.isArray(j.collectors)
      || !Array.isArray(j.errors)) return null;
  const 실패 = Object.entries(j.collectors)
    .filter(([, v]) => v && v.ok === false).map(([k]) => k);
  const 충돌 = Array.isArray(j.conflicts) ? j.conflicts.length : 0;
  const 경고 = [];
  if (실패.length) 경고.push(`수집기 실패: ${실패.join(', ')}`);
  if (충돌) 경고.push(`충돌 ${충돌}건`);
  return {
    실행시각: j.run_at,
    지표: [{ 라벨: '수집기 실패', 값: 실패.length }, { 라벨: '오류', 값: j.errors.length }],
    경고,
  };
}

function 어댑터_press(j) {
  if (!j || typeof j.run_at !== 'string' || typeof j.rounds !== 'number') return null;
  return { 실행시각: j.run_at, 지표: [{ 라벨: '회차', 값: j.rounds }], 경고: [] };
}

function 어댑터_ask(j) {
  if (!j || typeof j.run_at !== 'string' || !j.catalog
      || typeof j.catalog.ok !== 'boolean') return null;
  const 경고 = j.catalog.ok ? [] : ['카탈로그 갱신 실패'];
  return {
    실행시각: j.run_at,
    지표: [{ 라벨: '카탈로그', 값: j.catalog.ok ? '정상' : '실패' }],
    경고,
  };
}

// reports 만 `at` 이고, 전량 수록(reports) 대비 판정 수(recommend.judged)의
// 차이가 미판정이다. recommend 블록이 아예 없으면(옛 형식이거나 한 번도
// 성공적으로 안 돈 경우) 그 사실 자체를 알린다.
function 어댑터_reports(j) {
  if (!j || typeof j.at !== 'string' || typeof j.boards !== 'object'
      || j.boards === null || Array.isArray(j.boards)
      || typeof j.reports !== 'number') return null;
  const 실패게시판 = Object.entries(j.boards)
    .filter(([, v]) => v && v.ok === false).map(([k]) => k);
  const 미등록 = Array.isArray(j.unregistered) ? j.unregistered.length : 0;
  const 지표 = [{ 라벨: '게시판 실패', 값: 실패게시판.length }, { 라벨: '전체 보고서', 값: j.reports }];
  const 경고 = [];
  if (실패게시판.length) 경고.push(`게시판 실패: ${실패게시판.join(', ')}`);
  if (미등록) 경고.push(`미등록 게시판 ${미등록}건`);

  const 추천 = j.recommend;
  if (!추천 || typeof 추천.judged !== 'number') {
    지표.push({ 라벨: '미판정', 값: '판정 기록 없음' });
    경고.push('판정 기록 없음');
  } else {
    const 미판정 = Math.max(j.reports - 추천.judged, 0);
    지표.push({ 라벨: '미판정', 값: 미판정 });
    if (추천.error) 경고.push(`판정 실패: ${추천.error}`);
    if (미판정 > 0) 경고.push(`미판정 ${미판정}건`);
  }
  return { 실행시각: j.at, 지표, 경고 };
}

const 어댑터모음 = {
  employment: 어댑터_수집기계열,
  forecast: 어댑터_수집기계열,
  press: 어댑터_press,
  ask: 어댑터_ask,
  reports: 어댑터_reports,
};

// 원본 = { employment: json|null, press: ..., ... } — null 은 api.js 가
// 가져오기 자체에 실패했다는 뜻(404·네트워크 오류). json 은 있는데 어댑터가
// 못 읽으면 형식오류다. 두 경우를 이유로 구분해 보여준다 — 전자는 배포·주소
// 문제, 후자는 그 도메인이 last_run.json 모양을 바꿨다는 신호라 원인이 다르다.
export function 도메인현황(원본, 지금 = Date.now()) {
  return 도메인목록.map((키) => {
    const 기본 = { 키, 이름: 이름[키] ?? 키 };
    const 항목 = 원본?.[키];
    if (항목 == null) {
      return { ...기본, 형식오류: true, 이유: '불러오지 못함',
        실행시각: null, 경과시간: null, 지표: [], 경고: [] };
    }
    const 파싱 = 어댑터모음[키](항목);
    if (!파싱) {
      return { ...기본, 형식오류: true, 이유: '형식을 못 읽음',
        실행시각: null, 경과시간: null, 지표: [], 경고: [] };
    }
    const 경과 = 경과시간(파싱.실행시각, 지금);
    const 경고 = [...파싱.경고];
    if (경과 !== null && 경과 >= 24) 경고.unshift(`${Math.floor(경과)}시간째 안 돌았다`);
    return { ...기본, 형식오류: false, 이유: null,
      실행시각: 파싱.실행시각, 경과시간: 경과, 지표: 파싱.지표, 경고 };
  });
}
