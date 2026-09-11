# -*- coding: utf-8 -*-
"""보고서가 읽을 만한지 LLM 이 판정한다.

이 도메인은 전량 수록한다. 거르는 일은 수록이 아니라 여기가 한다.

키워드 단독으로는 안 된다 — 실측에서 '고용현황'·'청년층 고용' 같은 말투를
통째로 놓쳤다. 제목만 임베딩한 유사도도 기각했다: 양성 평균(0.612)이 음성
상위 10%(0.635)보다 낮아 임계값으로 자를 수 없었다(스펙 §3-6).

판정과 근거를 함께 받는다. 근거가 없으면 왜 틀렸는지 아무도 못 본다.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import os
import re
from typing import Callable, NamedTuple, Sequence

import requests

from .interests import Profile

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODEL_ANTHROPIC = 'claude-opus-5'
MODEL_OPENROUTER = 'anthropic/claude-opus-5'
MAX_TOKENS = 4000
TIMEOUT = 180
BATCH = 20                  # 한 번에 판정할 보고서 수
ABSTRACT_CAP = 800          # 초록을 이보다 길게 보내지 않는다

_FENCE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.S)
_WS = re.compile(r'\s+')


def _axis_key(s: str) -> str:
    """공백을 지운 대조용 키.

    '청년 고용' 을 '청년고용' 으로, 'AI·기술변화의 직종별 고용영향' 의
    가운뎃점을 빠뜨리는 정도의 한 글자 차이로 묶음 20건 전체가 ValueError 로
    죽으면 안 된다. 공백만 눌러 대조하고, 실제 저장은 프로파일의 정식
    이름으로 한다 — 진짜 모르는 축(오타가 아니라 존재하지 않는 이름)은
    여전히 걸린다.
    """
    return re.sub(r'\s+', '', s or '')


class Verdict(NamedTuple):
    n: int          # 묶음 안의 번호 (1부터). 호출자가 순서로 id 에 되맞춘다
    pick: bool
    axis: str
    why: str


def build_prompt(profile: Profile, rows: Sequence[dict]) -> str:
    lines = []
    for i, r in enumerate(rows, start=1):
        abstract = _WS.sub(' ', (r.get('abstract') or ''))[:ABSTRACT_CAP]
        head = f'{i}. [{r.get("org", "")} · {r.get("series", "")}] {r["title"]}'
        lines.append(f'{head}\n   {abstract}' if abstract else head)
    listing = '\n'.join(lines)
    axes = '\n'.join(f'- {a}' for a in profile.axes)
    return f"""고용노동부에서 노동시장을 분석하는 사람이 읽을 보고서를 고른다.

그 사람의 관심축은 이렇다:

{profile.text}

아래는 외부 연구기관이 낸 보고서 목록이다. 각 보고서가 **위 관심축에 닿고
실제로 읽을 가치가 있는지** 판정하라.

판정 기준:
- 관심축에 닿으면서 새 데이터·새 분석·정책 함의가 있으면 고른다.
- 같은 낱말을 써도 **다른 것을 말하면 고르지 않는다** — 금융안정 맥락의
  '가계', 물가 맥락의 '임금' 처럼.
- 정기 통계 공표·동향 요약처럼 **읽을 새 내용이 없으면** 고르지 않는다.
- 초록이 없어 제목만 있는 것은 제목이 분명히 관심축에 닿을 때만 고른다.
- 애매하면 고르지 않는 쪽으로 판정하라. 다만 그 이유를 적어라.
- 여러 축에 걸치면 **가장 강하게 닿는 하나**만 고른다.

축 이름은 아래 중 하나를 **그대로** 쓴다. 고르지 않으면 빈 문자열로 둔다:
{axes}

보고서 목록:
{listing}

각 보고서마다 한 줄씩, JSON 배열로만 답하라. 다른 말을 덧붙이지 마라:
[{{"n": 1, "pick": true, "axis": "청년 고용", "why": "청년 경력 사다리를 직종 기준으로 분해"}}]

