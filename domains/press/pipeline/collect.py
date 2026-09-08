# -*- coding: utf-8 -*-
"""네이버 뉴스 검색으로 그 회차 기사를 모은다 → sources/raw/

  python -m domains.press.pipeline.collect --release 2026-09-07
  python -m domains.press.pipeline.collect --release 2026-09-07 --follow

여기서는 **인용인지 판정하지 않는다.** 넓게 긁어 두고 판정은 `llm_cite` 가 한다.
수집기가 판정까지 하면, 판정 기준을 고칠 때마다 다시 수집해야 하는데
네이버 검색 API 는 검색어당 1,000건까지만 거슬러 가서 약 50일이면 못 닿는다.
**수집은 한 번뿐이고 판정은 몇 번이든 다시 할 수 있어야 한다.**

키: 환경변수 `NAVER_ID` / `NAVER_SECRET`. 방식은 `NAVER_API_MODE`(HUB|LEGACY),
없으면 HUB → LEGACY 순으로 찔러 보고 자동 판별한다.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.abspath(os.path.join(HERE, '..', 'sources', 'raw'))
RELEASES = os.path.abspath(os.path.join(HERE, '..', 'sources', 'releases'))

# 검색 API 는 두 방식이 공존한다. 구 개발자센터 방식은 2027-06-30 종료 예정이라
# 신규는 HUB 로 발급하지만, 이미 쓰던 키가 살아 있을 수 있어 둘 다 받는다.
MODES = {
    'HUB': {'url': 'https://naverapihub.apigw.ntruss.com/search/v1/news',
            'hdr': ('X-NCP-APIGW-API-KEY-ID', 'X-NCP-APIGW-API-KEY'),
            'label': 'NAVER API HUB'},
    'LEGACY': {'url': 'https://openapi.naver.com/v1/search/news.json',
               'hdr': ('X-Naver-Client-Id', 'X-Naver-Client-Secret'),
               'label': '구 개발자센터'},
}

# 매 회차 고정 검색어. 회차마다 보도자료에서 파생한 검색어가 여기에 붙는다.
FIXED = ['고용보험 가입자', '구직급여', '구인배수']

# 검색어로 승격하지 않을 것. 축 이름과, 동음이의로 무관 기사를 대량으로
# 끌어오는 항목(실측: '가구'는 후속 수집에서 50건이 들어왔고 대부분 家口였다).
GENERIC = {'연령별', '성별', '전산업', '기타', '상시'}
AMBIGUOUS = {'가구', '음료', '담배', '광업', '수도'}

# 도메인 → 언론사. 없으면 도메인을 그대로 쓴다 — 이름을 지어내지 않는다.
PRESS = {
 'yna.co.kr': '연합뉴스', 'news1.kr': '뉴스1', 'newsis.com': '뉴시스', 'newspim.com': '뉴스핌',
 'hankyung.com': '한국경제', 'mk.co.kr': '매일경제', 'sedaily.com': '서울경제',
 'fnnews.com': '파이낸셜뉴스', 'etoday.co.kr': '이투데이', 'ajunews.com': '아주경제',
 'heraldcorp.com': '헤럴드경제', 'etnews.com': '전자신문', 'chosun.com': '조선일보',
 'biz.chosun.com': '조선비즈', 'joongang.co.kr': '중앙일보', 'donga.com': '동아일보',
 'hani.co.kr': '한겨레', 'khan.co.kr': '경향신문', 'seoul.co.kr': '서울신문',
 'kmib.co.kr': '국민일보', 'segye.com': '세계일보', 'munhwa.com': '문화일보',
 'hankookilbo.com': '한국일보', 'asiae.co.kr': '아시아경제', 'mt.co.kr': '머니투데이',
 'edaily.co.kr': '이데일리', 'inews24.com': '아이뉴스24', 'dt.co.kr': '디지털타임스',
 'asiatoday.co.kr': '아시아투데이', 'newstomato.com': '뉴스토마토',
 'womennews.co.kr': '여성신문', 'koscaj.com': '대한전문건설신문',
 'newsfreezone.co.kr': '뉴스프리존', 'the-biz.co.kr': 'THE Biz', 'newscj.com': '천지일보',
 'ccdn.co.kr': '충청매일', 'knn.co.kr': 'KNN', 'youthdaily.co.kr': '청년일보',
 'electimes.com': '전기신문', 'namdonews.com': '남도일보',
 'outsourcing.co.kr': '아웃소싱타임스', 'datasom.co.kr': '데이터솜',
 'industryjournal.co.kr': '산업종합저널', 'joongangenews.com': '중앙이코노미뉴스',
}

# 넓은 그물. 이 다섯 낱말 중 하나라도 있으면 후보로 둔다.
ANCHOR = ('고용보험', '피보험자', '구직급여', '구인배수', '고용행정')


def press_of(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    host = host[4:] if host.startswith('www.') else host
    for d, name in PRESS.items():
        if host == d or host.endswith('.' + d):
            return name
    return host


def clean(s):
    return html.unescape(re.sub(r'</?b>', '', s)).strip()


def relevant(title, desc):
    """정기(배포 당일)용 그물. 배포일이라는 시점 자체가 강한 필터라 넓게 둔다."""
    blob = title + ' ' + desc
    return any(a in blob for a in ANCHOR)


def relevant_follow(title, desc, months):
    """후속(D+1~D+15)용 그물. 2주 구간이라 일반 고용노동 기사가 대량으로 섞인다.

    좁혀도 되는지 실측했다(2026-09-08, '26.7월분 후속): 이 그물이 떨어뜨린
    188건 중 앵커를 통과했을 85건을 LLM 에 물었더니 **인용이 0건**이었다.
    전부 그날의 다른 의제(청년 자발적 실업급여 논쟁)였다. 좁혀도 잃는 게 없고
    판정 호출이 회차당 다섯 번 줄어든다.
    """
    b = title + ' ' + desc
    if '고용행정' in b:
        return True
    if ('고용보험' in b or '피보험자' in b) and ('가입자' in b or '상시가입' in b):
        return True
    if months and any(x in months for x in re.findall(r'(\d+)개월', b)) and '고용' in b:
        return True
    return False


def window_of(release, follow):
    """회차 → 수집 구간. 정기는 배포 당일 하루, 후속은 그 뒤 보름."""
    d0 = datetime.strptime(release, '%Y-%m-%d').replace(tzinfo=KST)
    if follow:
        return d0 + timedelta(days=1), d0 + timedelta(days=15), 'follow'
    return d0, d0 + timedelta(days=1), 'regular'


def derive_queries(hwpx):
    """보도자료 요약부에 실제로 나온 항목명만 검색어로 승격한다.

    본문 통계표까지 훑으면 87개 산업이 전부 검색어가 되어 회차마다 수백 번
    호출하게 된다. 요약부는 그 달 무엇을 내세웠는지를 담고 있어, 거기 나온
    항목이 곧 기사가 될 항목이다.
    """
    from .press_parser import parse_release, build_dict, _norm
    rel = parse_release(hwpx)
    item = build_dict(rel)

    body = rel['body']
    i = body.find('<주요 특징>')
    j = body.find('【제조업】', i)                 # 본문 시작 = 요약 끝
    head = body[i:j] if 0 <= i < j else (body[i:i + 2000] if i >= 0 else body[:2000])
    nhead = _norm(head)

    picked = []
    for key, (axis, name) in item.items():
        if axis not in ('산업', '연령', '지표'):
            continue
        if name in GENERIC or name in AMBIGUOUS or len(name) < 2:
            continue
        if key in nhead:
            picked.append((axis, name))
    picked.sort(key=lambda x: {'산업': 0, '연령': 1, '지표': 2}[x[0]])
    # 산업·연령 단독어는 검색량이 너무 많다 — '자동차'는 하루 수천 건이고
    # '자동차 고용보험'은 몇 건이다. 앵커를 붙여 정밀 보완용으로 쓴다.
    return [n if axis == '지표' else f'{n} 고용보험' for axis, n in picked][:8], rel


def credentials():
    cid = os.environ.get('NAVER_ID', '').strip()
    sec = os.environ.get('NAVER_SECRET', '').strip()
    if not (cid and sec):
        raise RuntimeError('NAVER_ID / NAVER_SECRET 이 없다')
    return cid, sec


def headers(mode, cid, sec):
    a, b = MODES[mode]['hdr']
    return {a: cid, b: sec}


def _fetch(url, hdr, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
        return json.load(r)


def detect_mode(cid, sec, *, fetch=_fetch):
    """어느 방식 키인지 찔러 본다. 환경변수로 못 박아 두면 그걸 쓴다."""
    named = os.environ.get('NAVER_API_MODE', '').strip().upper()
    if named in MODES:
        return named
    for mode in ('HUB', 'LEGACY'):
        try:
            fetch(MODES[mode]['url'] + '?query=' + urllib.parse.quote('고용보험') + '&display=1',
                  headers(mode, cid, sec))
            return mode
        except Exception:
            continue
    raise RuntimeError('키가 두 방식 모두에서 거부됐다')


def search(q, want_from, want_to, cid, sec, mode, *, cap=1000, fetch=_fetch, log=print):
    """최신순으로 내려가며 [want_from, want_to] 구간만 담는다.

    네이버 검색 API 에는 기간 파라미터가 없다. 최신부터 한 장씩 넘겨 가는데
    검색어당 1,000건까지만 닿으므로, 배포일에서 오래 지난 회차는 구간에
    닿기 전에 끊긴다. 그때는 조용히 적게 담지 말고 `truncated` 로 알린다 —
    불완전한 수집을 완전한 것처럼 쓰면 「보도가 적었다」로 잘못 읽힌다.
    """
    hdr = headers(mode, cid, sec)
    base = MODES[mode]['url']
    kept, api_total, fetched, truncated = [], None, 0, False
    for start in range(1, cap + 1, 100):
        url = f'{base}?query={urllib.parse.quote(q)}&display=100&start={start}&sort=date'
        try:
            data = fetch(url, hdr)
        except Exception as exc:
            log(f'    ! {q} start={start} 실패: {exc}')
            break
        if api_total is None:
            api_total = data.get('total', 0)
        items = data.get('items', [])
        if not items:
            break
        fetched += len(items)
        oldest = None
        for it in items:
            pub = datetime.strptime(it['pubDate'], '%a, %d %b %Y %H:%M:%S %z').astimezone(KST)
            oldest = pub
            if want_from <= pub <= want_to:
                title, desc = clean(it['title']), clean(it.get('description', ''))
                kept.append({'title': title, 'desc': desc,
                             'link': it['link'], 'originallink': it['originallink'],
                             'press': press_of(it['originallink'] or it['link']),
                             'pub': pub.strftime('%Y-%m-%d %H:%M'), 'q': q,
                             'rel': relevant(title, desc)})
        if oldest and oldest < want_from:
            break
        time.sleep(0.1)
    else:
        truncated = True
    return kept, api_total, fetched, truncated


def run(release, hwpx=None, follow=False, *, fetch=_fetch, log=print, out_dir=None):
    cid, sec = credentials()
    mode = detect_mode(cid, sec, fetch=fetch)
    want_from, want_to, kind = window_of(release, follow)

    queries, months = list(FIXED), set()
    if hwpx and os.path.exists(hwpx):
        derived, rel = derive_queries(hwpx)
        months = {m for m in re.findall(r'(\d+)개월', rel['body']) if int(m) >= 10}
        for q in derived:
            if q not in queries:
                queries.append(q)
    else:
        log('⚠ 보도자료 hwpx 가 없다 — 기본 검색어 3개로만 긁는다(회차 파생어 없음)')

    log(f'회차 {release} · {kind} · 구간 {want_from:%m.%d}~{want_to:%m.%d} · {MODES[mode]["label"]}')
    log(f'검색어 {len(queries)}개: {", ".join(queries)}')

    seen, arts, qstat, cuts = {}, [], [], []
    for q in queries:
        kept, total, fetched, cut = search(q, want_from, want_to, cid, sec, mode,
                                           fetch=fetch, log=log)
        new = 0
        for it in kept:
            key = re.sub(r'\s+', '', it['title'])   # 같은 제목 = 같은 기사(전재·재송고)
            if key in seen:
                seen[key]['q'] += ', ' + q
            else:
                seen[key] = it
                arts.append(it)
                new += 1
        if follow:                                  # 후속은 좁은 그물로 덮어쓴다
            for x in kept:
                x['rel'] = relevant_follow(x['title'], x['desc'], months)
        rel_n = sum(1 for x in kept if x['rel'])
        qstat.append({'query': q, 'api_total': total, 'fetched': fetched, 'truncated': cut,
                      'in_window': len(kept), 'relevant': rel_n, 'new': new})
        if cut:
            cuts.append(q)
        log(f'  {q:<16} 전체 {(total or 0):>8,} | 조회 {fetched or 0:>4} | '
            f'구간내 {len(kept):>4} | 관련 {rel_n:>3} | 신규 {new:>3}'
            + ('   ⚠ 1,000건 상한 — 이 검색어는 누락됐다' if cut else ''))

    arts.sort(key=lambda x: x['pub'])
    core = [x for x in arts if x['rel']]
    out = {
        'round_release': release, 'mode': kind, 'auth': mode,
        'window': [want_from.strftime('%Y-%m-%d'), want_to.strftime('%Y-%m-%d')],
        'collected_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
        'volume': {'collected': len(arts), 'articles': len(core),
                   'press': len({x['press'] for x in core}), 'queries': len(queries)},
        'truncated_queries': cuts,
        'queries': qstat, 'articles': core,
        'excluded': [x for x in arts if not x['rel']],
    }
    dest = out_dir or RAW
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, f'articles_{release}_{kind}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    if cuts:
        log('')
        log(f'⚠ 다음 검색어가 1,000건 상한에 걸려 구간 전체를 못 훑었다: {", ".join(cuts)}')
        log('   배포일에서 너무 오래 지났다는 뜻이다. 이 회차 수집은 불완전하다.')
    log(f'■ 수집 {len(arts)}건 → 후보 {len(core)}건 · 언론사 {out["volume"]["press"]}곳')
    log(f'→ {path}')
    return out


def hwpx_for(release):
    """회차 → 보도자료 경로. 보도자료는 늘 전월 통계라 배포월의 전월을 본다."""
    d = datetime.strptime(release, '%Y-%m-%d')
    prev = d.replace(day=1) - timedelta(days=1)
    return os.path.join(RELEASES, 'ei_%s.hwpx' % prev.strftime('%Y-%m'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', required=True, help='배포일 YYYY-MM-DD')
    ap.add_argument('--follow', action='store_true', help='후속 모드(D+1 ~ D+15)')
    ap.add_argument('--hwpx', help='보도자료 hwpx (기본: sources/releases 에서 찾는다)')
    a = ap.parse_args()
    run(a.release, a.hwpx or hwpx_for(a.release), a.follow)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
