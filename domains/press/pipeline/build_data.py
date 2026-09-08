# -*- coding: utf-8 -*-
"""수집한 기사 + 인용 판정 → 앱이 읽는 JSON.

화면은 계산을 하지 않는다. 여기서 다 세어서 넘긴다 — 같은 수치가 두 곳에서
따로 계산되면 언젠가 어긋난다.

**신호(밖 키워드·논조·커버리지)는 인용 기사만으로 센다.** 인용이 아닌 기사가
섞이면 없는 프레임이 만들어진다 — 2026-09-08 실측에서 6월분 「재정」·「노동회의소」
두 개가 그렇게 생겨 초안에 헛경보를 달았다. 기사 **목록**에는 인용이 아닌 것도
남긴다(그날 무엇이 같이 돌았는지가 맥락이다). 세는 것과 보여주는 것은 다르다.
"""
from __future__ import annotations

import collections
import re

from .press_parser import parse_release, build_dict, analyze_title

# 제조업 중분류는 대분류로 굴린다 — 반도체·조선을 따로 이슈로 쪼개지 않는다.
MFG = ('반도체', '조선', '자동차', '전자·통신', '식료품', '화학', '전기장비',
       '철강', '1차금속', '금속가공', '기계장비', '의료정밀', '섬유제품',
       '고무·플라스틱', '기타운송장비')
# 커버리지 막대에 세울 축. 보도자료가 매월 같은 세 부분이라 고정으로 둔다.
SECTIONS = ['가입자수 현황', '구직급여', '고용24 구인·구직']
AGES = ['29세이하·청년', '30대', '40대', '50대', '60세이상']
INDUSTRIES = ['제조업', '건설업', '반도체', '조선', '서비스업', '도소매업', '보건복지업']

_AGE_KEY = {'29세이하·청년': ('29세이하', '청년'), '30대': ('30대',), '40대': ('40대',),
            '50대': ('50대',), '60세이상': ('60세이상', '고령')}
_SEC_KEY = {'가입자수 현황': ('고용보험', '가입자', '피보험자'),
            '구직급여': ('구직급여', '신규신청', '지급자', '지급액'),
            '고용24 구인·구직': ('신규구인', '신규구직', '구인배수')}


def _norm_title(t):
    return re.sub(r'\s+', '', t)


def enrich(arts, verdicts, D, body):
    """기사마다 판정·매칭항목·논조·밖키워드를 붙인다. 중복 제목은 하나로."""
    v = {x['n']: x for x in verdicts}
    seen, out = set(), []
    for i, a in enumerate(arts, start=1):
        k = _norm_title(a['title'])
        if k in seen:
            continue
        seen.add(k)
        hits, tone, kw = analyze_title(a['title'], D, body)
        got = v.get(i, {})
        out.append({
            'title': a['title'],
            'url': a.get('originallink') or a.get('link') or '',
            'press': a['press'],
            'pub': a['pub'][:16],
            'cites': bool(got.get('cites')),
            'why': got.get('why', ''),
            'hits': ['%s:%s' % (axis, name) for axis, name in hits],
            'tone': tone,
            'kw': [w for w in kw if not is_noise(w)],
        })
    return out


def _names(a):
    return [h.split(':', 1)[1] for h in a['hits']]


def coverage(cited):
    """보도자료가 다룬 것 중 무엇이 기사화됐나. 축마다 눈금이 달라 축 안에서만 비교한다."""
    def count(keys):
        n = 0
        for a in cited:
            names = _names(a)
            if any(any(k == nm or k in nm for nm in names) or k in a['title'] for k in keys):
                n += 1
        return n

    def roll(name):
        n = 0
        for a in cited:
            names = _names(a)
            hit = any(name in nm for nm in names) or name in a['title']
            if name == '제조업':
                hit = hit or any(any(m in nm for m in MFG) for nm in names)
            if hit:
                n += 1
        return n

    return {
        'section': [{'name': s, 'n': count(_SEC_KEY[s])} for s in SECTIONS],
        'age': [{'name': s, 'n': count(_AGE_KEY[s])} for s in AGES],
        'industry': [{'name': s, 'n': roll(s)} for s in INDUSTRIES],
    }


