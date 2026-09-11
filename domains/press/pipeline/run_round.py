# -*- coding: utf-8 -*-
"""워크플로가 부르는 하나의 문. 오늘 할 일이 있으면 끝까지 하고, 없으면 곧 끝난다.

  python -m domains.press.pipeline.run_round            # 오늘 할 일을 스스로 정한다
  python -m domains.press.pipeline.run_round --release 2026-10-14 --kind regular

YAML 이 얇아야 하는 이유: 워크플로 안의 로직은 테스트할 수 없다. 판단은 전부
`plan` 에 있고 여기서는 순서만 잇는다.

**판정은 아직 판정 없는 기사에만 돌린다.** 배포 당일 매시간 도는데 매번 전체를
다시 물으면 비용이 스물네 배가 된다. 판정을 제목으로 잇게 해 두었으므로,
이미 판정한 기사는 그대로 두고 새로 들어온 것만 묻는다.

다만 **판정에 논조(`tone`)가 없으면 다시 묻는다.** 논조는 나중에 붙인 항목이라
옛 판정 파일에는 없다. 없는 것을 '중립'으로 채우면 화면이 채워진 것처럼
보이므로, 한 번은 다시 물어서 실제 값을 받는다(회차당 한 번이면 끝난다).
"""
from __future__ import annotations

import argparse
import io
import json
import os
from . import collect, fetch_release, llm_cite, plan

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.abspath(os.path.join(HERE, '..', 'sources'))
RAW = os.path.join(SOURCES, 'raw')
VERDICTS = os.path.join(SOURCES, 'verdicts')
STATE = os.path.join(SOURCES, 'last_run.json')
DATA = os.path.abspath(os.path.join(HERE, '..', 'data'))


def _load(path):
    if not os.path.exists(path):
        return None
    return json.load(io.open(path, encoding='utf-8'))


def _norm(t):
    import re
    return re.sub(r'\s+', '', t)


