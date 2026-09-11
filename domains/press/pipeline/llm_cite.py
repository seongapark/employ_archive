# -*- coding: utf-8 -*-
"""기사가 그 회차 보도자료를 인용했는지 LLM 이 판정한다.

규칙이 아니라 LLM 을 주 판정으로 두는 이유는 규칙이 **조용히** 틀리기 때문이다.
2026-09-08 실측에서 두 번 그랬다 — 보도자료 수치를 지문으로 쓰는 규칙이 6월분
진짜 기사 33건을 떨어뜨렸고, 소수점(`2.6%`)에서 문장이 갈려 지표와 증감이
따로 놀았다. 둘 다 예외 없이 그럴듯한 숫자를 냈다.

판정과 근거를 함께 받는다. 근거가 없으면 왜 틀렸는지 아무도 못 본다.
공급자는 있는 키를 쓴다(Anthropic → OpenRouter → OpenAI) — 프롬프트와 파싱은
어느 쪽이든 같고, 요청 모양만 `payload_for` 가 맞춘다.

**논조도 같은 호출에서 받는다.** 고정 어휘표로는 못 센다는 것이 실측으로
드러났다 — 어휘표 14개('빨간불'·'한파'·'훈풍'…)는 '26.8월분 인용 73건 중
10건만 잡았고, 정작 그 회차를 이끈 「반등 16 · 호황 8 · 호조 2」는 목록에
없어 '보도자료 밖 표현'으로 흘러갔다. 그 표로 KPI 를 세웠다면 **긍정 우세인
회차를 '부정 우세'로 표시**했을 것이다. 어휘를 늘려도 「구직급여 급증」과
「가입자 급증」을 못 가른다 — 같은 낱말이 주어에 따라 뒤집힌다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple, Sequence

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL_ANTHROPIC = "claude-opus-5"
MODEL_OPENROUTER = "anthropic/claude-opus-5"
MODEL_OPENAI = "gpt-5.5"        # OPENAI_MODEL 로 바꿀 수 있다
MAX_TOKENS = 4000
# OpenAI 의 gpt-5 계열은 답 말고 **추론 토큰**을 따로 쓴다(실측: 기사 1건에
# 답 57 + 추론 53). 같은 4000 으로 두면 20건짜리 배치가 JSON 중간에서 잘린다.
MAX_TOKENS_OPENAI = 16000
TIMEOUT = 180
BATCH = 20                      # 한 번에 판정할 기사 수

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


# 논조 판정값. 이 셋 밖의 답은 에러다 — 모르는 값을 '중립'으로 접으면
# 모델이 딴소리를 해도 화면이 멀쩡해 보인다.
TONES = ('긍정', '부정', '중립')

# 인용의 **무게**. 「수치를 전했나」와 「그 수치가 기사의 본론인가」는 다른 질문이다.
# 실측('26.7월분 후속): 인용 31건 중 「'싼 게 비지떡' 청년 주거 엇박」처럼 주거·주식·
# 수기 기사가 도입부에 통계를 끌어다 쓴 것이 여럿 섞여 있었다. 네이버가 주는 요약에
# 실제로 수치가 있으니 인용은 맞지만, 후속 보도로 세면 「이 회차가 어디까지 번졌나」가
# 부풀어 보인다. 그래서 인용 여부와 무게를 따로 받는다.
FOCUSES = ('주제', '언급')


class Verdict(NamedTuple):
    n: int          # 기사 번호 (1부터)
    cites: bool
    why: str
    tone: str       # 긍정 | 부정 | 중립
    focus: str      # 주제 | 언급 (인용이 아니면 빈 문자열)


def build_prompt(release_label: str, release_date: str, digest: str,
                 arts: Sequence[dict]) -> str:
    lines = []
    for i, a in enumerate(arts, start=1):
        desc = re.sub(r"\s+", " ", a.get("desc", ""))[:200]
        lines.append(f'{i}. [{a.get("press","")}] {a["title"]}\n   {desc}')
    listing = "\n".join(lines)
    return f"""고용노동부가 {release_date} 에 「{release_label}」 보도자료를 냈다.