# 밖 키워드가 아니라 잡음인 것들. 기간·단위·편집 표기는 프레임이 아니다.
# (press_parser 의 _QTY 는 '만명·천명' 만 잡고 '개월째' 는 통과시킨다)
_NOISE = re.compile(r'^(\d+)?(개월째|개월|년째|년|달째|주째|일째|명대|명째|퍼센트)$')
STOP = {'그래픽', '사진', '표', '영상', '인포그래픽', '단독', '속보', '종합',
        '오늘', '어제', '지난달', '이번달', '전년', '올해', '내년'}
# 용언 활용형·파생 형용사('증가한', '안정적')는 프레임이 아니라 문장 조각이다.
# 프레임은 이름 꼴로 온다 — 홈플러스·반등·호황·AI·고용한파.
_DERIVED = re.compile(r'.{1,6}(적|한|된|는)$')


def is_noise(w):
    return bool(_NOISE.match(w)) or bool(_DERIVED.match(w)) or w in STOP


def signals(cited, min_count=2):
    kw = collections.Counter(w for a in cited for w in a['kw'] if not is_noise(w))
    tone = collections.Counter(w for a in cited for w in a['tone'])
    return ([{'w': w, 'n': n} for w, n in kw.most_common() if n >= min_count],
            [{'w': w, 'n': n} for w, n in tone.most_common()])


def issues(cited):
    """이슈 묶기 — 대표축(연령 > 산업)으로 군집. 없으면 '전체 가입자'."""
    g = collections.OrderedDict()
    for a in cited:
        key = None
        for axis in ('연령', '산업'):
            for h in a['hits']:
                ax, nm = h.split(':', 1)
                if ax == axis:
                    key = '제조업' if any(m in nm for m in MFG) else nm
                    break
            if key:
                break
        g.setdefault(key or '전체 가입자', []).append(a)
    rows = [{'key': k, 'n': len(v),
             'kw': [w for w, _ in collections.Counter(
                 x for a in v for x in a['kw'] if not is_noise(x)).most_common(4)],
             'heads': [{'title': a['title'], 'url': a['url'], 'press': a['press']}
                       for a in v[:5]]}
            for k, v in g.items()]
    return sorted(rows, key=lambda r: -r['n'])


def frames(reg_cited, fol_cited):
    """배포 당일 밖 키워드가 후속 구간에서 며칠째 살아있나."""
    d0 = collections.Counter(w for a in reg_cited for w in a['kw'] if not is_noise(w))
    rows = []
    for w, c0 in d0.most_common():
        if c0 < 2:
            continue
        hit = [a for a in fol_cited if w in a['title']]
        days = sorted(x['pub'][:10] for x in hit)
        rows.append({'kw': w, 'd0': c0, 'later': len(hit),
                     'first': days[0] if days else '', 'last': days[-1] if days else '',
                     'state': '확산' if len(hit) >= c0 else ('유지' if hit else '소멸')})
    return rows


# 판정 이유에서 의제 이름이 아닌 말. LLM 이 「…논의」·「…기사」로 끝맺는 버릇이 있다.
_RIVAL_STOP = {'기사', '모음', '관련', '해설', '분석', '논의', '논란', '우려', '비판',
               '지적', '소식', '내용', '보도', '발표', '다른', '여러', '묶은', '개인',
               '이슈', '문제', '상황', '현황', '전망', '주장', '반응'}


# 같은 것을 가리키는 말. 언론은 '실업급여', 보도자료는 '구직급여' 를 쓴다 —
# 붙여 두지 않으면 같은 의제가 두 덩어리로 쪼개진다('26.7월분에서 실제로 그랬다).
_RIVAL_SAME = {'실업급여': '구직급여', '피보험자': '가입자', '고용보험료': '고용보험'}


