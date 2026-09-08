// 답변에 등장하는 모든 숫자가 코드가 넘긴 집합 안에 있는지 대조한다.
// 이 저장소에 이미 있는 패턴이다 — tools/rationales.py 가 LLM 이 지목한 문장이
// 원문에 실재하는지 대조한다.

import { numbersIn } from './query.mjs';

// 연·기간 토큰(2025S1, 2026-07, 2026년)은 숫자로 세지 않는다.
const PERIOD = /\b(19|20)\d{2}(년|[-–]\d{1,2}|S[12]|H[12]|Q[1-4])?\b/g;
const NUM = /[-−+]?\d+(?:\.\d+)?/g;

export function extractNumbers(text) {
  const masked = String(text ?? '').replace(PERIOD, ' ');
  return (masked.match(NUM) ?? [])
    .map((s) => Number(s.replace('−', '-')))
    .filter((n) => Number.isFinite(n));
}

// extractNumbers 와 같은 규칙으로, 문자열 여러 개(또는 하나)에서 숫자를 모은다.
export function numbersInText(strings) {
  const list = Array.isArray(strings) ? strings : [strings];
  const s = new Set();
  for (const t of list) for (const n of extractNumbers(t)) s.add(n);
  return s;
}

export function verify(답변객체, 근거묶음, 허용텍스트 = []) {
  // 우리가 LLM 에게 준 문장(근거서술·한계·검정력_주석·우회경로·compare 설명 등)의 숫자는
  // 인용이지 환각이 아니다 — 근거 집합에 없다는 이유만으로 위반 처리하면 그 문장을
  // 그대로 인용한 정상 답변까지 튕겨 나간다. 호출부는 "우리가 실제로 넘긴 문장"만
  // 허용텍스트에 담아야 한다 — 그 규율은 이 함수가 아니라 호출부(Task 11·12)의 책임이다.
  const allowed = new Set([
    ...numbersIn(근거묶음),
    ...numbersInText(허용텍스트),
  ]);
  const found = [
    ...extractNumbers(답변객체?.답변),
    ...(답변객체?.근거 ?? []).flatMap((g) =>
      typeof g?.값 === 'number' ? [g.값] : extractNumbers(g?.값)),
  ];
  const 위반 = [...new Set(found.filter((n) => !allowed.has(n)))];
  return { ok: 위반.length === 0, 위반 };
}
