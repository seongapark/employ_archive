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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, NamedTuple, Sequence

import requests

from .interests import Profile

KST = timezone(timedelta(hours=9))
DATA = Path(__file__).resolve().parent.parent / 'data'

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'
MODEL_ANTHROPIC = 'claude-opus-5'
MODEL_OPENROUTER = 'anthropic/claude-opus-5'
MODEL_OPENAI = 'gpt-5.5'        # OPENAI_MODEL 로 바꿀 수 있다
MAX_TOKENS = 4000
# OpenAI 의 gpt-5 계열은 답 말고 **추론 토큰**을 따로 쓴다. 같은 4000 으로
# 두면 20건짜리 묶음이 JSON 중간에서 잘린다(domains/press/pipeline/llm_cite.py
# 실측과 같은 이유).
MAX_TOKENS_OPENAI = 16000
TIMEOUT = 180
BATCH = 20                  # 한 번에 판정할 보고서 수
ABSTRACT_CAP = 800          # 초록을 이보다 길게 보내지 않는다

_FENCE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.S)
_WS = re.compile(r'\s+')


def _axis_key(s: str) -> str:
    """공백·가운뎃점을 지운 대조용 키.

    '청년 고용' 을 '청년고용' 으로, 'AI·기술변화의 직종별 고용영향' 을
    모델이 'AI 기술변화의 직종별 고용영향' 처럼 가운뎃점을 공백으로 바꿔
    쓰는 정도의 한 글자 차이로 묶음 20건 전체가 ValueError 로 죽으면 안
    된다. 공백과 '·' 만 눌러 대조하고, 실제 저장은 프로파일의 정식
    이름으로 한다 — 진짜 모르는 축(오타가 아니라 존재하지 않는 이름)은
    여전히 걸린다. 현재 축 여덟 개는 이 둘을 지워도 서로 충돌하지 않는다
    (확인됨).
    """
    return re.sub(r'[\s·]+', '', s or '')


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
        if not isinstance(row['pick'], bool):
            # bool(row['pick']) 로 느슨하게 받으면 문자열 "false" 도 참이 되어
            # 안 고른 보고서가 추천으로 둔갑한다 — 진짜 불리언만 받는다.
            raise ValueError(f'pick 이 불리언이 아니다: {row!r}')
        pick = row['pick']
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
    """(url, model, headers) — 있는 키를 쓴다. 없으면 None.

    **순서가 곧 선호다.** 판정 품질은 `claude-opus-5` 기준으로 프롬프트를
    설계했으므로 그 모델을 쓸 수 있으면 그걸 쓴다. OpenAI 는 마지막이다 —
    같은 프롬프트로 돌지만 그 전제(축 이름 매칭, why 길이감)를 물려받지
    않는다(domains/press/pipeline/llm_cite.py 의 선례와 같은 순서).
    """
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if key:
        return (ANTHROPIC_URL, MODEL_ANTHROPIC,
                {'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json'})
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if key:
        return (OPENROUTER_URL, MODEL_OPENROUTER,
                {'Authorization': f'Bearer {key}', 'content-type': 'application/json'})
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if key:
        model = os.environ.get('OPENAI_MODEL', '').strip() or MODEL_OPENAI
        return (OPENAI_URL, model,
                {'Authorization': f'Bearer {key}', 'content-type': 'application/json'})
    return None


def payload_for(url: str, model: str, prompt: str) -> dict:
    """공급자마다 토큰 한도의 이름이 다르다.

    OpenAI 의 gpt-5 계열은 `max_tokens` 를 **거부한다**(400: Unsupported
    parameter). 이름만 다른 게 아니라 뜻도 다르다 — 추론 토큰까지 그
    한도에서 쓰므로 한도를 넉넉히 잡아야 답이 안 잘린다.
    """
    msg = [{'role': 'user', 'content': prompt}]
    if 'openai.com' in url:
        return {'model': model, 'max_completion_tokens': MAX_TOKENS_OPENAI,
                'messages': msg}
    return {'model': model, 'max_tokens': MAX_TOKENS, 'messages': msg}


def _call_api(prompt: str) -> str:
    got = provider()
    if got is None:
        raise RuntimeError('ANTHROPIC_API_KEY · OPENROUTER_API_KEY · OPENAI_API_KEY '
                           '중 아무것도 없다')
    url, model, headers = got
    resp = requests.post(url, headers=headers, json=payload_for(url, model, prompt),
                         timeout=TIMEOUT)
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


def load_cache(path: Path | str | None = None) -> dict:
    p = Path(path or (DATA / 'recommendations.json'))
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding='utf-8'))


def pending(reports: Sequence[dict], cache: dict, profile: Profile) -> list[dict]:
    """아직 안 물어본 것과, 프로파일이 바뀐 뒤로 안 물어본 것."""
    todo = []
    for r in reports:
        got = cache.get(r['id'])
        if got is None or got.get('profile_version') != profile.version:
            todo.append(r)
    return todo