그 보도자료의 요지:
{digest}

아래는 그 무렵 나온 기사들이다. 각 기사가 **이 보도자료가 발표한 통계를 전한
기사인지** 판정하라.

판정 기준:
- 이 보도자료의 수치·증감을 전하면 인용이다. 출처를 안 밝혀도 인용이다
  (수치만 받아쓰는 기사가 많다).
- 같은 낱말(고용보험·구직급여)을 써도 **다른 것을 말하면 인용이 아니다** —
  제도 개편, 법률 해설, 국회 심의, 개인 수기, 다른 기관의 조사, 지자체 사업.
- 여러 보도자료를 묶은 헤드라인 모음·[오늘의 신문] 류는 인용이 아니다.
- 애매하면 인용이 아닌 쪽으로 판정하라. 다만 그 이유를 적어라.

기사 목록:
{listing}

그리고 각 기사의 **논조**를 함께 판정하라. 지표가 좋고 나쁜지가 아니라
**제목·요약이 노동시장을 어떻게 그리는가**다:
- "긍정" — 나아지고 있다고 그린다. 반등·호황·회복·증가 전환·훈풍.
- "부정" — 나빠지고 있다고 그린다. 한파·감소·부진·역주행·빙하기·최악.
- "중립" — 수치만 전하거나, 좋고 나쁨이 섞여 어느 쪽도 아니다.

같은 낱말이라도 **무엇이 늘고 줄었는지**를 보라. 「구직급여 신청 급증」은
부정이고 「가입자 급증」은 긍정이다. 인용이 아닌 기사도 논조는 판정하라.

인용이라면 그 수치가 기사에서 **어떤 무게**인지도 판정하라(`focus`):
- "주제" — 이 통계를 전하는 것이 기사의 본론이다. 제목이나 첫 문단이 이 수치를
  다루고, 통계를 빼면 기사가 성립하지 않는다.
- "언급" — 다른 주제(주거·주식·수기·정책 논쟁·기업 분석)를 말하면서 이 통계를
  근거로 한두 줄 끌어다 썼을 뿐이다. 통계를 빼도 기사는 남는다.
인용이 아니면 `focus` 는 빈 문자열("")로 둬라.

각 기사마다 한 줄씩, JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"n": 1, "cites": true, "why": "8월 가입자 27만8천명 증가를 전함", "tone": "긍정", "focus": "주제"}}]

