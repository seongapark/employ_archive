# -*- coding: utf-8 -*-
"""
고용행정통계 보도자료(hwpx) 파서 + 기사 제목 매핑

기능 3가지만:
  1. parse_release(hwpx)  보도자료 → 항목사전·시계열·배포일정·본문
  2. analyze_title(title) 기사 제목 → 매칭 항목 + 보도자료 밖 키워드
  3. CLI            python press_parser.py <hwpx> [--titles titles.txt]

의존: lxml
"""
import io, json, os, re, sys, zipfile, unicodedata
from lxml import etree

NS = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'

# 산업 외 고정 어휘 (보도자료가 실어오지 않는 축)
AGE = ['29세이하', '30대', '40대', '50대', '60세이상', '청년', '고령']
SEX = ['남성', '여성']
IDX = ['고용보험', '가입자', '피보험자', '구직급여', '신규신청', '지급자',
       '지급액', '신규구인', '신규구직', '구인배수']
# 논조 표현 — 밖 키워드가 아니라 '프레임' 신호로 따로 분류
# 언론 통칭 ↔ 보도자료 산업분류 (보도자료에 없는 통칭을 산업축으로 흡수)
NICK = {'반도체': '전자·통신', '조선': '기타운송장비', '조선업': '기타운송장비',
        '자동차': '자동차', '철강': '1차금속', '바이오': '의료용물질·의약품'}

TONE = ['빨간불', '경고등', '한파', '훈풍', '악화', '개선', '부진', '회복',
        '양극화', '쇼크', '위축', '둔화', '급감', '급증']

_JOSA = re.compile(r'(은|는|이|가|을|를|의|에|에서|으로|로|도|만|와|과|보다|까지|부터|에도|에는)$')
_TAIL = re.compile(r'(다|고|서|며|어|아|지|나|음|함|됨)$')
_CONJ = re.compile(r'(었|았|졌|혔|랐|섰|왔|났|했|린|힌|긴|킨|면|져|어|아)$')  # 용언 활용형
_QTY = re.compile(r'^(만명|천명|억원|만원|명대|명째)')   # 수량 표현 잔여 조각


def _norm(s):
    return re.sub(r'[\s·‧・,]', '', unicodedata.normalize('NFKC', s))


def _cell(tc):
    return ' '.join(''.join(p.itertext()).strip() for p in tc.iter(NS + 'p')).strip()


def cache_path(hwpx_path):
    """파싱 결과를 담아 둘 자리 — hwpx 옆에 같은 이름의 .json."""
    return os.path.splitext(hwpx_path)[0] + '.json'


def have_release(hwpx_path):
    """이 회차를 조립할 수 있나. hwpx 든 캐시든 하나만 있으면 된다."""
    return os.path.exists(hwpx_path) or os.path.exists(cache_path(hwpx_path))


def parse_release(hwpx_path):
    """보도자료 hwpx → {alias, series, schedule, body}

    **hwpx 가 없으면 캐시로 버틴다.** hwpx 는 회차당 1.4MB 라 저장소에 안 담고
    매번 고용노동부 게시판에서 다시 받는데, 게시판이 한 번 안 열리면 그날 모든
    회차가 「보도자료가 없다」로 건너뛰어진다 — 2026-09-14 에 실제로 세 회차가
    한꺼번에 빠져 `회차 3 → 0` 방어가 걸렸고 수집이 통째로 죽었다. 게시판이
    비어 보인 것이지 실제로 비어 있던 것이 아니다(같은 코드가 로컬에서는 56개월을
    읽었다).

    그래서 파싱 결과(회차당 104KB)는 담는다. hwpx 가 있으면 파싱하고 결과를
    옆에 남기고, 없으면 남겨 둔 것으로 조립한다. 첫 수집 때 한 번만 게시판이
    필요하고, 그다음부터 그 회차는 네트워크와 무관해진다.
    """
    cache = cache_path(hwpx_path)
    if not os.path.exists(hwpx_path):
        with io.open(cache, encoding='utf-8') as f:
            return json.load(f)
    rel = _parse_hwpx(hwpx_path)
    with io.open(cache, 'w', encoding='utf-8') as f:
        json.dump(rel, f, ensure_ascii=False)
    return rel


