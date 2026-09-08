// core 를 감싸기만 한다. 로직을 여기 두면 /mcp 를 얹을 때 두 번 짜게 된다.
//
// LLM 호출 횟수 규율(설계 §5-1, task-12 규칙 2):
//   메타한계 · 범위밖  → 1회 (1패스 분해만. 카드 자체가 이미 답이라 2패스 서술이 없다)
//   나머지 넷          → 2회 (1패스 분해 + 2패스 서술)
//   사용자가 슬롯을 고쳐 보내면(유형·슬롯이 이미 주어지면) 1패스를 건너뛰어 그만큼 준다.

import { ask } from '../core/ask.mjs';
import { verify } from '../core/verify.mjs';
import { normalize } from '../core/classify.mjs';

export const quotaKey = (ip, today) => `q:${ip}:${today}`;

export async function checkQuota(kv, ip, today, limit) {
  const k = quotaKey(ip, today);
  const used = Number((await kv.get(k)) ?? 0);
  if (used >= limit) return { 허용: false, 남음: 0 };
  await kv.put(k, used + 1, { expirationTtl: 60 * 60 * 48 });
  return { 허용: true, 남음: limit - used - 1 };
}

// 어휘는 카탈로그(capability)에서만 뽑는다 — 하드코딩하면 카탈로그가 늘 때 조용히 낡는다.
async function 어휘(deps) {
  const caps = await deps.db.all('SELECT 주제, 집단축 FROM capability');
  const j = (s) => { try { return JSON.parse(s ?? '[]'); } catch { return []; } };
  return { 주제: [...new Set(caps.flatMap((c) => j(c.주제)))],
           집단축: [...new Set(caps.flatMap((c) => j(c.집단축)))] };
}

// 이 두 유형의 카드는 소스·한계·라우팅·답할수있는질문처럼 이미 완결된 산문으로 채워진다
// (ask.mjs 참조) — LLM 이 다시 "서술" 할 근거 묶음(관측·파생)이 애초에 없다.
// 2패스를 태우면 호출만 늘 뿐 검증할 새 숫자도 없어 낭비다.
const NO_COMPOSE = new Set(['메타한계', '범위밖']);

export async function handleAsk(deps, { 질문, 유형, 슬롯, ip, today }) {
  const q = await checkQuota(deps.kv, ip, today, deps.quota);

  let 저확신 = false;
  // 규칙 3: '이해 카드' 가 "이렇게 이해했습니다" 를 보여주고 고칠 수 있으려면
  // 매핑된 슬롯(카드.슬롯)과 LLM 원문(원문슬롯)이 둘 다 응답에 실려야 한다.
  let 원문슬롯 = 슬롯 ?? null;

  if (!유형 || !슬롯) {
    // 1패스. 사용자가 슬롯을 고쳐 보내면 이 호출을 건너뛴다 → 결정적
    if (!q.허용) {
      // 1패스조차 LLM 이라 할당량을 태운다 — 넘겼으면 분해 없이 메타한계로 떨어뜨린다.
      // 원문슬롯은 LLM 을 부르지 않았으니 아직 없다.
      const 카드 = await ask(deps, { 유형: '메타한계', 슬롯: {}, 한도초과: true });
      카드.원문슬롯 = null;
      return 카드;
    }
    let raw = null;
    try { raw = await deps.llm.classify(질문); } catch { raw = null; }
    const n = normalize(raw, { 어휘: await 어휘(deps) });
    ({ 유형, 슬롯, 저확신 } = n);
    원문슬롯 = n.원문슬롯;
  }

  const 카드 = await ask(deps, { 유형, 슬롯, 저확신, 한도초과: !q.허용 });
  카드.원문슬롯 = 원문슬롯;
  if (!q.허용) return 카드;                       // LLM 만 건너뛴다. 카드는 그대로

  if (NO_COMPOSE.has(유형)) return 카드;          // 규칙 2: 이 둘은 여기서 끝난다 (1회)

  let 문장 = null;
  try { 문장 = await deps.llm.compose(유형, 카드); } catch { 문장 = null; }
  if (!문장) return 카드;

  // 규칙 1: verify 세 번째 인자에 카드.허용텍스트 를 그대로 넘긴다 — 우리가 실제로
  // LLM 에게 넘긴 문장(현상 근거서술·한계·우회경로 등)의 숫자는 인용이지 환각이 아니다.
  const v = verify(문장, 카드.근거 ?? [], 카드.허용텍스트 ?? []);
  if (!v.ok) {
    카드.검증실패 = true;
    카드.검증위반 = v.위반;
    카드.배지 = [...new Set([...(카드.배지 ?? []), '검증실패'])];
    return 카드;                                  // 답변만 버린다. 근거는 남는다
  }
  카드.답변 = 문장.답변;
  카드.한계 = [...new Set([...(카드.한계 ?? []), ...(문장.한계 ?? [])])];
  카드.미확인 = [...new Set([...(카드.미확인 ?? []), ...(문장.미확인 ?? [])])];
  카드.후속질문 = 문장.후속질문 ?? [];
  return 카드;
}
