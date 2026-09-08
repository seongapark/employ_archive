# -*- coding: utf-8 -*-
"""그 회차 보도자료 hwpx 를 고용노동부 게시판에서 받아 sources/releases 에 둔다.

  python -m domains.press.pipeline.fetch_release --month 2026-08

게시판을 읽는 코드는 **고용동향 도메인의 것을 그대로 쓴다**. 같은 게시판이고
그쪽에는 픽스처 테스트가 붙어 있다 — 여기 한 벌 더 두면 고용노동부가 페이지를
바꿀 때 고칠 곳이 둘이 된다. 의존은 이 파일 하나에만 두어 press → employment
한 방향으로 묶이고, 나머지 파이프라인은 이 결합을 모른다.

hwpx 는 저장소에 담지 않는다(.gitignore). 회차마다 1.4MB 이고 언제든 다시
받을 수 있다 — 반면 수집한 기사와 판정은 다시 만들 수 없어서 담는다.
"""
from __future__ import annotations

import argparse
import os

import requests

from domains.employment.pipeline import releases as board

HERE = os.path.dirname(os.path.abspath(__file__))
RELEASES = os.path.abspath(os.path.join(HERE, '..', 'sources', 'releases'))
TIMEOUT = 120


def index(*, fetch_list=None, fill=None):
    """게시판에서 고용행정통계 회차 목록과 첨부를 읽는다."""
    fetch_list = fetch_list or board.fetch_list
    fill = fill or board.fill_attachments
    found = fetch_list('ei')
    got = fill({'ei': found}, 'ei')
    # fill_attachments 는 (색인, 채운 수) 를 돌려준다. 첫 원소만 쓴다.
    idx = got[0] if isinstance(got, tuple) else got
    return idx['ei']


def hwpx_url(entry):
    for att in entry.get('attachments', []):
        if att.get('type') == 'hwpx':
            return att.get('url')
    return None


def save(month, *, idx=None, get=None, out_dir=None, log=print):
    """`2026-08` → sources/releases/ei_2026-08.hwpx. 이미 있으면 건너뛴다."""
    dest = out_dir or RELEASES
    path = os.path.join(dest, 'ei_%s.hwpx' % month)
    if os.path.exists(path):
        log('이미 있다: %s' % path)
        return path

    idx = idx if idx is not None else index()
    entry = idx.get(month)
    if entry is None:
        raise RuntimeError('게시판에 %s 회차가 없다 — 아직 안 올라왔을 수 있다' % month)
    url = hwpx_url(entry)
    if url is None:
        raise RuntimeError('%s 회차에 hwpx 첨부가 없다: %s' % (month, entry.get('url')))

    get = get or (lambda u: requests.get(u, timeout=TIMEOUT).content)
    body = get(url)
    os.makedirs(dest, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(body)
    log('받음: %s (%s · %s 바이트)'
        % (path, entry.get('title', '')[:40], format(len(body), ',')))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True, help='기준월 YYYY-MM (배포월의 전월)')
    a = ap.parse_args()
    save(a.month)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