`why` 는 20자 안팎으로 짧게. 인용이 아니면 무엇을 다룬 기사인지 적어라.
`tone` 은 긍정·부정·중립 중 하나만 쓴다.
"""


def parse_response(body: str, n_expected: int) -> list[Verdict]:
    """JSON 배열을 읽는다. 못 읽으면 ValueError — 조용히 넘기지 않는다."""
    text = body.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"응답을 JSON 으로 읽지 못했다: {body[:200]}") from exc
    if not isinstance(rows, list):
        raise ValueError(f"배열이 아니다: {body[:200]}")
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"항목이 객체가 아니다: {row!r}")
        try:
            n = int(row["n"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"n 을 읽지 못했다: {row!r}") from exc
        if not (1 <= n <= n_expected):
            raise ValueError(f"n 이 범위 밖이다({n}, 1~{n_expected}): {row!r}")
        if n in seen:
            raise ValueError(f"n 이 중복이다: {n}")
        seen.add(n)
        if "cites" not in row:
            raise ValueError(f"cites 가 없다: {row!r}")
        if "tone" not in row:
            raise ValueError(f"tone 이 없다: {row!r}")
        tone = str(row["tone"]).strip()
        if tone not in TONES:
            raise ValueError(f"tone 이 {'·'.join(TONES)} 가 아니다({tone!r}): {row!r}")
        cites = bool(row["cites"])
        if "focus" not in row:
            raise ValueError(f"focus 가 없다: {row!r}")
        focus = str(row["focus"]).strip()
        if cites and focus not in FOCUSES:
            raise ValueError(f"focus 가 {'·'.join(FOCUSES)} 가 아니다({focus!r}): {row!r}")
        if not cites:
            focus = ''          # 인용이 아니면 무게를 따질 것이 없다
        out.append(Verdict(n, cites, str(row.get("why", "")).strip(), tone, focus))
    missing = sorted(set(range(1, n_expected + 1)) - seen)
    if missing:
        # 빠진 기사를 조용히 '인용 아님' 으로 두면 누락이 안 보인다.
        raise ValueError(f"판정이 빠진 기사가 있다: {missing}")
    return sorted(out)


def provider() -> tuple[str, str, dict] | None:
    """(url, model, headers) — 있는 키를 쓴다. 없으면 None.

    **순서가 곧 선호다.** 인용 판정의 품질은 `claude-opus-5` 로 실측했으므로
    (규칙과의 불일치 7건이 전부 LLM 이 맞았다) 그 모델을 쓸 수 있으면 그걸 쓴다.
    OpenAI 는 마지막이다 — 같은 프롬프트로 돌지만 그 실측을 물려받지는 않는다.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return (ANTHROPIC_URL, MODEL_ANTHROPIC,
                {"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return (OPENROUTER_URL, MODEL_OPENROUTER,
                {"Authorization": f"Bearer {key}", "content-type": "application/json"})
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        model = os.environ.get("OPENAI_MODEL", "").strip() or MODEL_OPENAI
        return (OPENAI_URL, model,
                {"Authorization": f"Bearer {key}", "content-type": "application/json"})
    return None


def payload_for(url: str, model: str, prompt: str) -> dict:
    """공급자마다 토큰 한도의 이름이 다르다.

    OpenAI 의 gpt-5 계열은 `max_tokens` 를 **거부한다**(400: Unsupported
    parameter). 이름만 다른 게 아니라 뜻도 다르다 — 추론 토큰까지 그 한도에서
    쓰므로 한도를 넉넉히 잡아야 답이 안 잘린다.
    """
    msg = [{"role": "user", "content": prompt}]
    if "anthropic.com" in url:
        return {"model": model, "max_tokens": MAX_TOKENS, "messages": msg}
    if "openai.com" in url:
        return {"model": model, "max_completion_tokens": MAX_TOKENS_OPENAI,
                "messages": msg}
    return {"model": model, "max_tokens": MAX_TOKENS, "messages": msg}


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError("ANTHROPIC_API_KEY · OPENROUTER_API_KEY · OPENAI_API_KEY "
                           "중 아무것도 없다")
    url, model, headers = got
    resp = requests.post(url, headers=headers, json=payload_for(url, model, prompt),
                         timeout=TIMEOUT)
    if resp.status_code != 200:
        raise ValueError(f"API 가 {resp.status_code} 를 돌려줬다: {resp.text[:300]}")
    data = resp.json()
    try:
        if "content" in data:                       # Anthropic Messages
            return "".join(b.get("text", "") for b in data["content"])
        return data["choices"][0]["message"]["content"]   # OpenAI 호환
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"200 응답인데 형식이 예상과 다르다: {resp.text[:300]}") from exc


def judge(release_label: str, release_date: str, digest: str, arts: Sequence[dict],
          *, call: Callable[[str], str] | None = None,
          log: Callable[[str], None] = print) -> list[Verdict]:
    """기사 전체를 BATCH 씩 나눠 판정한다. 번호는 전체 기준으로 돌려준다."""
    call = call or _call_api
    out = []
    for start in range(0, len(arts), BATCH):
        chunk = list(arts[start:start + BATCH])
        log(f"  판정 {start + 1}~{start + len(chunk)} / {len(arts)}")
        got = parse_response(
            call(build_prompt(release_label, release_date, digest, chunk)), len(chunk))
        out.extend(Verdict(v.n + start, v.cites, v.why, v.tone, v.focus) for v in got)
    return out