`why` 는 25자 안팎으로 짧게. 고르지 않으면 무엇을 다룬 보고서인지 적어라.
"""


def parse_response(body: str, n_expected: int, axes: Sequence[str]) -> list[Verdict]:
    """JSON 배열을 읽는다. 못 읽으면 ValueError — 조용히 넘기지 않는다."""
    text = (body or '').strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'응답을 JSON 으로 읽지 못했다: {body[:200]}') from exc
    if not isinstance(rows, list):
        raise ValueError(f'배열이 아니다: {body[:200]}')

    by_key = {_axis_key(a): a for a in axes}
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f'항목이 객체가 아니다: {row!r}')
        try:
            n = int(row['n'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'n 을 읽지 못했다: {row!r}') from exc
        if not (1 <= n <= n_expected):
            raise ValueError(f'n 이 범위 밖이다({n}, 1~{n_expected}): {row!r}')
        if n in seen:
            raise ValueError(f'n 이 중복이다: {n}')
        seen.add(n)
        if 'pick' not in row:
            raise ValueError(f'pick 이 없다: {row!r}')
        pick = bool(row['pick'])
        axis = str(row.get('axis', '')).strip()
        why = str(row.get('why', '')).strip()
        if pick:
            canonical = by_key.get(_axis_key(axis))
            if canonical is None:
                raise ValueError(f'모르는 축이다({axis!r}): {row!r}')
            axis = canonical
        else:
            # 안 고른 항목의 axis 는 버리는 값이라 검증하지 않는다(의도).
            # 모델이 '없는축' 같은 값을 넣어도 무해하다 — 어차피 빈 문자열로
            # 치환된다. 여기서 검증하면 정작 고르지 않은 항목의 사소한 이탈
            # 때문에 묶음 20건 전체가 죽는다.
            axis = ''
        if not why:
            raise ValueError(f'이유가 비었다: {row!r}')
        out.append(Verdict(n, pick, axis, why))
    missing = sorted(set(range(1, n_expected + 1)) - seen)
    if missing:
        # 빠진 보고서를 조용히 '고르지 않음' 으로 두면 누락이 안 보인다.
        raise ValueError(f'판정이 빠진 보고서가 있다: {missing}')
    return sorted(out)


def provider() -> tuple[str, str, dict] | None:
    """(url, model, headers) — 있는 키를 쓴다. 없으면 None."""
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if key:
        return (ANTHROPIC_URL, MODEL_ANTHROPIC,
                {'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json'})
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if key:
        return (OPENROUTER_URL, MODEL_OPENROUTER,
                {'Authorization': f'Bearer {key}', 'content-type': 'application/json'})
    return None


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError('ANTHROPIC_API_KEY 도 OPENROUTER_API_KEY 도 없다')
    url, model, headers = got
    payload = {'model': model, 'max_tokens': MAX_TOKENS,
               'messages': [{'role': 'user', 'content': prompt}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise ValueError(f'API 가 {resp.status_code} 를 돌려줬다: {resp.text[:300]}')
    data = resp.json()
    try:
        if 'content' in data:                        # Anthropic Messages
            return ''.join(b.get('text', '') for b in data['content'])
        return data['choices'][0]['message']['content']
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError(f'200 응답인데 형식이 예상과 다르다: {resp.text[:300]}') from exc


def judge(profile: Profile, rows: Sequence[dict], *,
          call: Callable[[str], str] | None = None,
          log: Callable[[str], None] = print) -> list[Verdict]:
    """보고서 전체를 BATCH 씩 나눠 판정한다. n 은 전체 기준으로 돌려준다."""
    call = call or _call_api
    out: list[Verdict] = []
    for start in range(0, len(rows), BATCH):
        chunk = list(rows[start:start + BATCH])
        log(f'  판정 {start + 1}~{start + len(chunk)} / {len(rows)}')
        got = parse_response(call(build_prompt(profile, chunk)),
                             len(chunk), profile.axes)
        out.extend(Verdict(v.n + start, v.pick, v.axis, v.why) for v in got)
    return out
