// 질문을 색인에 던져 **"이런 출처가 답이 될 수 있다"** 를 도메인별로 낸다.
//
// **여기서는 LLM 을 부르지 않는다** — `deps.llm` 을 아예 안 본다. 요약 문장은 이
// 결과를 재료로 `api/routes.mjs` 가 따로 만든다. 찾기와 문장을 갈라 두면 할당량이
// 떨어지거나 LLM 이 죽어도 출처는 그대로 나간다.
//
// 고용동향만 색인이 아니라 `observation` 조회다. 관측은 문장이 아니라 수치라
// 색인할 본문이 없다 — 대신 같은 모양(제목·스니펫·링크)으로 접어 낸다. 화면이
// 도메인마다 다른 그림을 그리지 않게 하려는 것이다.

import { derive, queryObservations } from '../core/query.mjs';
import { slotsFromText, 도메인적용, 월이동 } from './applies.mjs';

const squash = (s) => String(s ?? '').replace(/\s+/g, '');

// trigram 은 세 글자가 최소 단위다(2026-09-10 실물 D1 실측: '고용'·'임금' 이 0건).
const MIN = 3;
// 도메인당 몇 건까지 보여줄 것인가. 더 보고 싶으면 그 도메인 앱으로 간다.
const LIMIT = 5;
const 폭 = 70;
// SQL 에서 몇 배로 넉넉히 받아 올 것인가. **점수를 JS 에서 다시 매기기 때문이다** —
// SQL 이 딱 LIMIT 만 주면 bm25 가 고른 다섯 건 안에서만 순위를 바꾸게 되고, 정작
// 여러 낱말이 걸린 여섯째 글을 못 본다. 조회 한 번의 값이라 세 배까지는 싸다.
const 여유 = 3;

// 한국어 조사. trigram 은 글자 그대로 맞춰서 '고용률이' 로 던지면 '고용률을' 이
// 안 걸린다 — 뒤에 붙은 조사를 떼야 한다. 긴 것부터 뗀다('에서' 가 '서' 에 먹히지
// 않게). 형태소 분석기를 넣지 않는다: 워커에 무게를 더할 값이 아니고, 덜 떼도
// 부분일치라 대개 걸린다.
const 조사 = ['으로써', '에서는', '으로는', '에게서', '이라는', '에서', '으로', '에게',
              '까지', '부터', '보다', '이나', '이란', '라는', '와의', '과의',
              '은', '는', '이', '가', '을', '를', '의', '에', '도', '만', '와', '과', '로'];

// 글로 찾는 세 도메인. 순서가 곧 화면 순서다.
const 글도메인 = ['reports', 'forecast', 'press', 'catalog'];

