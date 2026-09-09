"""raw + keywords.json → data/reports.json · abstracts.json · 결측률.

수집기는 게시판에 있는 것을 전부 raw 에 넣는다. 고용 여부를 가르는 것은 여기다.
경계가 여기 있는 이유는 비용이다 — 판정이 수집 안에 있으면 키워드 한 줄을 고칠
때마다 KDI·KIET 를 며칠에 걸쳐 다시 긁어야 한다. 여기서는 수십 초다.

  python -m domains.reports.pipeline.build
"""
from __future__ import annotations

import sys

# Windows 콘솔 기본 코드페이지(cp949)는 em-dash 같은 문자를 못 찍는다. 로그 한 줄
# 때문에 수집이 통째로 중단되면 안 된다.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
from pathlib import Path

from . import boards as boards_mod
from . import keywords as kw_mod
from . import store
from .models import RawReport, Report

DATA = Path(__file__).resolve().parent.parent / 'data'


def judge(raw: RawReport, board, kw: dict) -> Report:
    text = ' '.join([raw.title, raw.abstract or '', ' '.join(raw.toc)])
    matched = kw_mod.match(text, kw)
    # 매칭은 네 기관 전부에 남긴다. 담을지 말지에 쓰는 것만 filter 게시판이다.
    employment = bool(matched) if board.filter else True
    return Report(**raw.model_dump(), employment=employment, matched=matched)


def abstract_missing(reports: list[Report]) -> dict:
    out: dict[str, dict[str, dict]] = {}
    for r in reports:
        cell = out.setdefault(r.org, {}).setdefault(
            r.series, {'total': 0, 'missing': 0, 'rate': 0.0})
        cell['total'] += 1
        if not (r.abstract or '').strip():
            cell['missing'] += 1
    for series in out.values():
        for cell in series.values():
            cell['rate'] = round(cell['missing'] / cell['total'], 3) if cell['total'] else 0.0
    return out


def build(raw_rows: list[RawReport], boards: list, kw: dict):
    by_id = {b.id: b for b in boards}
    kept: list[Report] = []
    for raw in raw_rows:
        board = by_id.get(raw.board)
        if board is None or not board.enabled:
            continue
        rec = judge(raw, board, kw)
        if rec.employment:
            kept.append(rec)
    kept.sort(key=lambda r: (r.published, r.id), reverse=True)
    abstracts = {r.id: {'abstract': r.abstract or '', 'toc': r.toc} for r in kept}
    return kept, abstracts, abstract_missing(kept)


def _light(r: Report) -> dict:
    """목록용 경량 레코드. 초록·목차는 abstracts.json 으로 간다."""
    d = r.model_dump(mode='json')
    d.pop('abstract', None)
    d.pop('toc', None)
    d.pop('collected_at', None)
    return d


def main(argv=None) -> int:
    kept, abstracts, missing = build(
        store.load_all_raw(), boards_mod.load_boards(), kw_mod.load_keywords())

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'reports.json').write_text(
        json.dumps([_light(r) for r in kept], ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8')
    (DATA / 'abstracts.json').write_text(
        json.dumps(abstracts, ensure_ascii=False) + '\n', encoding='utf-8')

    last_path = DATA / 'last_run.json'
    last = json.loads(last_path.read_text(encoding='utf-8')) if last_path.exists() else {}
    last['reports'] = len(kept)
    last['abstract_missing'] = missing
    last_path.write_text(json.dumps(last, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    print(f'built: {len(kept)} reports')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
