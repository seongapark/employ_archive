"""보고서 전문을 주고 지표별 근거 문장을 지목하게 한다.

요약시키지 않는다. 원문 문장을 그대로 옮기게 하고, 옮긴 것이 맞는지는
llm_verify 가 따로 대조한다 — 이 모듈은 검증을 모른다.

쪽을 좁히지 않고 전문을 주는 것이 규칙 방식과의 가장 큰 차이다. 규칙 방식은
표 앞뒤 한 쪽씩만 봤는데, 창을 넓히자 한국은행 집필진 명단이 근거로 뽑혔다
(낱말만 보면 조건을 다 만족한다). LLM 은 그것을 근거로 착각하지 않으므로
BOK 의 진짜 서술이 8·10·11·39·43쪽에 흩어져 있어도 닿는다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple, Sequence

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ANTHROPIC = "claude-sonnet-5"
MODEL_OPENROUTER = "anthropic/claude-sonnet-5"
# 추론(thinking)을 켜는 경로에서는 추론 토큰이 이 예산을 함께 먹는다 —
# 실측(OpenRouter, claude-sonnet-5): 한 회차가 completion 1,491 토큰 중
# 1,191 이 추론이었다. 2000 이면 긴 회차에서 답을 쓸 자리가 안 남아 JSON 이
# 중간에 잘리거나 content 가 통째로 비어 온다. 상한일 뿐이라 넉넉히 잡아도
# 실제로 쓴 만큼만 청구된다.
MAX_TOKENS = 8000

# 정하지 않으면 기본 샘플링이라 같은 입력에 매번 다른 답이 온다 — 쪽번호가
# 24와 23 사이를 오갔고, 응답 형식조차 흔들려 한 회차가 통째로 죽었다
# (백틱 없는 "json" 접두어). 재실행이 "다시 굴리기" 가 아니라 "재현" 이어야
# 사람이 결과를 믿고 읽을 수 있다. 실측: 0 이면 같은 입력에 글자까지 같은
# 답이 오고(2회), 추론(thinking)을 켠 채로도 받아들여진다.
TEMPERATURE = 0
TIMEOUT = 120

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


class Picked(NamedTuple):
    indicator: str
    text: str
    source_page: int


def build_prompt(org: str, title: str, indicators: Sequence[str],
                 pages: Sequence[str]) -> str:
    body = "\n\n".join(f"[{n}쪽]\n{t}" for n, t in enumerate(pages, start=1))
    wanted = ", ".join(indicators)
    return f"""다음은 {org} 의 「{title}」 전문이다.

지표마다 **그 전망을 그렇게 한 이유를 말하는 문장 하나**를 원문에서 찾아라.

대상 지표: {wanted}

규칙:
- 원문을 **한 글자도** 바꾸지 마라. 다듬거나 요약하면 버려진다.
- 이유를 말하는 문장이 없으면 그 지표는 **비워라.** 빈 칸은 정상이고
  지어낸 근거보다 낫다.
- 수치를 다시 말하는 문장은 근거가 아니다("3.2% 성장할 전망" 은 전망이지
  이유가 아니다).
- 표·목차·집필진 명단·각주·참고문헌은 근거가 아니다.
- 그 문장이 실린 쪽번호를 함께 적어라.

JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"indicator": "...", "text": "...", "source_page": 1}}]