def _parse_hwpx(hwpx_path):
    with zipfile.ZipFile(hwpx_path) as z:
        xml = z.read('Contents/section0.xml')
    root = etree.fromstring(xml)

    # 본문 문단 (중복 제거, 순서 유지)
    seen, paras = set(), []
    for p in root.iter(NS + 'p'):
        t = ''.join(p.itertext()).strip()
        if t and t not in seen:
            seen.add(t)
            paras.append(t)
    body = '\n'.join(paras)

    # 표 (행·열 구조)
    tables = [[[_cell(tc) for tc in tr.findall(NS + 'tc')]
               for tr in tbl.findall(NS + 'tr')] for tbl in root.iter(NS + 'tbl')]

    # 참고2: 약칭 산업분류명 ↔ 표준산업분류명  (6열 2세트 반복)
    alias = {}
    for rows in tables:
        if not rows or '약칭 산업분류명' not in ' '.join(rows[0]):
            continue
        for r in rows[1:]:
            for off in (0, 3):
                if len(r) > off + 2:
                    code, short, full = r[off].strip(), r[off + 1].strip(), r[off + 2].strip()
                    if short and full:
                        alias[short] = {'부호': code, '표준산업분류명': full}

    # ▸ 시계열
    series = []
    for line in paras:
        if not line.startswith('▸'):
            continue
        m = re.match(r'▸\s*(.+?)\s*:\s*(.+)$', line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        unit = None
        mu = re.search(r'\(([^()]*(?:명|원)|구인/구직)\)$', name)
        if mu:
            unit, name = mu.group(1), name[:mu.start()].strip()
        pts = [{'시점': a, '값': float(b)} for a, b in
               re.findall(r'\(([^)]+)\)\s*(-?\d+(?:\.\d+)?)', rest)]
        series.append({'항목': name, '단위': unit, '계열': pts})

    # 참고3: 배포 일정 (작성기준월 행 다음 2행)
    schedule = {}
    for rows in tables:
        flat = [c for r in rows for c in r]
        if '작성기준월' in flat and len(rows) >= 3:
            months, dates = rows[-2], rows[-1]
            schedule = {m.strip(): d.strip() for m, d in zip(months, dates) if m.strip()}
            break

    return {'alias': alias, 'series': series, 'schedule': schedule, 'body': body}


def build_dict(release):
    """항목사전: {정규화키: (축, 표시명)}"""
    d = {}
    for k in release['alias']:
        d[_norm(k)] = ('산업', k)
    for axis, words in (('연령', AGE), ('성', SEX), ('지표', IDX)):
        for k in words:
            d[_norm(k)] = (axis, k)
    for nick, std in NICK.items():
        d.setdefault(_norm(nick), ('산업', f'{nick}({std})'))
    return d


def analyze_title(title, item_dict, body):
    """기사 제목 → (매칭항목, 논조표현, 보도자료 밖 키워드)"""
    nt, nbody = _norm(title), _norm(body)
    used = [False] * len(nt)
    hits = []
    for k in sorted(item_dict, key=len, reverse=True):   # 최장 매칭 우선
        i = nt.find(k)
        while i >= 0:
            if not any(used[i:i + len(k)]):
                used[i:i + len(k)] = [True] * len(k)
                hits.append(item_dict[k])
                break
            i = nt.find(k, i + 1)

    tone = [t for t in TONE if _norm(t) in nt]
    outside = []
    for w in re.findall(r'[가-힣]{2,8}|[A-Za-z]{2,10}', title):
        w = _TAIL.sub('', _JOSA.sub('', w))
        if len(w) < 2 or _QTY.match(w) or _CONJ.search(w):
            continue
        if _norm(w) in item_dict or _norm(w) in nbody or w in tone:
            continue
        outside.append(w)
    return sorted(set(hits)), sorted(set(tone)), sorted(set(outside))


if __name__ == '__main__':
    rel = parse_release(sys.argv[1])
    d = build_dict(rel)
    print(f"항목사전 {len(d)}건 (산업 {len(rel['alias'])}) · 시계열 {len(rel['series'])}건 "
          f"· 배포일정 {len(rel['schedule'])}개월")
    if '--titles' in sys.argv:
        for line in io.open(sys.argv[sys.argv.index('--titles') + 1], encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            h, t, o = analyze_title(line, d, rel['body'])
            print(f"\n{line}")
            print(f"  매칭: {', '.join(f'{a}:{b}' for a, b in h) or '-'}")
            print(f"  논조: {', '.join(t) or '-'}")
            print(f"  ⚠밖: {', '.join(o) or '-'}")
    else:
        json.dump(rel, io.open('release.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print("→ release.json 저장")
