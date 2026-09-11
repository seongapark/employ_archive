"""게시판을 훑어 sources/raw/ 에 넣는다. **판정하지 않는다.**

  python -m domains.reports.pipeline.collect
  python -m domains.reports.pipeline.collect --board kli-research
  python -m domains.reports.pipeline.collect --dry-run

넓게 긁어 두고 판정은 build 가 한다. 수집기가 판정까지 하면 판정 기준을 고칠
때마다 다시 수집해야 하는데, 게시판 예의 때문에 그게 며칠이다.
"""
from __future__ import annotations

import sys

# Windows 콘솔 기본 코드페이지(cp949)는 em-dash 같은 문자를 못 찍는다. 로그 한 줄
# 때문에 수집이 통째로 중단되면 안 된다.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import boards as boards_mod
from . import build as build_mod
from . import http, store
from .models import CUTOFF, RawReport, normalize_published, report_id
from .sites import bok, kdi, keis, kiet, kli

KST = timezone(timedelta(hours=9))
DATA = Path(__file__).resolve().parent.parent / 'data'
SITES = {'kli': kli, 'keis': keis, 'kdi': kdi, 'kiet': kiet, 'bok': bok}
DETAIL_CAP = 40          # 회차당 게시판별 상세 조회 상한
MAX_PAGES = 60
DELAY = 1.0


class NoThrottle:
    def wait(self) -> None:
        return None


def stub_record(item: dict, board) -> RawReport:
    """테스트용 최소 레코드. 파서 없이 오케스트레이션만 잴 때 쓴다."""
    published, precision = normalize_published(item['published_raw'])
    return RawReport(
        id=report_id(board.org, board.id_prefix + item['native_id']),
        org=board.org, board=board.id, series=board.series,
        title=item['title'], published=published, date_precision=precision,
        landing_url=item['detail_url'],
    )


def collect_board(board, *, fetch, throttle, detail_cap, existing,
                  parse_list=None, parse_detail=None):
    site = SITES[board.org]
    parse_list = parse_list or site.parse_list
    parse_detail = parse_detail or site.parse_detail
    list_url = site.list_url
    known = {r.id for r in existing}
    result = {'ok': True, 'parsed': 0, 'added': 0, 'details': 0,
              'reached_cutoff': False, 'error': None}
    records: list[RawReport] = []
    details = 0
    now = datetime.now(KST).isoformat(timespec='seconds')
    try:
        for page in range(1, MAX_PAGES + 1):
            url = list_url(board, page)
            if not url:
                break
            throttle.wait()
            items = parse_list(fetch(url), board)
            if not items:
                break
            result['parsed'] += len(items)
            stop = False
            for item in items:
                if item.get('published_raw'):
                    published, _ = normalize_published(item['published_raw'])
                    if published < CUTOFF:
                        result['reached_cutoff'] = stop = True
                        break
                rid = report_id(board.org, board.id_prefix + item['native_id'])
                if rid in known:
                    continue
                if details >= detail_cap:
                    stop = True
                    break
                if board.detail_in_list:
                    detail_html = item.get('block', '')
                else:
                    throttle.wait()
                    detail_html = fetch(item['detail_url'])
                    details += 1
                rec = parse_detail(detail_html, item, board)
                rec.collected_at = now
                records.append(rec)
            if stop:
                break
    except Exception as exc:                       # noqa: BLE001
        result['ok'] = False
        result['error'] = str(exc)
    result['details'] = details
    if result['ok'] and result['parsed'] == 0:
        result['ok'] = False
        result['error'] = '목록을 받았지만 항목이 0건이다 — 마크업 변경 신호'
    return records, result


def write_last_run(results: dict, unregistered_found: list[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / 'last_run.json'
    last = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    # boards 는 덮어쓰기가 아니라 병합이다. --board/--org 로 일부만 돌리면
    # results 에는 그 게시판들만 들어 있는데, 통째로 덮어쓰면 이번 회차에
    # 돌지 않은 나머지 게시판의 최근 기록이 사라진다. check_run.py 가 이
    # boards 를 읽어 게시판 단위로 실패를 판정하므로, 기록이 사라지면
    # "그 게시판이 최근에 돌았는지 안 돌았는지"조차 알 수 없게 된다.
    # boards.json 에서 이미 빠진(등록이 없어진) 게시판의 낡은 키만 정리한다.
    boards = dict(last.get('boards', {}))
    boards.update(results)
    registered = {b.id for b in boards_mod.load_boards()}
    boards = {bid: r for bid, r in boards.items() if bid in registered}
    last['at'] = datetime.now(KST).isoformat(timespec='seconds')
    last['boards'] = boards
    last['unregistered'] = unregistered_found
    path.write_text(json.dumps(last, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def main(argv=None, *, collectors=None, fetch=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--board')
    ap.add_argument('--org')
    ap.add_argument('--cap', type=int, default=DETAIL_CAP)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    # collectors 를 주입하면 네트워크가 꺼진다 — 테스트가 밖으로 안 나간다.
    sites = SITES if collectors is None else collectors
    if not sites or args.dry_run:
        write_last_run({}, [])
        return 0

    getter = fetch or (lambda url: http.get_text(url))
    throttle = http.Throttle(delay=DELAY)
    results: dict[str, dict] = {}
    for board in boards_mod.load_boards():
        if not board.enabled:
            continue
        if args.board and board.id != args.board:
            continue
        if args.org and board.org != args.org:
            continue
        path = store.raw_path(board.id, board.org)
        existing = store.load_raw(path)
        records, result = collect_board(
            board, fetch=getter, throttle=throttle,
            detail_cap=args.cap, existing=existing)
        merged, added = store.upsert(existing, records)
        result['added'] = len(added)
        result['total'] = len(merged)
        store.save_raw(path, merged)
        results[board.id] = result
        print(f"{board.id}: parsed={result['parsed']} added={result['added']} "
              f"total={result['total']} ok={result['ok']} {result['error'] or ''}")

    write_last_run(results, [])
    build_mod.main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
