# -*- coding: utf-8 -*-
"""회차 원자료(raw/) + 판정(verdicts/) → 앱 데이터(rounds.json · articles.json).

수집기가 raw/ 를 채우고, llm_cite 가 verdicts/ 를 채운 뒤 이걸 돌린다.
세 단계를 나눠 둔 이유는 각각 실패하는 이유가 다르기 때문이다 —
수집은 네이버 API, 판정은 LLM 키, 조립은 보도자료 hwpx.
하나가 막혀도 앞 단계 결과는 남는다.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone

from .build_data import build_round

KST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
# data/ 는 그대로 배포된다(tools/build.py 가 통째로 복사한다). 원자료·보도자료
# hwpx·판정은 다시 만들 때만 필요하고 앱은 안 읽으므로 sources/ 에 둔다 —
# data/ 에 두면 회차마다 1.4MB 짜리 hwpx 가 사이트에 실린다.
DATA = os.path.abspath(os.path.join(HERE, '..', 'data'))
SOURCES = os.path.abspath(os.path.join(HERE, '..', 'sources'))
RAW = os.path.join(SOURCES, 'raw')
VERDICTS = os.path.join(SOURCES, 'verdicts')
RELEASES = os.path.join(SOURCES, 'releases')


def _load(path):
    if not os.path.exists(path):
        return None
    return json.load(io.open(path, encoding='utf-8'))


def rounds_on_disk():
    """raw/ 에 있는 회차를 배포일 순으로. 파일이 진실이고 목록은 코드에 없다."""
    out = {}
    for fn in os.listdir(RAW):
        if not fn.startswith('articles_') or not fn.endswith('.json'):
            continue
        rest = fn[len('articles_'):-len('.json')]
        release, _, kind = rest.rpartition('_')
        out.setdefault(release, set()).add(kind)
    return sorted(out.items())


def month_of(release):
    """배포일 → 기준월. 보도자료는 늘 전월 통계를 낸다."""
    d = datetime.strptime(release, '%Y-%m-%d')
    first = d.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.strftime('%Y-%m')


def main():
    summaries, articles = [], {}
    prev_press = None
    for release, kinds in rounds_on_disk():
        month = month_of(release)
        hwpx = os.path.join(RELEASES, 'ei_%s.hwpx' % month)
        if not os.path.exists(hwpx):
            print('건너뜀 %s — 보도자료 %s 가 없다' % (release, os.path.basename(hwpx)))
            continue
        reg = _load(os.path.join(RAW, 'articles_%s_regular.json' % release))
        if reg is None:
            print('건너뜀 %s — 정기 수집이 없다' % release)
            continue
        reg_v = _load(os.path.join(VERDICTS, 'verdict_%s_regular.json' % release)) or []
        fol = _load(os.path.join(RAW, 'articles_%s_follow.json' % release))
        fol_v = _load(os.path.join(VERDICTS, 'verdict_%s_follow.json' % release)) or []
        summary, arts = build_round(release, month, hwpx, reg, reg_v, fol, fol_v,
                                    prev_press=prev_press)
        summary['judged'] = bool(reg_v)
        summaries.append(summary)
        articles[release] = arts
        prev_press = summary['all_press']
        f = summary['follow']
        print('%s  %s  정기 %d/%d 인용 · 후속 %s' % (
            release, summary['label'], summary['regular']['cited'],
            summary['regular']['kept'],
            ('%d/%d 인용' % (f['cited'], f['kept'])) if f else '없음'))

    summaries.sort(key=lambda r: r['release'], reverse=True)
    json.dump(summaries, io.open(os.path.join(DATA, 'rounds.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(articles, io.open(os.path.join(DATA, 'articles.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump({'run_at': datetime.now(KST).strftime('%Y-%m-%dT%H:%M:%S+09:00'),
               'rounds': len(summaries)},
              io.open(os.path.join(DATA, 'last_run.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('→ rounds.json · articles.json · last_run.json (%d개 회차)' % len(summaries))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