export function 용어뽑기(질문) {
  const out = [];
  for (const raw of String(질문 ?? '').split(/[^가-힣A-Za-z0-9]+/)) {
    let t = squash(raw);
    if (!t) continue;
    for (const j of 조사) {
      // 조사를 떼고도 두 글자는 남아야 한다 — '의' 를 떼서 한 글자만 남으면 말이 아니다.
      if (t.length > j.length + 1 && t.endsWith(j)) { t = t.slice(0, -j.length); break; }
    }
    if (t.length < 2) continue;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

// **도메인을 가로질러 비교할 수 있는 점수 하나.**
//
// SQL 이 주는 순위는 두 눈금이다 — MATCH 쪽은 bm25(음수, 문서 길이에 좌우된다),
// LIKE 쪽은 걸린 낱말 수(1 이상의 정수). 눈금이 다르면 도메인끼리 못 섞는다.
// 그래서 돌려받은 행에서 **같은 방식으로 다시 센다**: 낱말 하나가 제목에 있으면 2,
// 본문에만 있으면 1. 질문의 낱말 집합이 모든 도메인에 같으므로 합계가 그대로 비교된다.
//
// 공백을 지우고 맞춘다 — 색인이 그 규칙이라 "청년 고용" 과 "청년고용" 이 같아야 한다.
export function 점수(행, 용어들) {
  const 제목 = squash(행?.제목);
  const 본문 = squash(행?.본문);
  let s = 0;
  for (const t of 용어들 ?? []) {
    const q = squash(t);
    if (!q) continue;
    if (제목.includes(q)) s += 2;
    else if (본문.includes(q)) s += 1;
  }
  return s;
}

// 점수가 같으면 **새 글이 위**다. 같은 점수에서 2014년 초록이 2026년 기사보다 위에
// 오던 것이 "최근 고용상황은?" 같은 질문을 망치던 자리다. 날짜가 없는 글(카탈로그의
// 한계·충돌)은 동점에서 뒤로 가되 탈락하지는 않는다.
const 순위 = (a, b) => (b.점수 - a.점수)
  || String(b.날짜 ?? '').localeCompare(String(a.날짜 ?? ''));

// 기간 슬롯(`YYYY-MM`)을 날짜 열(`YYYY-MM-DD` 또는 `YYYY-MM`)과 비교할 수 있게 늘린다.
// **자리수를 안 맞추면 조용히 틀린다** — `'2026-12-15' <= '2026-12'` 는 거짓이라
// 12월을 물었을 때 12월 글이 통째로 빠진다.
const 날짜아래 = (from) => (from ? `${from}-01` : '');
const 날짜위 = (to) => (to ? `${to}-31` : '');

export function 매치식(용어들) {
  // 따옴표로 감싸지 않으면 FTS5 가 용어를 문법으로 읽어 구문 오류를 낸다.
  // 따옴표는 두 번 써서 이스케이프한다.
  return (용어들 ?? [])
    .map((t) => `"${String(t).replace(/"/g, '""')}"`)
    .join(' OR ');
}

export function 스니펫(본문, 용어들, w = 폭) {
  const s = String(본문 ?? '');
  if (!s) return '';
  // 색인은 공백을 지운 사본이라 "청년 고용" 이 "청년고용" 으로 걸린다. 원문에서
  // 그 자리를 찾으려면 공백을 지운 위치 → 원문 위치 대응표가 필요하다.
  const map = [];
  let 압축 = '';
  for (let i = 0; i < s.length; i += 1) {
    if (!/\s/.test(s[i])) { 압축 += s[i]; map.push(i); }
  }
  let hit = -1;
  for (const t of 용어들 ?? []) {
    const i = 압축.indexOf(squash(t));
    if (i >= 0 && (hit < 0 || i < hit)) hit = i;
  }
  if (hit < 0) return s.length <= w * 2 ? s : `${s.slice(0, w * 2).trim()}…`;
  const at = map[hit];
  const from = Math.max(0, at - Math.floor(w / 2));
  const to = Math.min(s.length, at + w);
  return `${from > 0 ? '…' : ''}${s.slice(from, to).trim()}${to < s.length ? '…' : ''}`;
}

// **두 길로 찾아 합친다.**
//
// trigram 은 세 글자가 최소 단위인데, 한국어에서 가장 중요한 낱말이 하필 두
// 글자다 — 청년·정년·임금·여성·고용. 색인만 쓰면 "청년 고용률" 이라는 질문에서
// `청년` 이 통째로 사라진다. 그래서 세 글자 이상은 색인(MATCH)으로, 두 글자는
// LIKE 로 훑어 합친다. 색인이 4,425행·10MB 남짓이라 전수 훑기가 아직 감당된다 —
// 데이터가 열 배가 되면 다시 잰다.
async function 글조회(deps, 도메인, 용어들, limit, 기간 = { from: '', to: '' }) {
  const 긴것 = (용어들 ?? []).filter((x) => x.length >= MIN);
  const 짧은것 = (용어들 ?? []).filter((x) => x.length < MIN);
  const rows = [];
  const 넉넉히 = limit * 여유;

  // 기간을 물었으면 그 창 밖의 글은 빼되, **날짜 없는 글은 남긴다** — 카탈로그의
  // 한계·충돌은 특정 시점의 글이 아니라 상시 사실이라, 기간을 물을 때마다 그
  // 사실이 사라지면 "왜 못 주는지" 를 말할 근거를 잃는다.
  const 창 = [];
  const 창값 = [];
  if (기간?.from || 기간?.to) {
    const 조건 = ["날짜 = ''"];
    if (기간.from) { 조건.push('날짜 >= ?'); }
    if (기간.to) { 조건.push('날짜 <= ?'); }
    // ('' 이거나) (from 이상 and to 이하)
    const 안 = 조건.slice(1).join(' AND ');
    창.push(`(날짜 = '' OR (${안}))`);
    if (기간.from) 창값.push(날짜아래(기간.from));
    if (기간.to) 창값.push(날짜위(기간.to));
  }
  const 창절 = 창.length ? ` AND ${창.join(' AND ')}` : '';

  const 식 = 매치식(긴것);
  if (식) {
    // bm25 는 색인 열에만 걸린다 — 제목색인(8번째)에 무게를 더 준다.
    // **열이 아홉 개다**(0005 에서 날짜가 들어왔다). 0 의 개수가 어긋나면 무게가
    // 엉뚱한 열에 걸려 순위가 조용히 뒤바뀐다.
    rows.push(...await deps.db.all(
      `SELECT doc_id, 종류, 제목, 본문, 링크, 날짜 FROM doc_fts
        WHERE doc_fts MATCH ? AND 도메인 = ?${창절}
        ORDER BY bm25(doc_fts, 0,0,0,0,0,0,0, 10, 1) LIMIT ?`,
      [식, 도메인, ...창값, 넉넉히]));
  }

  if (짧은것.length) {
    const like = 짧은것.map(() => '본문색인 LIKE ?');
    // **걸린 낱말 수로 세운다.** 두 글자 낱말 중에는 '고용' 처럼 거의 모든 글에
    // 있는 말이 섞여 있어, 정렬하지 않으면 그 하나만 걸린 글이 여러 낱말이 다
    // 걸린 글보다 위로 온다(실측: "정년 연장이 고용에 미치는 영향").
    // 이름을 `점수식` 으로 둔다 — 위의 함수 `점수()` 와 같은 이름이면 읽는 사람이
    // SQL 쪽 세기와 JS 쪽 세기를 같은 것으로 착각한다. 둘은 눈금이 다르다.
    const 점수식 = like.map((c) => `(${c})`).join(' + ');
    const 값 = 짧은것.map((x) => `%${squash(x)}%`);
    // 낱말이 셋 이상이면 **둘 이상 걸려야** 낸다. '고용' 처럼 거의 모든 글에 있는
    // 말 하나만 걸린 글을 "정년 연장" 질문의 답으로 내밀면 묻지 않은 것을 답한
    // 셈이다(실측). 낱말이 한둘뿐이면 그대로 하나만 걸려도 낸다.
    const 최소 = 짧은것.length >= 3 ? 2 : 1;
    rows.push(...await deps.db.all(
      `SELECT doc_id, 종류, 제목, 본문, 링크, 날짜 FROM doc_fts
        WHERE 도메인 = ? AND (${like.join(' OR ')}) AND (${점수식}) >= ?${창절}
        ORDER BY ${점수식} DESC LIMIT ?`,
      [도메인, ...값, ...값, 최소, ...창값, ...값, 넉넉히]));
  }

  // **여기서 순위를 다시 세운다.** SQL 이 준 두 순서(bm25 / 걸린 낱말 수)는 눈금이
  // 달라 섞을 수 없고, 도메인끼리 비교할 수도 없다. 같은 자에 놓고 다시 잰다.
  const 점수붙임 = rows.map((r) => ({ ...r, 점수: 점수(r, 용어들) })).sort(순위);

  // **문서 단위로 추린다.** 초록 한 건이 여러 청크로 쪼개져 있어, 조각 단위로
  // 추리면 다섯 자리가 같은 보고서로 다 차서 다른 보고서를 볼 기회가 사라진다
  // (실측). 두 길로 같은 글이 걸리는 것도 여기서 함께 걸러진다 — 점수가 높은 쪽이
  // 앞에 있으므로 먼저 온 것을 남긴다.
  const 본것 = new Set();
  const out = [];
  for (const r of 점수붙임) {
    // doc_id 는 `reports:kli-10303:초록:0` 꼴이다. 앞 두 마디가 문서를 가리킨다.
    const key = String(r.doc_id ?? `${r.종류}|${r.제목}`).split(':').slice(0, 2).join(':');
    // **제목으로도 추린다.** 같은 보고서가 게시판 둘에 올라가 id 는 다른데 제목이
    // 같은 경우가 있다(실측: "고령 노동과 소득 크레바스" 가 두 번 나왔다).
    const 이름 = `${도메인}|${r.제목 ?? ''}`;
    if (본것.has(key) || 본것.has(이름)) continue;
    본것.add(key);
    본것.add(이름);
    out.push(r);
    if (out.length >= limit) break;
  }
  return out;
}

// observation 의 breakdown 열은 이 셋뿐이다(실측). 직업 축은 값이 한 건도 없다.
const 축_BREAKDOWN = { 연령: 'age', 성: 'sex', 산업: 'industry' };

// **주제가 출처와 계열을 정한다.** 전에는 `source: 'eaps'` 가 박혀 있어서 "종사자수" 를
// 물어도 경활을 조회했고, 계열을 안 걸러 한 출처의 아홉 계열이 섞여 나왔다(2026-09-13
// 배포 후 실측: "최근 고용상황" 카드에 `2026-08 전체` 가 다섯 번 찍혔다 — 취업자·실업자·
// 경제활동인구·인구·고용률이 같은 제목으로 나란히 선 것이다). 세 출처 모두 계열 이름은
// `headcount` 다.
const 주제_계열 = {
  취업자수: { source: 'eaps', series: 'headcount' },
  종사자수: { source: 'est', series: 'headcount' },
  상시가입자수: { source: 'ei', series: 'headcount' },
};

// 추세를 볼 창의 길이(개월). 13이면 **전년동월이 창 안에 들어온다** — 12로 잡으면
// 한 달이 모자라 "작년 같은 달과 비교" 가 창 밖으로 떨어진다.
const 창개월 = 13;

// 창의 시작. 월 셈은 `월이동` 한 곳에만 둔다 — 두 벌이 되면 한쪽만 고쳐 어긋난다.
export const 창시작 = (끝, n = 창개월) => 월이동(끝, -(n - 1));

// 고용동향: 색인이 아니라 관측 조회. 같은 모양으로 접는다.
//
// **관측이 가진 축을 고른다.** 첫 축만 보면 "청년 사무직" 처럼 축이 둘인 질문에서
// 관측에 없는 직업 축을 집어 고용동향이 통째로 0건이 된다 — 연령으로는 낼 수
// 있는데도. 못 내는 축은 버리지 않고 말한다(못 준다와 못 알아들었다는 다르다).

async function 관측조회(deps, 슬롯, limit, { 넓은질문 = false } = {}) {
  const 됨 = (슬롯.집단축 ?? []).filter((a) => a in 축_BREAKDOWN);
  const 안됨 = (슬롯.집단축 ?? []).filter((a) => !(a in 축_BREAKDOWN));
  const 축 = 됨[0] ?? null;
  const 한계 = [];
  if (안됨.length) 한계.push(`${안됨.join('·')}별 관측은 적재돼 있지 않다`);
  if (됨.length > 1) 한계.push(`${됨[0]} 축만 본다 — ${됨.slice(1).join('·')} 과의 교차는 못 낸다`);

  // 주제를 못 알아들었으면 여기까지 오지 않는다(`도메인적용` 이 고용동향을 안 켠다).
  // 그래도 기본값을 둔다 — 표에 없는 주제가 새로 생겨도 조용히 엉뚱한 출처를 읽는
  // 것보다 취업자수로 읽고 그 사실을 슬롯으로 밝히는 편이 낫다.
  const 계열 = 주제_계열[슬롯.주제] ?? 주제_계열.취업자수;
  const 조건 = {
    ...계열,
    breakdown: 축 ? 축_BREAKDOWN[축] : 'total',
    category: 축 ? (슬롯.category[축] ?? null) : null,
  };
  let rows = await queryObservations(deps, {
    ...조건, from: 슬롯.기간.from, to: 슬롯.기간.to, 최신만: true,
  });

  // **넓은 질문에는 한 점이 아니라 창을 준다.** "최근 고용상황은?" 에 최신 한 점만
  // 주면 늘었는지 줄었는지를 말할 수가 없다 — 차이·증감률은 두 점부터 생긴다
  // (`derive` 가 시계열일 때만 만든다). 축이 있거나 기간을 지정한 질문은 건드리지
  // 않는다: 그쪽은 한 시점의 단면을 물은 것이고, 창을 열면 단면이 사라진다.
  if (넓은질문 && rows.length) {
    const 끝 = rows[rows.length - 1].period;
    const from = 창시작(끝);
    if (from) {
      rows = await queryObservations(deps, { ...조건, from, to: 끝 });
      한계.push(`${from}~${끝} 추세를 본다`);
    }
  }

  // `derive` 는 한국어 열 이름(값·기간)을 읽는다. SQL 행은 영어라 여기서 옮긴다 —
  // 안 옮기면 파생이 조용히 전부 NaN 이 된다.
  const 파생 = derive(rows.map((o) => ({ 값: o.value, 기간: o.period })),
    { 단위: rows[0]?.unit }) ?? {};

  return {
    // 화면은 **최신부터** 본다. 조회는 period 오름차순이라 그대로 자르면 창의 가장
    // 오래된 다섯 점이 카드에 박힌다.
    결과: [...rows].reverse().slice(0, limit).map((o) => ({
      제목: `${o.period} ${축 ? `${축} ${o.category}` : '전체'}`,
      스니펫: `${o.value}${o.unit ?? ''}${o.yoy != null ? ` (전년대비 ${o.yoy})` : ''}`,
      링크: o.release_url ?? '',
      근거유형: '관측',
    })),
    한계,
    // 요약 문장의 재료다. 화면은 안 읽는다 — 숫자는 LLM 이 만들지 않고 이 집합에서만
    // 인용되며, `verify` 가 그 집합으로 대조한다.
    관측: rows,
    파생,
  };
}

export async function lookup(deps, 질문, { limit = LIMIT, now } = {}) {
  const 용어들 = 용어뽑기(질문);
  // **오늘을 넘긴다.** 안 넘기면 '작년'·'지난달' 을 풀 수 없어 기간이 늘 비고,
  // 기간이 비면 오래된 글이 최신 글과 같은 자격으로 올라온다.
  const 슬롯 = slotsFromText(질문, { now });
  const 적용 = 도메인적용(질문, { now });

  const 묶음 = [];
  const 해당없음 = 적용.filter((a) => !a.적용).map((a) => ({ 도메인: a.도메인, 사유: a.사유 }));
  const 켜진 = new Set(적용.filter((a) => a.적용).map((a) => a.도메인));

  for (const 도메인 of 글도메인) {
    if (!켜진.has(도메인)) continue;
    const rows = await 글조회(deps, 도메인, 용어들, limit, 슬롯.기간);
    묶음.push({
      도메인,
      결과: rows.map((r) => ({
        제목: r.제목, 스니펫: 스니펫(r.본문, 용어들),
        링크: r.링크 ?? '', 근거유형: r.종류,
        날짜: r.날짜 ?? '', 점수: r.점수 ?? 0,
      })),
      ...(rows.length ? {} : { 사유: '이 질문으로 걸리는 글이 없다' }),
    });
  }

  // **도메인 순서를 점수로 정한다.** 전에는 `글도메인` 배열 순서가 곧 화면 순서라,
  // 질문과 상관없이 연구보고서가 늘 맨 위였다. 이제 제일 잘 걸린 글을 가진 도메인이
  // 위로 온다. 점수가 같으면 새 글을 가진 쪽, 그래도 같으면 원래 순서다.
  const 최고 = (m) => Math.max(0, ...(m.결과 ?? []).map((x) => x.점수 ?? 0));
  const 최신 = (m) => (m.결과 ?? []).reduce((a, x) => (String(x.날짜 ?? '') > a ? String(x.날짜) : a), '');
  묶음.sort((a, b) => (최고(b) - 최고(a))
    || 최신(b).localeCompare(최신(a))
    || (글도메인.indexOf(a.도메인) - 글도메인.indexOf(b.도메인)));

  if (켜진.has('employment')) {
    // **고용동향은 순위 경쟁에 넣지 않고 맨 앞에 둔다.** 관측은 낱말로 걸린 게
    // 아니라 조건으로 조회한 것이라 글과 비교할 공통 눈금이 없다(점수를 지어내면
    // 그 순위는 뜻이 없다). 그리고 숫자가 답의 뼈대라 앞에 있는 것이 맞다.
    const 넓은질문 = !(슬롯.집단축 ?? []).length && !슬롯.기간.from && !슬롯.기간.to;
    const { 결과, 한계, 관측, 파생 } = await 관측조회(deps, 슬롯, limit, { 넓은질문 });
    const 사유 = [...한계, ...(결과.length ? [] : ['이 조건의 관측이 적재돼 있지 않다'])];
    묶음.unshift({
      도메인: 'employment', 결과, 관측, 파생,
      ...(사유.length ? { 사유: 사유.join(' · ') } : {}),
    });
  }

  return { 질문: String(질문 ?? ''), 슬롯, 묶음, 해당없음 };
}
