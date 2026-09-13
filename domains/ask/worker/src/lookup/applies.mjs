// 질문 문자열에서 슬롯을 뽑고, 어느 도메인을 보여줄지 정한다.
//
// **LLM 을 부르지 않는다.** `classify.mjs` 의 동의어 표는 이미 "한국어 낱말 →
// 카탈로그 어휘" 표다. 질문을 그 표에 통과시키면 주제·축·카테고리가 나온다.
// 결정적이고 공짜다 — 대신 표에 없는 표현은 못 알아듣고, 그 사실을 사유로 낸다.
//
// 표를 여기에 다시 적지 않는다. 두 벌이 되면 한쪽만 늘어나 조용히 어긋난다
// (이 도메인에서 실제로 그렇게 어긋나 "여성 취업자" 가 메타한계로 떨어진 적이 있다).

import { 주제_SYN, 카테고리_SYN } from '../core/classify.mjs';

// 공백을 지운 사본끼리 맞춘다. 사람은 "고용 보험" 이라고도 쓰고 "고용보험" 이라고도
// 쓴다 — FTS 색인에서 쓰는 규칙과 같다.
const squash = (s) => String(s ?? '').replace(/\s+/g, '');

// **긴 열쇠부터 맞힌다.** '고용보험' 안에 '고용' 이 들어 있어, 짧은 것부터 맞히면
// 상시가입자수가 취업자수로 둔갑해 엉뚱한 통계를 조회한다.
const 긴것부터 = (표) => Object.keys(표).sort((a, b) => b.length - a.length);

const 주제열쇠 = 긴것부터(주제_SYN);
const 카테고리열쇠 = 긴것부터(카테고리_SYN);

