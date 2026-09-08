// core 를 감싸기만 한다. 로직을 여기 두면 /mcp 를 얹을 때 두 번 짜게 된다.
//
// LLM 호출 횟수 규율(설계 §5-1 정정판 — "core 왕복" 열과 "LLM" 을 혼동하지 않는다):
//   여섯 유형 모두 LLM 호출 횟수는 같다 — 1패스(슬롯 분해) + 2패스(서술).
//   사용자가 슬롯을 고쳐 보내면(유형·슬롯이 이미 주어지면) 1패스를 건너뛴다 → 1회.
//   확정사항 #4 "LLM 이 답변 전체를 쓴다" 는 유형을 가리지 않는다 — 메타한계·범위밖이야말로
//   "왜 못 주는지" 를 문장으로 설명해야 하는 자리라, 여기서 서술을 생략하면 이 도구의
//   핵심 산출물이 그 두 유형에서만 빠진다. (이전에 있던 NO_COMPOSE 게이트는 철회했다 —
//   자세한 경위는 task-12-report.md 의 "수정 라운드 1" 참조.)

import { ask } from '../core/ask.mjs';
import { verify } from '../core/verify.mjs';
import { normalize } from '../core/classify.mjs';

export const quotaKey = (ip, today) => `q:${ip}:${today}`;

export async function checkQuota(kv, ip, today, limit) {
  const k = quotaKey(ip, today);
  let used;
  try {
    used = Number((await kv.get(k)) ?? 0);
  } catch {
    // KV 가 죽으면 이용량을 셀 수 없다. 관대한 기본값(허용: true)으로 열어 두면 장애가
    // 길어지는 동안 LLM 비용이 무한정 샌다 — 남용 방어가 존재하는 이유가 사라진다.
    // "초과하면 LLM 만 건너뛰고 카드는 그대로 낸다" 는 이 설계의 원칙을 그대로 적용해
    // 확인 실패도 LLM 은 건너뛰되, 사용자가 한도를 다 쓴 것(내일 다시)과 우리 저장소가
    // 죽은 것(잠시 뒤 다시)은 서로 다른 사실이라 별도 신호(`확인불가`)로 가른다.
    return { 허용: false, 남음: 0, 확인불가: true };
  }
  if (used >= limit) return { 허용: false, 남음: 0 };
  try {
    // **문자열로 넘긴다.** Workers KV 의 put() 이 받는 값은
    // string | ArrayBuffer | ArrayBufferView | ReadableStream 뿐이라, 숫자를 넘기면
    // 실물 바인딩이 TypeError 를 던진다. 그 예외를 아래 catch 가 삼키므로 프로덕션에서
    // **모든 요청의 카운트가 안 늘고 IP 할당량이 통째로 무효**가 됐다(최종 리뷰 Critical 1).
    // 테스트가 못 잡은 이유는 가짜 KV 가 String() 을 대신 해 줬기 때문이다 —
    // 그쪽도 실물과 같게 고쳤다(routes.test.mjs 의 memKv).
    await kv.put(k, String(used + 1), { expirationTtl: 60 * 60 * 48 });
  } catch {
    // put 실패는 이번 카운트가 안 늘 뿐이다 — get 으로 이미 한도 안임을 확인했으므로
    // 이번 요청은 통과시킨다. 쓰기 지연 하나로 정상 이용자를 막는 것이 더 나쁘다.
  }
  return { 허용: true, 남음: limit - used - 1 };
}

// 한도초과(사용자가 오늘 몫을 다 씀)와 확인불가(우리 KV 가 죽어 셀 수 없음)는 서로 다른
// 사실이라 뭉개지 않는다 — 필드도 배지도 다르게 낸다. 카드(라우팅·한계 등)는 두 경우 다
// 그대로 나가고, LLM(compose)만 건너뛴다.
function 확인불가표시(카드) {
  카드.할당량확인불가 = true;
  카드.한계 = [...(카드.한계 ?? []), '이용량 확인에 실패해 문장 생성을 건너뛴다'];
  카드.배지 = [...new Set([...(카드.배지 ?? []), '할당량확인불가'])];
  return 카드;
}

// 어휘는 카탈로그(capability)에서만 뽑는다 — 하드코딩하면 카탈로그가 늘 때 조용히 낡는다.
async function 어휘(deps) {
  const caps = await deps.db.all('SELECT 주제, 집단축 FROM capability');
  const j = (s) => { try { return JSON.parse(s ?? '[]'); } catch { return []; } };
  return { 주제: [...new Set(caps.flatMap((c) => j(c.주제)))],
           집단축: [...new Set(caps.flatMap((c) => j(c.집단축)))] };
}

export async function handleAsk(deps, { 질문, 유형, 슬롯, ip, today }) {
  const q = await checkQuota(deps.kv, ip, today, deps.quota);

  let 저확신 = false;
  // 규칙 3: '이해 카드' 가 "이렇게 이해했습니다" 를 보여주고 고칠 수 있으려면
  // 매핑된 슬롯(카드.슬롯)과 LLM 원문(원문슬롯)이 둘 다 응답에 실려야 한다.
  let 원문슬롯 = 슬롯 ?? null;

  if (!유형 || !슬롯) {
    // 1패스. 사용자가 슬롯을 고쳐 보내면 이 호출을 건너뛴다 → 결정적
    if (!q.허용) {
      // 1패스조차 LLM 이라 할당량을 태운다 — 넘겼거나 확인 못 했으면 분해 없이
      // 메타한계로 떨어뜨린다. `한도초과` 는 확인불가일 때 false 로 넘긴다 — 진짜
      // 초과가 아니라서다. 원문슬롯은 LLM 을 부르지 않았으니 아직 없다.
      const 카드 = await ask(deps, { 유형: '메타한계', 슬롯: {}, 한도초과: !q.확인불가 });
      카드.원문슬롯 = null;
      if (q.확인불가) 확인불가표시(카드);
      return 카드;
    }
    let raw = null;
    try { raw = await deps.llm.classify(질문); } catch { raw = null; }
    const n = normalize(raw, { 어휘: await 어휘(deps) });
    ({ 유형, 슬롯, 저확신 } = n);
    원문슬롯 = n.원문슬롯;
  }

  const 카드 = await ask(deps, { 유형, 슬롯, 저확신, 한도초과: !q.허용 && !q.확인불가 });
  카드.원문슬롯 = 원문슬롯;
  if (q.확인불가) 확인불가표시(카드);
  if (!q.허용) return 카드;                       // LLM 만 건너뛴다. 카드는 그대로

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