def judge_missing(release, kind, *, log=print, call=None):
    """아직 판정 없는 기사만 LLM 에 묻고 기존 판정에 합친다."""
    raw = _load(os.path.join(RAW, 'articles_%s_%s.json' % (release, kind)))
    if raw is None:
        log('  수집 파일이 없다 — 판정 건너뜀')
        return 0
    arts = raw['articles']
    vpath = os.path.join(VERDICTS, 'verdict_%s_%s.json' % (release, kind))
    old = _load(vpath) or []
    known = {_norm(v['title']) for v in old if v.get('title') and v.get('tone')}
    todo = [a for a in arts if _norm(a['title']) not in known]
    if not todo:
        log('  새로 판정할 기사 없음 (기존 %d건 유지)' % len(old))
        return 0
    stale = sum(1 for v in old if v.get('title') and not v.get('tone'))
    if llm_cite.provider() is None:
        log('  ⚠ LLM 키가 없다 — %d건이 판정 없이 남는다(화면에서 인용 아님으로 센다)'
            % len(todo))
        return 0

    month = plan.month_of(release)
    hwpx = os.path.join(SOURCES, 'releases', 'ei_%s.hwpx' % month)
    digest = _digest(hwpx)
    label = '%s년 %d월 고용행정 통계로 본 노동시장 동향' % (month[:4], int(month[5:]))
    log('  판정 대상 %d건 (기존 %d건 중 논조 없는 %d건 포함)' % (len(todo), len(old), stale))
    verdicts = llm_cite.judge(label, release, digest, todo, call=call, log=log)

    # 다시 물은 기사의 옛 판정은 버린다 — 남겨 두면 같은 제목이 두 줄이 되고,
    # build_data 가 둘 중 아무거나 집는다.
    redone = {_norm(a['title']) for a in todo}
    merged = [v for v in old if _norm(v.get('title', '')) not in redone]
    merged += [{'n': v.n, 'cites': v.cites, 'why': v.why, 'tone': v.tone,
                'title': todo[v.n - 1]['title'], 'press': todo[v.n - 1]['press']}
               for v in verdicts]
    os.makedirs(VERDICTS, exist_ok=True)
    json.dump(merged, io.open(vpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log('  판정 %d건 추가 → 총 %d건' % (len(verdicts), len(merged)))
    return len(verdicts)


def _digest(hwpx):
    """보도자료 요지. 없으면 최소 맥락으로도 판정은 된다(실측에서 결과가 같았다)."""
    if not os.path.exists(hwpx):
        return ('(보도자료 원문을 아직 못 받았다. 기준월은 배포일의 전월이고, 내용은 '
                '매월 같은 세 부분이다: 고용보험 상시가입자 현황(산업·연령·성별 증감), '
                '구직급여 신규신청·지급자·지급액, 고용24 신규구인·신규구직·구인배수.)')
    from .press_parser import parse_release
    rel = parse_release(hwpx)
    lines = []
    for s in rel['series']:
        pts = s.get('계열') or []
        if pts:
            lines.append('- %s: %s %s%s' % (s['항목'], pts[-1].get('시점'),
                                            pts[-1].get('값'), s.get('단위', '')))
    return rel['body'][:1400] + '\n\n[표에서 읽은 최신 수치]\n' + '\n'.join(lines)


def known_releases(today):
    """배포일 목록. 먼저 저장해 둔 일정표를 보고, 모자랄 때만 게시판에 묻는다.

    매시간 도는 게이트가 매번 고용노동부를 두드리는 것은 예의가 아니고, 대부분의
    날은 물어볼 이유도 없다 — 보도자료 참고3의 일정표에 다음 달 배포일까지 적혀
    있기 때문이다. 일정표가 오늘을 못 덮을 때만(연말에 이듬해 표가 아직 없을 때)
    게시판으로 내려간다.
    """
    sched = _load(os.path.join(DATA, 'schedule.json')) or {}
    releases = sorted(sched.values())
    if releases and plan.latest_release(releases, plan._d(today)) is not None             and max(releases) >= today.strftime('%Y-%m-%d'):
        return releases
    print('  일정표가 오늘을 못 덮는다 — 게시판을 본다')
    index = fetch_release.index()
    # 게시판 목록 행이 배포일(posted_at)을 들고 있다 — 지어낼 필요가 없다.
    return sorted(set(releases) | {e['posted_at'] for e in index.values()
                                   if e.get('posted_at')})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', help='배포일. 주면 계획을 건너뛴다')
    ap.add_argument('--kind', choices=['regular', 'follow'])
    ap.add_argument('--dry-run', action='store_true', help='할 일만 알려주고 끝낸다')
    a = ap.parse_args(argv)

    today = plan.today_kst()
    if a.release and a.kind:
        kind, release, why = a.kind, a.release, '직접 지정'
    else:
        releases = known_releases(today)
        kind, release, why = plan.should_run(today, releases, plan.load_state(STATE))

    print('오늘 %s · %s' % (today, why))
    if a.dry_run:
        # 워크플로가 읽는 줄. 계획 잡이 이걸 보고 수집 잡을 돌릴지 정한다.
        print('PLAN_KIND=%s' % (kind or ''))
        print('PLAN_RELEASE=%s' % (release or ''))
        return 0
    if kind is None:
        return 0

    month = plan.month_of(release)
    try:
        fetch_release.save(month)
    except Exception as exc:                      # 보도자료가 아직 안 올라왔을 수 있다
        print('  보도자료를 못 받았다: %s — 기본 검색어로 진행한다' % exc)

    hwpx = os.path.join(SOURCES, 'releases', 'ei_%s.hwpx' % month)
    collect.run(release, hwpx if os.path.exists(hwpx) else None, kind == 'follow')
    judge_missing(release, kind)

    from . import make_data
    make_data.main()
    plan.save_state(STATE, release, kind, today)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