// 연-월 · 연도.
const 연월 = /(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*월?/;
const 연도 = /(\d{4})\s*년/;
const 월단독 = /(\d{1,2})\s*월/;
const 최근몇개월 = /최근\s*(\d{1,2})\s*개월/;

// **상대 표현은 오늘이 있어야 풀린다.** 예전에는 여기서 안 풀어서 "작년"·"지난달" 이
// 통째로 무시됐다. 옛 LLM 경로에서도 같은 자리에서 데였다 — 프롬프트에 오늘이 없어
// "8월" 이 2023-08 으로 갔다. 그때 배운 규칙을 그대로 둔다: **기준은 KST 다.**
const KST = 9 * 60 * 60 * 1000;

export function 오늘KST(now = new Date()) {
  const d = new Date(now.getTime() + KST);
  return { 연: d.getUTCFullYear(), 월: d.getUTCMonth() + 1 };
}

// `YYYY-MM` 을 n 개월 옮긴다. **월을 문자열로 더하지 않는다** — 1월에서 한 달 물러나면
// 0월이 나오고, 12월에 한 달 더하면 13월이 나온다. 통째로 개월 수로 바꿔 셈한다.
export function 월이동(연월문자, n = 0) {
  const m = /^(\d{4})-(\d{1,2})$/.exec(String(연월문자 ?? ''));
  if (!m) return '';
  const t = (Number(m[1]) * 12 + Number(m[2]) - 1) + n;
  if (t < 0) return '';
  return `${String(Math.floor(t / 12)).padStart(4, '0')}-${String((t % 12) + 1).padStart(2, '0')}`;
}

// 연도를 가리키는 상대 표현. 긴 것부터 본다 — '재작년' 안에 '작년' 이 있다.
const 연도상대 = [
  ['재작년', -2], ['내후년', 2], ['작년', -1], ['지난해', -1], ['전년', -1],
  ['올해', 0], ['금년', 0], ['이번해', 0], ['내년', 1], ['명년', 1],
];

export function slotsFromText(질문, { now } = {}) {
  const q = squash(질문);
  const 주제키 = 주제열쇠.find((k) => q.includes(squash(k)));
  const category = {};
  const 집단축 = [];
  for (const k of 카테고리열쇠) {
    if (!q.includes(squash(k))) continue;
    const { 축, code } = 카테고리_SYN[k];
    // 한 축은 한 번만 잡는다. '30대 여성' 처럼 축이 둘이면 둘 다 살린다.
    if (축 in category) continue;
    category[축] = code;
    집단축.push(축);
  }
  return {
    주제: 주제키 ? 주제_SYN[주제키] : '',
    집단축, category,
    기간: 기간뽑기(질문, now),
  };
}

// **'최근' 은 기간으로 풀지 않는다.** 창을 억지로 잡으면(예: 최근 12개월) 그 창 밖의
// 글이 통째로 사라져, 2019년 연구보고서가 답인 질문에서 빈손이 된다. 대신 색인 조회가
// 동점일 때 새 글을 위로 올리고(search.mjs 의 `순위`), 고용동향은 넓은 질문에 추세
// 창을 연다. "최근 N개월" 처럼 **사용자가 창을 직접 말한 경우만** 창으로 푼다.
export function 기간뽑기(질문, now) {
  const s = String(질문 ?? '');

  // ① 연-월을 그대로 쓴 경우가 가장 강하다 — 2026년 8월
  const m = 연월.exec(s);
  if (m) {
    const mm = String(Number(m[2])).padStart(2, '0');
    return { from: `${m[1]}-${mm}`, to: `${m[1]}-${mm}` };
  }

  const 오늘 = 오늘KST(now);
  const 이번달 = `${오늘.연}-${String(오늘.월).padStart(2, '0')}`;

  // ② 사용자가 창을 직접 말한 경우 — 최근 6개월
  const 창 = 최근몇개월.exec(s);
  if (창) {
    const n = Math.max(1, Number(창[1]));
    return { from: 월이동(이번달, -(n - 1)), to: 이번달 };
  }

  // ③ 연도 상대 표현. 달까지 말했으면 그 달만 — "작년 8월"
  const 상대 = 연도상대.find(([낱말]) => s.includes(낱말));
  if (상대) {
    const 연 = 오늘.연 + 상대[1];
    const md = 월단독.exec(s);
    if (md) {
      const mm = String(Number(md[1])).padStart(2, '0');
      return { from: `${연}-${mm}`, to: `${연}-${mm}` };
    }
    return { from: `${연}-01`, to: `${연}-12` };
  }

  // ④ 달을 가리키는 상대 표현
  if (/지난\s*달|전월|지난달/.test(s)) {
    const p = 월이동(이번달, -1);
    return { from: p, to: p };
  }
  if (/이번\s*달|이달|금월|당월/.test(s)) return { from: 이번달, to: 이번달 };

  // ⑤ 연도를 적은 경우
  const y = 연도.exec(s);
  if (y) return { from: `${y[1]}-01`, to: `${y[1]}-12` };

  // ⑥ 달만 적은 경우 — 올해로 읽는다. **아직 오지 않은 달이면 작년이다**:
  // 9월에 "12월 취업자" 를 묻는 사람은 올해 12월(없는 값)이 아니라 작년 12월을 뜻한다.
  const md = 월단독.exec(s);
  if (md) {
    const n = Number(md[1]);
    if (n >= 1 && n <= 12) {
      const 연 = n > 오늘.월 ? 오늘.연 - 1 : 오늘.연;
      const mm = String(n).padStart(2, '0');
      return { from: `${연}-${mm}`, to: `${연}-${mm}` };
    }
  }

  return { from: '', to: '' };
}

// 글로 찾는 도메인들. 질문 원문을 색인에 그대로 던지므로 주제 어휘를 몰라도 된다 —
// '정년'·'최저임금' 처럼 주제 표에 없는 정책 낱말이 오히려 여기서 걸린다.
const 글도메인 = ['reports', 'forecast', 'press', 'catalog'];

export function 도메인적용(질문, { now } = {}) {
  const 있음 = squash(질문).length > 0;
  const 슬롯 = slotsFromText(질문, { now });
  const out = 글도메인.map((도메인) => ({
    도메인,
    적용: 있음,
    ...(있음 ? {} : { 사유: '질문이 비어 있다' }),
  }));
  out.unshift({
    도메인: 'employment',
    적용: 있음 && Boolean(슬롯.주제),
    ...(있음 && 슬롯.주제 ? {} : {
      사유: 있음
        ? '어떤 통계를 볼지 정할 낱말이 질문에 없다 — 취업자·종사자·고용보험 가입자 중 하나가 필요하다'
        : '질문이 비어 있다',
    }),
  });
  return out;
}
