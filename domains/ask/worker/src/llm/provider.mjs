// 유일한 네트워크 의존. 주입 가능해야 테스트가 나가지 않는다.
// OPENROUTER_API_KEY 는 wrangler secret 으로만 들어온다 — 이 파일에는 키 값이
// 한 글자도 없다. apiKey 와 baseUrl 은 항상 호출부(index.mjs)가 env 에서 읽어 주입한다.

// ★ 슬롯 값 필드에 enum 을 걸지 말 것. Task 0 실측에서 strict json_schema 의 enum 배열이
// provider 문법 컴파일을 느리게 만들어 45초를 넘겼다(웹에서 사용 불가). 어휘 강제는
// core/classify.mjs 의 동의어 표가 코드로 한다. `유형` 의 enum 은 단일 필드라 빠르고 안전하다.
export const SLOT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['유형', '슬롯', '확신도'],
  properties: {
    유형: { type: 'string',
      enum: ['수치조회', '출처비교', '메타한계', '전망', '원인탐색', '범위밖'] },
    슬롯: {
      type: 'object', additionalProperties: false,
      required: ['주제', '집단축', '지역입도', '시간입도', '기간', '출처'],
      properties: {
        주제: { type: 'string' },
        집단축: { type: 'array', items: { type: 'string' } },
        지역입도: { type: 'string' },
        시간입도: { type: 'string' },
        기간: { type: 'object', additionalProperties: false,
                required: ['from', 'to'],
                properties: { from: { type: 'string' }, to: { type: 'string' } } },
        출처: { type: 'array', items: { type: 'string' } },
      },
    },
    확신도: { type: 'number' },
  },
};

export const ANSWER_SCHEMA = {
  type: 'object', additionalProperties: false,
  // strict 모드는 properties 의 **모든** 키가 required 에 있어야 한다.
  // `후속질문` 이 빠져 있어 스키마가 400 으로 거부됐고, 그래서 2패스가 통째로
  // 실패해 답변이 늘 null 이었다(2026-09-09 배포 후 실측). SLOT_SCHEMA 는
  // 전부 들어 있어 통과했기에 스파이크가 이 결함을 못 봤다.
  required: ['답변', '근거', '한계', '미확인', '후속질문'],
  properties: {
    답변: { type: 'string' },
    근거: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['지표', '기간', '값', '출처'],
      properties: { 지표: { type: 'string' }, 기간: { type: 'string' },
                    값: { type: 'string' }, 출처: { type: 'string' } } } },
    한계: { type: 'array', items: { type: 'string' } },
    미확인: { type: 'array', items: { type: 'string' } },
    후속질문: { type: 'array', items: { type: 'string' } },
  },
};

// Task 0 실측 — 이 정의 블록 하나가 유형 정확도를 1/5 → 6/6 으로 올렸다.
// 같은 모델·같은 스키마에서 프롬프트만 바꾼 결과이므로 줄이지 말 것.
const SYS_CLASSIFY = `한국 고용통계 질문을 분해만 한다. 답하지 않는다.
유형 정의:
- 수치조회: 특정 시점·집단의 값을 묻는다 ("2026년 7월 30대 취업자 몇 명")
- 출처비교: 두 통계의 숫자가 왜 다른지 묻는다 ("경활과 행정통계는 왜 다른가")
- 메타한계: 어떤 통계로 무엇을 볼 수 있는지/없는지 묻는다 ("사업체조사로 연령별을 볼 수 있나")
- 전망: 미래 예측치를 묻는다 ("내년 취업자 전망")
- 원인탐색: 왜 그런 변화가 일어났는지 묻는다 ("청년 사무직은 왜 줄었나")
- 범위밖: 고용통계가 아니다 ("카페 매출")
슬롯 규칙:
- 주제: 한 단어. 취업자·종사자·상시가입자수·실업률·고용률 중 뜻이 맞는 것.
- 집단축: **질문이 집단을 나눠 물을 때만 채운다. 안 나누면 빈 배열.**
  축은 산업·성·연령·직업 넷뿐이다 — **시간(월·연)과 지역은 집단축이 아니다.**
  질문이 특정 값을 가리키면 축 이름이 아니라 그 값을 그대로 적는다.
  "30대 취업자" → ["30대"]   "여성 취업자" → ["여자"]   "연령별 취업자" → ["연령"]
  "2026년 8월 취업자" → **[]** (전체를 묻는 것이지 나눠 묻는 게 아니다)
  값을 축 이름으로 바꾸면 어느 연령대인지가 사라진다.
- 지역입도: 전국·시도·시군구 중 하나. 안 나오면 "전국".
- 시간입도: 월·반기·연 중 하나. **질문에 월이 나오면 "월"이다.** "2026년 7월"은 연이 아니라 월.
- 기간: 월이면 "2026-07", 반기면 "2026S1", 연이면 "2026" 형식. 시작과 끝이 같으면 둘 다 같은 값.
- 출처: 질문이 통계 이름을 말하면 그 코드를 넣는다. 여러 개면 여러 개 다 넣는다.
  eaps ← 경활 · 경제활동인구조사
  est  ← 사업체 · 사업체노동력조사
  ei   ← 행정통계 · 고용행정통계 · 고용보험
  예) "경활이랑 고용행정통계는 왜 달라" → ["eaps","ei"]
  통계 이름이 안 나오면 **빈 배열**. 기관 이름을 지어내지 않는다.
- 확신도: 0과 1 사이.`;
const SYS_COMPOSE =
  '주어진 근거 묶음 안의 값만 인용해 한국어로 답한다. ' +
  '근거에 없는 수치를 절대 만들지 않고, 계산도 하지 않는다(파생값은 이미 들어 있다). ' +
  '인과를 단정하지 않고 상관·선후만 말한다. 한계와 미확인을 반드시 채운다.';

// baseUrl 을 주입으로 받는 이유: 공급자를 갈아끼울 때 코드가 아니라 설정만 바뀌게 한다.
// 실제로 한 번 갈아끼웠다(OpenRouter → OpenAI). 요청·응답 형식이 같은 OpenAI 호환
// 서비스면 wrangler.jsonc 의 ASK_API_BASE 한 줄로 옮겨갈 수 있다.
export function makeLlm({ apiKey, model, baseUrl, fetch: f = fetch }) {
  async function once(system, user, schema, name) {
    const res = await f(`${baseUrl}/chat/completions`, {
      method: 'POST',
      signal: AbortSignal.timeout(20000),
      headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'system', content: system },
                   { role: 'user', content: user }],
        response_format: { type: 'json_schema',
                           json_schema: { name, strict: true, schema } },
      }),
    });
    if (!res.ok) throw new Error(`llm ${res.status}`);
    const body = await res.json();
    return JSON.parse(body.choices[0].message.content);
  }
  // Task 0 실측에서 provider 504(내부 429)가 실제로 났다. 한 번만 다시 건다 —
  // 두 번 이상 끌면 카드가 늦게 나가느니 카드만 내보내는 편이 낫다.
  async function call(system, user, schema, name) {
    try { return await once(system, user, schema, name); }
    catch { return await once(system, user, schema, name); }
  }
  return {
    classify: (질문) => call(SYS_CLASSIFY, 질문, SLOT_SCHEMA, 'slots'),
    compose: (유형, 카드) =>
      call(SYS_COMPOSE,
           `유형: ${유형}\n근거 묶음(JSON):\n${JSON.stringify(카드, null, 1)}`,
           ANSWER_SCHEMA, 'answer'),
  };
}