def merge(cache: dict, rows: Sequence[dict], verdicts: Sequence[Verdict],
          profile: Profile, model: str = MODEL_ANTHROPIC) -> dict:
    """판정을 캐시에 얹는다. 이번에 안 물어본 것은 그대로 둔다.

    `model` 은 **실제로 판정에 쓴 모델**을 호출자가 넘겨야 한다. 여기서
    상수(MODEL_ANTHROPIC)를 그대로 박으면, 이 저장소처럼 OPENAI_API_KEY
    밖에 없어 실제로는 gpt-5.5 로 판정했는데도 캐시에는 claude-opus-5 로
    거짓 기록된다(실측: 2026-09-11, 20건을 gpt-5.5 로 판정했더니 캐시엔
    전부 claude-opus-5 로 찍혔다). 이 필드는 "이 판정을 누가 내렸나"의
    유일한 기록이라, 나중에 앤트로픽 키가 들어와 모델별 판정 품질을
    비교하거나 특정 모델의 판정만 골라 재판정하려 할 때 이 값이 진실이
    아니면 아무것도 구분할 수 없다. 기본값은 단위 테스트에서 model 을
    안 넘기고 merge() 를 직접 부르던 기존 호출을 깨지 않기 위함이다 —
    실제 판정 경로(judge_and_cache)는 항상 provider() 가 돌려준 실제
    모델을 넘긴다.
    """
    now = datetime.now(KST).isoformat(timespec='seconds')
    out = dict(cache)
    for v in verdicts:
        row = rows[v.n - 1]
        out[row['id']] = {
            'pick': v.pick, 'axis': v.axis, 'why': v.why,
            # 초록이 없어 제목만으로 판정한 것을 표시한다. 나중에 원문에서
            # 초록을 채우면 그 레코드만 다시 물어보면 된다.
            'basis': 'abstract' if (row.get('abstract') or '').strip() else 'title',
            'model': model,
            'profile_version': profile.version,
            'judged_at': now,
        }
    return out


def judge_and_cache(profile: Profile, rows: Sequence[dict], cache: dict, *,
                     call: Callable[[str], str] | None = None,
                     cache_path: Path | str | None = None,
                     log: Callable[[str], None] = print) -> dict:
    """묶음마다 판정하고, 묶음이 끝날 때마다 그 자리에서 캐시 파일에 반영한다.

    judge() 를 통째로 불러 다 끝난 뒤에야 파일을 쓰면, 113회 호출 중
    한 번만 파싱에 실패해도 예외가 올라와 그때까지 판정한 것이 전부
    날아간다. 2,200건을 돌릴 예정이고 비용이 들기 때문에 이 위험을 감수할
    수 없다. 그래서 여기서는 BATCH 묶음 하나가 끝날 때마다 즉시
    write_text 한다 — 다음 묶음에서 예외가 나도 앞선 묶음은 디스크에
    남고, 다시 돌리면 pending() 이 그만큼을 걸러 다시 묻지 않는다.

    실제로 어느 모델이 판정했는지는 provider() 가 안다 — call 을 주입해도
    (테스트처럼) 마찬가지로 provider() 를 물어서 model 을 정하고, 키가
    하나도 없으면 MODEL_ANTHROPIC 으로 fallback 한다(그 경우는 call 이
    주입돼 있지 않는 한 어차피 _call_api 에서 RuntimeError 로 먼저
    끊긴다 — fallback 은 테스트에서 call 을 주입했을 때 model 표기가
    비지 않게 하려는 것뿐이다).
    """
    call = call or _call_api
    path = Path(cache_path or (DATA / 'recommendations.json'))
    got = provider()
    model = got[1] if got is not None else MODEL_ANTHROPIC
    cache = dict(cache)
    for start in range(0, len(rows), BATCH):
        chunk = list(rows[start:start + BATCH])
        log(f'  판정 {start + 1}~{start + len(chunk)} / {len(rows)}')
        # judge() 를 쓰지 않는다 — judge() 는 전체를 다 돌고서야 돌려주므로
        # 묶음마다 즉시 반영하려면 여기서 직접 한 묶음씩 부른다.
        verdicts = parse_response(call(build_prompt(profile, chunk)),
                                  len(chunk), profile.axes)
        cache = merge(cache, chunk, verdicts, profile, model=model)
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + '\n',
                        encoding='utf-8')
    return cache


def main(argv=None, *, call=None) -> int:
    import argparse

    from . import interests as interests_mod

    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='이번에 판정할 최대 건수')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    profile = interests_mod.load()
    reports = json.loads((DATA / 'reports.json').read_text(encoding='utf-8'))
    abstracts = json.loads((DATA / 'abstracts.json').read_text(encoding='utf-8'))
    rows = [{'id': r['id'], 'org': r['org'], 'series': r['series'], 'title': r['title'],
             'abstract': (abstracts.get(r['id']) or {}).get('abstract', '')}
            for r in reports]

    cache = load_cache()
    todo = pending(rows, cache, profile)
    if args.limit:
        todo = todo[:args.limit]
    print(f'판정 대상 {len(todo)} / 전체 {len(rows)} (프로파일 {profile.version})')
    # --dry-run 은 API 키 없이도 돌아야 한다 — provider()/_call_api 는
    # 아래에서 실제로 판정할 것이 있을 때만 불린다.
    if args.dry_run or not todo:
        return 0

    cache_path = DATA / 'recommendations.json'
    cache = judge_and_cache(profile, todo, cache, call=call, cache_path=cache_path)
    picked = sum(1 for v in cache.values() if v.get('pick'))
    print(f'추천 {picked} / 판정 {len(cache)}')

    last_path = DATA / 'last_run.json'
    last = json.loads(last_path.read_text(encoding='utf-8')) if last_path.exists() else {}
    last['recommend'] = {'judged': len(cache), 'picked': picked,
                         'profile_version': profile.version,
                         'title_only': sum(1 for v in cache.values()
                                           if v.get('basis') == 'title')}
    last_path.write_text(json.dumps(last, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
