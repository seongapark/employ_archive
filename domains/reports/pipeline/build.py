"""raw + keywords.json → data/reports.json · abstracts.json · 결측률.

**전량 수록한다.** 이 사이트는 외부기관 보고서를 취합하는 아카이브이고, 읽을
만한 것을 고르는 일은 recommend 가 별도 파일에서 한다.

keywords 는 거르는 도구가 아니라 **분류하는 도구**다 — matched 가 주제 화면의
입구다. 키워드를 고치면 재수집 없이 여기서 수십 초에 다시 매겨진다.

  python -m domains.reports.pipeline.build
"""
from __future__ import annotations

import sys

# Windows 콘솔 기본 코드페이지(cp949)는 em-dash 같은 문자를 못 찍는다. 로그 한 줄
# 때문에 수집이 통째로 중단되면 안 된다.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import gzip
import json
from pathlib import Path

from . import boards as boards_mod
from . import keywords as kw_mod
from . import store
from .boards import Board
from .models import RawReport, Report

DATA = Path(__file__).resolve().parent.parent / 'data'


def judge(raw: RawReport, board, kw: dict) -> Report:
    """주제 태그만 붙인다. 수록 여부는 가르지 않는다 — 전량 수록이다."""
    text = ' '.join([raw.title, raw.abstract or '', ' '.join(raw.toc)])
    return Report(**raw.model_dump(), matched=kw_mod.match(text, kw))


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


def missing_reasons(reports: list[Report]) -> dict:
    """초록이 빈 레코드가 왜 비었는지. 결측률만으로는 손쓸 수 있는 것과
    없는 것이 안 갈린다 — 스캔본은 OCR 없이는 영영 못 채우고, '요약 섹션 없음'
    은 기관이 애초에 안 쓴 것이며, 아직 안 받아 본 것은 다음 회차에 채워진다.
    스펙 9-3(NKIS 보강 전환) 판단이 이 구분에 걸려 있다."""
    out: dict[str, int] = {}
    for r in reports:
        if (r.abstract or '').strip():
            continue
        key = r.abstract_note or ('원문 없음' if not r.file_url else '아직 안 받음')
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def dedupe(reports: list[Report], by_id: dict[str, Board]) -> list[Report]:
    """같은 게시판에 제목이 똑같은 게 둘이면 이른 날짜 하나만 남긴다.

    조사연구자료에서 같은 연구를 두 지역본부가 각각 올린다(실측 7쌍). nttId 가
    달라 id 로는 안 잡힌다. dedupe_titles 가 켜진 게시판만 대상으로 한다.
    **게시판 간에는 보지 않는다** — 고른 게시판 사이 중복은 실측 0건이고,
    우연한 동명이 지워지면 안 된다.
    """
    # dedupe_titles 가 켜지지 않은 게시판은 손대지 않고 통과시킨다.
    passthrough = [r for r in reports
                   if not getattr(by_id.get(r.board), 'dedupe_titles', False)]

    # dedupe_titles 가 켜진 게시판만 같은 제목 중복 제거 대상으로 한다.
    target = [r for r in reports
              if getattr(by_id.get(r.board), 'dedupe_titles', False)]

    best: dict[tuple[str, str], Report] = {}
    for r in target:
        key = (r.board, r.title.strip())
        prev = best.get(key)
        if prev is None or (r.published, r.id) < (prev.published, prev.id):
            best[key] = r

    return passthrough + list(best.values())


def build(raw_rows: list[RawReport], boards: list, kw: dict):
    by_id = {b.id: b for b in boards}
    kept: list[Report] = []
    for raw in raw_rows:
        board = by_id.get(raw.board)
        if board is None or not board.enabled:
            continue
        rec = judge(raw, board, kw)
        kept.append(rec)
    kept = dedupe(kept, by_id)
    kept.sort(key=lambda r: (r.published, r.id), reverse=True)
    abstracts = {r.id: {'abstract': r.abstract or '', 'toc': r.toc} for r in kept}
    return kept, abstracts, abstract_missing(kept)


def _light(r: Report) -> dict:
    """목록용 경량 레코드. 초록·목차는 abstracts.json 으로 간다."""
    d = r.model_dump(mode='json')
    for k in ('abstract', 'toc', 'collected_at',
              'abstract_tried', 'abstract_note'):
        d.pop(k, None)
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
    last['abstract_missing_why'] = missing_reasons(kept)

    def _gz(name: str) -> int:
        return len(gzip.compress((DATA / name).read_bytes()))

    # 초록은 검색창을 누를 때 통째로 받는다. 3MB 를 넘으면 기관별로 쪼갠다 —
    # 미리 쪼개면 검색 품질과 복잡도를 숫자가 나오기 전에 내주는 셈이다.
    last['sizes'] = {'reports_gzip': _gz('reports.json'),
                     'abstracts_gzip': _gz('abstracts.json')}

    last_path.write_text(json.dumps(last, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    print(f'built: {len(kept)} reports')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
