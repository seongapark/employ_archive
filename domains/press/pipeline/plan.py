# -*- coding: utf-8 -*-
"""오늘 무엇을 수집해야 하는가.

워크플로는 매시간 깨어나되 대부분의 날은 아무것도 하지 않는다. 배포일이
매달 다르기 때문에(7/13 · 8/10 · 9/7 · 10/14) 크론에 날짜를 박을 수 없다 —
게시판을 보고 그날그날 판단해야 한다.

**「지금 몇 시인가」가 아니라 「어느 회차가 아직 안 찼는가」로 판단한다.**
이 저장소의 예약 실행은 5~8시간 늦게 시작한다(2026-09-02 실측). 시각으로
판단하면 늦게 깬 실행이 엉뚱한 날로 넘어가 그 회차를 통째로 건너뛴다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 후속 구간은 D+1~D+15 다. **그 구간이 열려 있는 동안 매일 긁는다** —
# D+16 에 딱 한 번만 긁던 것을 2026-09-11 에 바꿨다. 한 번만 긁으면 후속
# 화면이 보름 내내 비어 있다가 어느 날 갑자기 차고, 그 사이에 프레임이
# 번져도 아무도 모른다. 이 도메인에서 가장 나쁜 것이 늦게 아는 것이다.
#
# D+1 은 빼 둔다 — 그날은 정기 수집이 도는 날이고, 후속 구간이 하루치뿐이라
# 긁을 것이 사실상 없다. D+16 은 구간이 닫힌 다음날이라 마지막으로 한 번 더 돈다.
FOLLOW_FROM = 2
FOLLOW_LAST = 16


def today_kst():
    return datetime.now(KST).date()


def _d(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, '%Y-%m-%d').date()


def latest_release(releases, today):
    """오늘까지 나온 것 중 가장 최근 배포일. 없으면 None."""
    past = sorted(d for d in (_d(r) for r in releases) if d <= today)
    return past[-1] if past else None


def decide(today, releases):
    """(무엇, 회차) 또는 (None, None).

    - 배포 당일과 그 이튿날 → 정기. 이튿날까지 도는 이유는 수집 구간이
      D~D+1 이라서다. 당일 밤 기사는 이튿날 실행이 담는다.
    - 배포 +2일 ~ +16일 → 후속. 구간(D+1~D+15)이 열려 있는 동안 **매일**
      긁고, 닫힌 다음날(D+16)에 한 번 더 긁어 마감한다.
    - 그 밖의 날 → 아무것도 안 한다.

    매일 다시 긁어도 손해가 없다: 수집은 발행일로 거르므로 같은 구간을
    통째로 다시 훑고, 판정은 제목으로 이어져 새 기사만 LLM 에 간다.
    """
    today = _d(today)
    rel = latest_release(releases, today)
    if rel is None:
        return None, None
    gap = (today - rel).days
    if gap in (0, 1):
        return 'regular', rel.strftime('%Y-%m-%d')
    if FOLLOW_FROM <= gap <= FOLLOW_LAST:
        return 'follow', rel.strftime('%Y-%m-%d')
    return None, None


def is_release_day(today, releases):
    """배포 당일인가. 이 날만 매시간 돈다.

    기사가 12시부터 밤까지 계속 올라오고, 이 도메인은 늦게 아는 것이 가장
    나쁘다. 이튿날과 후속일은 하루 한 번이면 된다 — 그날 기사는 이미 다 나와
    있어 매시간 돌아봐야 같은 것을 다시 긁는다.
    """
    today = _d(today)
    rel = latest_release(releases, today)
    return rel is not None and rel == today


def should_run(today, releases, last=None):
    """(무엇, 회차, 사유). 무엇이 None 이면 이번 실행은 아무것도 안 한다.

    「오늘 이미 돌았나」를 상태로 판단한다. 실행 시각으로 판단하지 않는 이유는
    이 저장소의 예약 실행이 5~8시간 늦게 시작하기 때문이다(2026-09-02 실측) —
    「10시 실행만 통과」 같은 규칙은 늦게 깬 실행을 전부 버린다.

    `last` 는 지난 실행 기록 {'release','kind','date'} 이고 없으면 처음이다.
    """
    today = _d(today)
    kind, release = decide(today, releases)
    if kind is None:
        return None, None, '오늘은 수집일이 아니다'
    if is_release_day(today, releases):
        return kind, release, '배포 당일 — 매시간 수집'
    prev = last or {}
    done_today = (prev.get('date') == today.strftime('%Y-%m-%d')
                  and prev.get('kind') == kind and prev.get('release') == release)
    if done_today:
        return None, None, '오늘 이미 수집했다(배포 당일이 아니면 하루 한 번)'
    return kind, release, '배포 이튿날 · 창 마감' if kind == 'regular' else '후속 구간 — 하루 한 번'


def load_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}          # 깨진 상태 파일 때문에 수집을 멈추지는 않는다


def save_state(path, release, kind, today):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'release': release, 'kind': kind,
                   'date': _d(today).strftime('%Y-%m-%d')}, f, ensure_ascii=False, indent=1)


def schedule_to_releases(schedule, year):
    """보도자료 참고3의 배포일정표 → 배포일 목록.

    표는 「1월: 2.9 (월)」처럼 **기준월 → 배포 월.일** 이고 연도가 없다.
    기준연도가 곧 배포연도다(1월분을 2월에, 11월분을 12월에 낸다). 12월분만
    이듬해라 「‘27년 미정」으로 비워 두므로 건너뛴다.

    이 표를 쓰면 게시판을 두드리지 않고도 **다음 달 배포일까지 미리 안다.**
    매시간 도는 게이트가 매번 고용노동부에 묻는 것은 예의가 아니다.
    """
    out = {}
    for key, value in (schedule or {}).items():
        m = re.match(r'(\d{1,2})월', str(key))
        d = re.match(r'\s*(\d{1,2})\.\s*(\d{1,2})', str(value))
        if not (m and d):
            continue                      # '‘27년 미정' 같은 칸
        base = int(m.group(1))
        month, day = int(d.group(1)), int(d.group(2))
        try:
            released = date(int(year), month, day)
        except ValueError:
            continue
        out['%s-%02d' % (year, base)] = released.strftime('%Y-%m-%d')
    return out


def month_of(release):
    """배포일 → 보도자료 기준월. 보도자료는 늘 전월 통계를 낸다."""
    d = _d(release)
    return (d.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
