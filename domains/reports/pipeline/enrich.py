"""초록이 빈 레코드의 원문 PDF 에서 초록을 뽑아 raw 에 채운다.

  python -m domains.reports.pipeline.enrich            # 상한만큼
  python -m domains.reports.pipeline.enrich --cap 400  # 백필

수집(collect)과 분리한 이유는 성격이 다르기 때문이다. 수집은 게시판 목록을
매일 훑는 일이고, 이것은 이미 아는 레코드의 빈 칸을 채우는 일이다. 처음 한 번
크게 돌고 나면 그 뒤로는 새로 올라온 몇 건뿐이다.

**PDF 는 저장소에 남기지 않는다.** 메모리에서 텍스트만 뽑고 버린다. 원문은
기관 서버가 정본이고, 우리가 받아 두면 그 시점에 굳는다.

한 번 시도한 레코드는 `abstract_tried` 로 표시해 다시 받지 않는다. 이게 없으면
요약이 없는 보고서(잡지·발제문집)를 회차마다 헛되이 다시 내려받는다. 실측으로는
**요약 섹션이 있는 것이 연구보고서류뿐**이라 대부분은 한 번 받고 끝난다.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse
import io
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from . import boards as boards_mod
from . import build as build_mod
from . import http, store
from . import pdf_abstract
from .models import RawReport

KST = timezone(timedelta(hours=9))
CAP = 40                 # 회차 기본 상한. 백필은 --cap 으로 올린다.
DELAY = 1.5              # 파일은 목록보다 무겁다 — 더 여유를 둔다
PAGES = 20               # 요약은 앞쪽에 있다. 뒤까지 읽을 이유가 없다
MAX_BYTES = 60 * 1024 * 1024


def needs_text(rec: RawReport) -> bool:
    if rec.abstract_tried:
        return False
    if (rec.abstract or '').strip():
        return False
    return bool(rec.file_url)


def read_pdf(data: bytes, *, pages: int = PAGES) -> list[str]:
    """앞 몇 쪽의 텍스트. PDF 가 아니면 빈 목록."""
    if data[:5] != b'%PDF-':
        return []
    import pdfplumber                       # 무거운 import 는 쓸 때만
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(p.extract_text() or '') for p in pdf.pages[:pages]]


def enrich_record(rec: RawReport, *, fetch: Callable[[str], bytes],
                  read: Callable[[bytes], list[str]] = read_pdf) -> bool:
    """레코드 하나를 채운다. 무엇이든 시도했으면 True(=표시를 남긴다).

    `read` 를 주입할 수 있어 테스트가 진짜 PDF 없이 돈다.
    """
    rec.abstract_tried = True
    try:
        data = fetch(rec.file_url)
    except Exception as exc:                 # noqa: BLE001
        rec.abstract_note = f'내려받기 실패: {exc}'[:200]
        return True
    if len(data) > MAX_BYTES:
        rec.abstract_note = f'파일이 너무 큼({len(data) // 1024 // 1024}MB)'
        return True
    try:
        pages = read(data)
    except Exception as exc:                 # noqa: BLE001
        rec.abstract_note = f'PDF 를 열 수 없음: {exc}'[:200]
        return True
    if not pages or not any(p.strip() for p in pages):
        # 스캔 이미지본이다(KEIS 인력수급전망이 그렇다). OCR 없이는 못 읽는다.
        rec.abstract_note = '텍스트가 없는 스캔본'
        return True
    rec.abstract = pdf_abstract.extract(pages)
    if not rec.abstract:
        rec.abstract_note = '요약 섹션 없음'
    return True


def main(argv=None, *, fetch: Optional[Callable[[str], bytes]] = None,
         read: Optional[Callable[[bytes], list[str]]] = None) -> int:
    """`fetch`·`read` 를 주입하면 네트워크에도 PDF 라이브러리에도 안 나간다."""
    ap = argparse.ArgumentParser()
    ap.add_argument('--cap', type=int, default=CAP)
    ap.add_argument('--board')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    getter = fetch or (lambda url: http.get_bytes(url))
    throttle = http.Throttle(delay=DELAY)
    done = 0

    for board in boards_mod.load_boards():
        if done >= args.cap:
            break
        if not board.enabled or (args.board and board.id != args.board):
            continue
        path = store.raw_path(board.id, board.org)
        records = store.load_raw(path)
        targets = [r for r in records if needs_text(r)]
        if not targets:
            continue
        changed = 0
        filled = {'abstract': 0, 'none': 0}     # 게시판마다 새로 센다
        for rec in targets:
            if done >= args.cap:
                break
            if args.dry_run:
                done += 1
                continue
            throttle.wait()
            enrich_record(rec, fetch=getter, read=read or read_pdf)
            rec.collected_at = datetime.now(KST).isoformat(timespec='seconds')
            done += 1
            changed += 1
            if rec.abstract:
                filled['abstract'] += 1
            else:
                filled['none'] += 1
        if changed:
            store.save_raw(path, records)
            print(f'{board.id}: {changed}건 시도 '
                  f"(초록 {filled['abstract']} 없음 {filled['none']})")

    print(f'총 {done}건 시도')
    if not args.dry_run and done:
        build_mod.main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
