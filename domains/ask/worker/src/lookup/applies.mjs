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

// 연-월 · 연도. 오늘 날짜를 지어내지 않는다 — '작년'·'최근' 은 여기서 안 푼다.
// 기간이 비면 조회가 최신 한 시점을 내고, 무엇을 기준으로 답했는지 밝힌다.
const 연월 = /(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*월?/;
const 연도 = /(\d{4})\s*년/;

export function slotsFromText(질문) {
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
    기간: 기간뽑기(질문),
  };
}

function 기간뽑기(질문) {
  const s = String(질문 ?? '');
  const m = 연월.exec(s);
  if (m) {
    const mm = String(Number(m[2])).padStart(2, '0');
    return { from: `${m[1]}-${mm}`, to: `${m[1]}-${mm}` };
  }
  const y = 연도.exec(s);
  if (y) return { from: `${y[1]}-01`, to: `${y[1]}-12` };
  return { from: '', to: '' };
}

// 글로 찾는 도메인들. 질문 원문을 색인에 그대로 던지므로 주제 어휘를 몰라도 된다 —
// '정년'·'최저임금' 처럼 주제 표에 없는 정책 낱말이 오히려 여기서 걸린다.
const 글도메인 = ['reports', 'forecast', 'catalog'];

export function 도메인적용(질문) {
  const 있음 = squash(질문).length > 0;
  const 슬롯 = slotsFromText(질문);
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