def rivals(not_cited, min_count=2):
    """인용이 아닌 기사를 의제로 묶는다.

    이것이 잡음이 아닌 이유: '26.7월분 배포 당일에 「청년 자발적 실업급여」 논쟁
    기사가 10건 같이 돌았다. 청년 가입자 46개월 연속 감소라는 통계가 나온 날에
    「청년이 실업급여 받으려 1년 못 채우고 나간다」는 프레임이 나란히 돈 것이다.
    그날의 경쟁 의제이고, 이 도메인이 봐야 할 것이다.

    묶는 근거는 LLM 이 낸 판정 이유(why)다 — 이미 의제 이름 꼴로 온다.
    제목으로 묶으면 매체마다 표현이 달라 안 모인다.
    """
    def words(a):
        out = []
        for w in re.findall(r'[가-힣]{2,8}|[A-Za-z]{2,10}', a.get('why', '')):
            if len(w) >= 2 and w not in _RIVAL_STOP:
                out.append(_RIVAL_SAME.get(w, w))
        return out

    freq = collections.Counter(w for a in not_cited for w in set(words(a)))
    topics = [w for w, n in freq.most_common() if n >= min_count]

    groups, rest = collections.OrderedDict(), []
    for a in not_cited:
        mine = set(words(a))
        hit = next((t for t in topics if t in mine), None)
        if hit is None:
            rest.append(a)
        else:
            groups.setdefault(hit, []).append(a)

    def head(v):
        return [{'title': x['title'], 'url': x['url'], 'press': x['press'],
                 'why': x.get('why', '')} for x in v[:4]]

    # 한 건짜리 묶음은 의제가 아니라 우연이다 — '그 밖' 으로 합친다.
    for t in [t for t, v in groups.items() if len(v) < min_count]:
        rest.extend(groups.pop(t))

    rows = [{'topic': t, 'n': len(v), 'heads': head(v)} for t, v in groups.items()]
    rows.sort(key=lambda r: -r['n'])
    if rest:
        rows.append({'topic': '그 밖', 'n': len(rest), 'heads': head(rest)})
    return rows


def gaps(cov, cited, body):
    """보도자료 ↔ 기사의 어긋남. 숫자를 문장으로 부풀리지 않고 사실만 적는다."""
    out = []
    zero = [s['name'] for s in cov['section'] if s['n'] == 0]
    if zero:
        out.append('보도자료 3개 섹션 중 %s 보도 0건' % ' · '.join(zero))
    svc = next((s['n'] for s in cov['industry'] if s['name'] == '서비스업'), None)
    if svc is not None and svc <= 2 and '서비스업' in body:
        out.append('요약부가 증가 견인으로 제시한 서비스업 보도 %d건' % svc)
    young = next((s['n'] for s in cov['age'] if s['name'] == '29세이하·청년'), 0)
    if cited:
        out.append('청년 보도 %d건 (%d%%)' % (young, round(young * 100 / len(cited))))
    return out


def build_round(release, month, hwpx, reg, reg_v, fol=None, fol_v=None, prev_press=None):
    """한 회차 → (요약 dict, 기사 dict)."""
    rel = parse_release(hwpx)
    D, body = build_dict(rel), rel['body']
    r_all = enrich(reg['articles'], reg_v, D, body)
    r_cited = [a for a in r_all if a['cites']]
    f_all = enrich(fol['articles'], fol_v, D, body) if fol else []
    f_cited = [a for a in f_all if a['cites']]

    press_now = {a['press'] for a in r_cited}
    outside, tone = signals(r_cited)
    cov = coverage(r_cited)
    year, mon = month.split('-')
    summary = {
        'release': release,
        'month': month,
        'label': "'%s.%d월분" % (year[2:], int(mon)),
        'title': '%s년 %d월 고용행정 통계로 본 노동시장 동향' % (year, int(mon)),
        'regular': {
            'collected': reg['volume']['collected'], 'kept': len(r_all),
            'cited': len(r_cited), 'press': len(press_now),
            'window': reg.get('window', []), 'at': reg.get('collected_at', ''),
        },
        'follow': ({'collected': fol['volume']['collected'], 'kept': len(f_all),
                    'cited': len(f_cited), 'press': len({a['press'] for a in f_cited}),
                    'window': fol.get('window', []), 'at': fol.get('collected_at', '')}
                   if fol else None),
        'coverage': cov,
        'gaps': gaps(cov, r_cited, body),
        'outside': outside,
        'tone': tone,
        'issues': issues(r_cited),
        'rivals': rivals([a for a in r_all if not a['cites']]),
        'frames': frames(r_cited, f_cited) if fol else [],
        'new_press': sorted(press_now - set(prev_press or [])) if prev_press else [],
        'all_press': sorted(press_now),
        'truncated': reg.get('truncated_queries', []),
    }
    return summary, {'regular': r_all, 'follow': f_all}