{body}
"""


def parse_response(body: str) -> list[Picked]:
    """JSON 배열을 읽는다. 못 읽으면 ValueError — 조용히 넘기지 않는다.

    indicator 값 자체는 여기서 걸러내지 않는다 — 목록에 없는 지표가 와도
    그대로 돌려준다. 걸러내면 select 가 깨끗한 목록을 내놓아, 모델이
    엉뚱한 지표에 문장을 붙였다는 사실을 아무도 못 보게 된다. 그 대조는
    호출자(지표 목록을 아는 쪽)가 하고, 걸러낸 사실을 보고서에 남긴다.
    여기서는 형식만 본다.
    """
    text = body.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        # 형식이 실행마다 흔들린다. 실측: 백틱 없이 "json" 한 줄만 앞에 붙어
        # 온 회차가 있었다(BOK 2026년 5월) — 그때 그 회차가 통째로 죽었다.
        # 배열의 바깥 괄호를 찾아 한 번 더 본다. 배열이 아예 없으면 그대로
        # 세운다 — 무엇이든 읽어내려 하면 지어낸 근거를 통과시키게 된다.
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end < start:
            raise ValueError(f"응답을 JSON 으로 읽지 못했다: {body[:200]}") from exc
        try:
            rows = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            raise ValueError(f"응답을 JSON 으로 읽지 못했다: {body[:200]}") from exc
    if not isinstance(rows, list):
        raise ValueError(f"배열이 아니다: {body[:200]}")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"항목이 객체가 아니다: {row!r}")
        text_ = str(row.get("text", "")).strip()
        if not text_:
            continue  # 근거 없음은 정상이다
        try:
            raw_indicator = row["indicator"]
            if raw_indicator is None:
                # str(None) 은 "None" 이 되어 지표 이름처럼 보인다 —
                # null 은 지표가 아니라 잘못된 입력이므로 여기서 막는다.
                raise ValueError("indicator 가 null 이다")
            indicator = str(raw_indicator)
            source_page = int(row["source_page"])
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            # ArithmeticError 는 OverflowError 를 포함한다 — json.loads 는
            # Infinity 를 기본으로 받아들이는데 int(inf) 는 이 예외를 던진다.
            raise ValueError(f"항목을 읽지 못했다(indicator/source_page 누락 "
                             f"또는 형식 오류): {row!r}") from exc
        if source_page < 1:
            # pages[source_page - 1] 로 색인하므로 0 이하는 잘못된(때로는
            # 마지막) 쪽으로 둔갑한다 — 조용히 넘기지 않고 여기서 막는다.
            raise ValueError(f"source_page 가 1보다 작다: {source_page} ({row!r})")
        out.append(Picked(indicator, text_, source_page))
    return out


def provider() -> tuple[str, str, dict] | None:
    """(url, model, headers) — 있는 키를 쓴다. 둘 다 없으면 None.

    press 의 llm_cite.provider() 와 같은 차례다(Anthropic 직결이 먼저,
    OpenRouter 가 대타). 순서를 바꾸지 않는다 — 둘 다 있는 환경에서
    도메인마다 다른 공급자를 쓰면, 같은 프롬프트가 왜 다른 답을 냈는지
    설명할 수 없게 된다.
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
    return None


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError("ANTHROPIC_API_KEY 도 OPENROUTER_API_KEY 도 없다")
    url, model, headers = got
    resp = requests.post(
        url,
        headers=headers,
        json={"model": model, "max_tokens": MAX_TOKENS,
              "temperature": TEMPERATURE,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        # raise_for_status() 는 본문을 버린다 — 401 이나 429 가 왜 그랬는지는
        # 본문 안에 있다. 그대로 실어 보낸다.
        raise ValueError(f"API 가 {resp.status_code} 를 돌려줬다: {resp.text[:200]}")
    data = resp.json()
    try:
        if "content" in data:                              # Anthropic Messages
            text = "".join(b.get("text", "") for b in data["content"])
        else:
            text = data["choices"][0]["message"]["content"]  # OpenAI 호환
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f"200 응답인데 형식이 예상과 다르다: {resp.text[:200]}") from exc
    if not isinstance(text, str):
        # OpenRouter 는 추론 토큰이 max_tokens 를 다 먹으면 content 를 null 로
        # 돌려준다. 그대로 넘기면 parse_response 에서 NoneType 오류가 나
        # 실행 로그만 보고는 원인을 알 수 없다 — finish_reason 이 들어 있는
        # 본문을 그대로 실어 보낸다.
        raise ValueError(f"200 응답인데 본문이 비어 있다: {resp.text[:300]}")
    return text


def select(org: str, title: str, indicators: Sequence[str], pages: Sequence[str],
           *, call: Callable[[str], str] | None = None) -> list[Picked]:
    call = call or _call_api
    return parse_response(call(build_prompt(org, title, indicators, pages)))
