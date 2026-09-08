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

export function verify(답변객체, 근거묶음) {
  const allowed = numbersIn(근거묶음);
  const found = [
    ...extractNumbers(답변객체?.답변),
    ...(답변객체?.근거 ?? []).flatMap((g) =>
      typeof g?.값 === 'number' ? [g.값] : extractNumbers(g?.값)),
  ];
  const 위반 = [...new Set(found.filter((n) => !allowed.has(n)))];
  return { ok: 위반.length === 0, 위반 };
}
