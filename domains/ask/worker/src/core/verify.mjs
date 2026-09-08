// 답변에 등장하는 모든 숫자가 코드가 넘긴 집합 안에 있는지 대조한다.
// 이 저장소에 이미 있는 패턴이다 — tools/rationales.py 가 LLM 이 지목한 문장이
// 원문에 실재하는지 대조한다.

import { numbersIn } from './query.mjs';

// 연·기간 토큰(2025S1, 2026-07, 2026년)은 숫자로 세지 않는다.
const PERIOD = /\b(19|20)\d{2}(년|[-–]\d{1,2}|S[12]|H[12]|Q[1-4])?\b/g;

// 라벨은 숫자로 세지 않는다. **값이 아니라 이름이다** — 기간이 값이 아니라 좌표인 것과
// 같다. 카테고리를 정확히 집어도 답변이 "30대 취업자" 라고 쓰는 순간 30 이 위반으로
// 잡히던 것을 막는다.
//
// 가리는 것 — 집단 라벨: `30대` · `30~39세`/`30-39세` · `15세 이상`/`65세 미만`
//             시점 라벨: `7월` · `3분기` · `4반기` · `3년`(연도는 PERIOD 가 먼저 가린다)
// **절대 안 가리는 것** — `600천명` · `1200건` · `-2.3%` · 소수점 있는 수.
//   그게 우리가 재서 낸 값이고, 가리면 환각 방어에 구멍이 뚫린다.
//   **이 두 정규식에 단위 글자(천명·건·%)가 한 글자도 없다는 것이 그 경계다.**
//
// 두 가지 함정을 막아 뒀다.
//   ① 긴 패턴이 짧은 패턴에 먼저 먹힌다 — 범위형(`\d+~\d+세`)을 맨 앞에 둬
//      `30~39세` 가 `39세` 로 쪼개지지 않게 한다.
//   ② 소수의 뒷자리가 라벨로 먹힌다 — `(?<![\d.])` 로 막는다. 없으면 `1.5년` 이
//      `5년` 만 가려져 `1` 이 남고, 원래 값 1.5 가 사라진 채 엉뚱한 1 이 대조된다.
const COHORT = /(?<![\d.])(?:\d+\s*[~\-–]\s*\d+세|\d+세\s*(?:이상|미만|이하|초과)?|\d+대)/g;
const TERM = /(?<![\d.])\d+(?:분기|반기|월|년)/g;

const NUM = /[-−+]?\d+(?:\.\d+)?/g;

export function extractNumbers(text) {
  // PERIOD 를 먼저 돌린다 — `2026년 7월` 에서 연도를 걷어낸 뒤 `7월` 을 가려야 한다
  const masked = String(text ?? '')
    .replace(PERIOD, ' ').replace(COHORT, ' ').replace(TERM, ' ');
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
