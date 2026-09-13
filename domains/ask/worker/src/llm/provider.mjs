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
// **오늘을 프롬프트에 심는다.** 없으면 LLM 은 학습 시점을 현재로 가정한다 — 실배포
// 화면에서 "8월" 이 2023-08 로, "내년" 이 2024 로 풀려 2027년 전망 11건이 D1 에
// 있는데도 못 꺼냈다. 하드코딩하지 않고 호출 때마다 계산한다(워커 isolate 는 오래
// 산다 — 상수로 굳히면 배포일에 멈춘 달력을 쓰게 된다).
//
// **한국 시각으로 읽는다.** 워커는 UTC 로 도는데 질문하는 사람은 KST 로 산다.
// UTC 로 읽으면 매달 마지막 날 밤 9시간 동안 "이번 달" 이 한 달 밀린다.
const KST = (d) => new Date(d.getTime() + 9 * 60 * 60 * 1000);
const YM = (d) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;

export function sysClassify(오늘 = new Date()) {
  const k = KST(오늘);
  const 연 = k.getUTCFullYear();
  return `오늘: ${YM(k)} (한국 시각)
시점 해석 — 이 날짜를 기준으로 푼다. 학습 시점을 현재로 쓰지 않는다.
- 올해=${연}, 내년=${연 + 1}, 작년=${연 - 1}
- 연도 없는 월은 오늘 기준 **가장 최근에 지난 그 달**이다.
  오늘이 ${YM(k)} 이면 "8월"은 ${연}-08, 아직 오지 않은 달은 작년 것이다.
- "전망"은 올해(${연}) 또는 내년(${연 + 1})이며, 명시가 없으면 **내년(${연 + 1})**이다.

한국 고용통계 질문을 분해만 한다. 답하지 않는다.
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
  **값 하나만 나와도 채운다** — "나눠 묻는다" 는 여러 값을 비교한다는 뜻이 아니다.
  "30대 취업자" → ["30대"]        "여성 취업자" → ["여자"]
  "제조업 취업자" → ["제조업"]     "제조업이 왜 줄었나" → ["제조업"]
  "청년 사무직" → ["청년","사무직"]
  "연령별 취업자" → ["연령"]      (값이 아니라 축 자체를 물으면 축 이름)
  "2026년 8월 취업자" → **[]**    (전체를 묻는 것이지 나눠 묻는 게 아니다)
  값을 축 이름으로 바꾸거나 비우면 **어느 산업·어느 연령인지가 사라진다.**
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
}
const SYS_COMPOSE =
  '주어진 근거 묶음 안의 값만 인용해 한국어로 답한다. ' +
  '근거에 없는 수치를 절대 만들지 않고, 계산도 하지 않는다(파생값은 이미 들어 있다). ' +
  '인과를 단정하지 않고 상관·선후만 말한다. 한계와 미확인을 반드시 채운다.';

// ── 요약: 지금 실제로 쓰이는 유일한 LLM 호출 ──────────────────────────────
//
// **JSON 을 요구하지 않는다.** 필요한 산출물이 문장 하나라서다 — 한계·사유는 이미
// 코드가 만들어 카드에 담아 두었고(관측 창·못 내는 축·해당없음), LLM 이 다시 쓸
// 필요가 없다. 스키마를 끼우는 순간 공급자마다 다른 그 문법이 실패 지점이 되는데,
// 옛 2패스에서 `ANSWER_SCHEMA` 가 strict 위반으로 400 을 내 답변이 늘 null 이었던
// 전례가 있다. 문장 하나면 파싱도 스키마도 없다.
//
// 숫자는 여기서 만들어지지 않는다 — `verify` 가 재료 밖의 숫자를 잡아내면 호출부가
// 문장을 버리고 카드만 남긴다.
function SYS_요약(오늘 = new Date()) {
  const k = KST(오늘);
  return `오늘: ${YM(k)} (한국 시각). 학습 시점을 현재로 쓰지 않는다.

너는 한국 고용통계 아카이브의 검색 결과를 사람이 읽을 문장으로 옮긴다.
주어진 재료(JSON)만 쓴다.

규칙:
- **재료에 있는 숫자만 쓴다.** 없는 숫자를 만들지 않고, 새로 계산하지 않는다
  (차이·증감률은 '파생' 에 이미 들어 있다).
- 인과를 단정하지 않는다. "때문이다" 가 아니라 "함께 나타났다"·"이 시기에" 로 쓴다.
- 재료가 못 주는 것을 감추지 않는다. '사유'·'해당없음' 에 적힌 것은 그대로 말한다.
- 관측 수치가 있으면 **그것부터** 말한다. 보고서·기사는 "무엇을 볼 수 있다" 로 덧붙인다.
- **종류가 '기사' 인 출처는 제목만 있다.** 그 기사가 무슨 내용이었는지 아는 척하지 않고,
  "관련 보도 N건이 있으니 훑어보라" 는 식으로 권한다. 제목을 근거로 쓰지 않는다.
- '비슷한말' 이 붙은 출처는 질문의 말이 아니라 비슷한 말로 찾은 것이다 — 그 사실을 밝힌다.
- 3~5문장. 제목을 나열하지 않는다. 표·목록·머리글 없이 줄글로 쓴다.
- 재료가 비었으면 그렇다고 한 문장으로 말한다. 지어내서 채우지 않는다.`;
}

// Claude(Anthropic Messages API). 요청 형식이 OpenAI 와 다르다 — 키는 `x-api-key`,
// 시스템 프롬프트는 `messages` 가 아니라 top-level `system`, 버전 헤더가 필수다.
//
// `thinking` 을 넘기지 않는다. 파라미터를 늘릴수록 400 으로 통째로 죽을 자리가
// 늘고, 여기서 하는 일은 재료를 문장으로 옮기는 짧은 작업이다.
export function makeClaude({ apiKey, model, baseUrl, fetch: f = fetch, now = () => new Date() }) {
  async function once(재료) {
    const res = await f(`${baseUrl}/messages`, {
      method: 'POST',
      signal: AbortSignal.timeout(20000),
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        max_tokens: 1024,
        system: SYS_요약(now()),
        messages: [{ role: 'user', content: `재료(JSON):\n${JSON.stringify(재료, null, 1)}` }],
      }),
    });
    if (!res.ok) throw new Error(`llm ${res.status}`);
    const body = await res.json();
    // content 는 블록 배열이다. text 블록만 이어 붙인다 — `content[0].text` 로 집으면
    // 앞에 다른 블록이 한 번이라도 오는 날 조용히 빈손이 된다.
    return (body.content ?? [])
      .filter((b) => b?.type === 'text').map((b) => b.text).join('').trim() || null;
  }
  return {
    // 한 번만 다시 건다 — 카드가 늦게 나가느니 카드만 내보내는 편이 낫다(옛 경로와 같은 규율).
    요약: async (재료) => {
      try { return await once(재료); } catch { return await once(재료); }
    },
  };
}

// baseUrl 을 주입으로 받는 이유: 공급자를 갈아끼울 때 코드가 아니라 설정만 바뀌게 한다.
// 실제로 한 번 갈아끼웠다(OpenRouter → OpenAI). 요청·응답 형식이 같은 OpenAI 호환
// 서비스면 wrangler.jsonc 의 ASK_API_BASE 한 줄로 옮겨갈 수 있다.
export function makeLlm({ apiKey, model, baseUrl, fetch: f = fetch, now = () => new Date() }) {
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
    // now() 를 **호출 때마다** 부른다 — isolate 하나가 며칠 살아도 달력이 안 굳는다.
    classify: (질문) => call(sysClassify(now()), 질문, SLOT_SCHEMA, 'slots'),
    compose: (유형, 카드) =>
      call(SYS_COMPOSE,
           `유형: ${유형}\n근거 묶음(JSON):\n${JSON.stringify(카드, null, 1)}`,
           ANSWER_SCHEMA, 'answer'),
  };
}
