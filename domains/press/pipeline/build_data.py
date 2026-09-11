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

from .collect import ANCHOR
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
    """기사마다 판정·매칭항목·논조·밖키워드를 붙인다. 중복 제목은 하나로.

    판정을 **제목으로** 잇는다. 번호로 이으면 재수집 때 조용히 어긋난다 —
    네이버 검색 결과는 시간이 지나면 순서와 개수가 달라지므로, 같은 회차를
    다시 긁는 순간 3번 기사의 판정이 5번 기사에 붙는다. 아무 에러도 안 난다.
    번호는 제목이 없는 옛 판정 파일을 위한 폴백으로만 남긴다.
    """
    by_title = {_norm_title(x['title']): x for x in verdicts if x.get('title')}
    by_n = {x['n']: x for x in verdicts}
    seen, out = set(), []
    for i, a in enumerate(arts, start=1):
        k = _norm_title(a['title'])
        if k in seen:
            continue
        seen.add(k)
        hits, tone, kw = analyze_title(a['title'], D, body)
        got = by_title.get(k) or (by_n.get(i, {}) if not by_title else {})
        judged = bool(got)
        out.append({
            'title': a['title'],
            'url': a.get('originallink') or a.get('link') or '',
            'press': a['press'],
            'pub': a['pub'][:16],
            'cites': bool(got.get('cites')),
            'judged': judged,
            'why': got.get('why', ''),
            'hits': ['%s:%s' % (axis, name) for axis, name in hits],
            'tone': tone,
            'stance': got.get('tone', ''),
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


def stance(cited):
    """언론이 대체로 긍정적인가 부정적인가. LLM 이 기사마다 매긴 논조를 센다.

    **고정 어휘표로는 못 센다.** 어휘표 14개는 '26.8월분 인용 73건 중 10건만
    잡았고, 그 회차를 이끈 「반등 16 · 호황 8 · 호조 2」는 목록에 없어 '보도자료
    밖 표현'으로 흘러갔다 — 그 표로 셌다면 긍정 우세인 회차를 '부정 우세'로
    표시했을 것이다. 어휘를 늘려도 「구직급여 급증」과 「가입자 급증」은 못 가른다.

    **판정이 없으면 없다고 말한다.** 빈 값을 '중립'으로 접으면 LLM 키가 없는
    상태와 정말 중립인 회차가 화면에서 똑같아 보인다.
    """
    c = collections.Counter(a['stance'] for a in cited if a['stance'] in ('긍정', '부정', '중립'))
    pos, neg, neu = c['긍정'], c['부정'], c['중립']
    judged = pos + neg + neu
    if not judged:
        label = '판정 없음'
    elif pos > neg:
        label = '긍정 우세'
    elif neg > pos:
        label = '부정 우세'
    elif pos:
        label = '엇갈림'
    else:
        label = '중립'
    return {'pos': pos, 'neg': neg, 'neu': neu, 'judged': judged,
            'total': len(cited), 'label': label}


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


def graph(cited, min_node=2, min_edge=2, max_nodes=28):
    """한 기사 안에 같이 나온 말들을 이어 그 달의 보도 구조를 만든다.

    프레임은 낱말 하나가 아니라 **같이 다니는 낱말 뭉치**다 — '26.8월분의
    「제조업·반도체·반등·호황」이 한 덩어리인 것처럼. 표로는 그 뭉침이 안 보인다.

    노드가 40개를 넘으면 480px 화면에서 글자가 겹쳐 읽을 수 없게 되므로
    등장 횟수 상위만 남긴다. 잘라낸 사실은 화면이 말한다(`trimmed`).
    """
    axis_of, count = {}, collections.Counter()
    for a in cited:
        for h in a['hits']:
            ax, nm = h.split(':', 1)
            axis_of.setdefault(nm, ax)
        for w in a['kw']:
            axis_of.setdefault(w, '밖')
        for w in a['tone']:
            axis_of.setdefault(w, '논조')
        for t in _terms(a):
            count[t] += 1

    keep = [w for w, n in count.most_common() if n >= min_node][:max_nodes]
    kept = set(keep)

    pairs = collections.Counter()
    for a in cited:
        ts = sorted(t for t in _terms(a) if t in kept)
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                pairs[(ts[i], ts[j])] += 1

    idx = {w: i for i, w in enumerate(keep)}
    edges = [[idx[x], idx[y], n] for (x, y), n in pairs.items() if n >= min_edge]
    edges.sort(key=lambda e: -e[2])
    # 어디에도 안 붙는 노드는 그래프에서 점 하나로 떠돈다 — 뺀다.
    linked = {i for e in edges for i in e[:2]}
    nodes, remap = [], {}
    for i, w in enumerate(keep):
        if i in linked:
            remap[i] = len(nodes)
            nodes.append({'id': w, 'axis': axis_of.get(w, '밖'), 'n': count[w]})
    edges = [[remap[a], remap[b], n] for a, b, n in edges]
    return {'nodes': nodes, 'edges': edges,
            'trimmed': max(0, len([1 for _, n in count.items() if n >= min_node]) - len(nodes))}


def _terms(a):
    """기사 하나가 들고 있는 말들. 축이 달라도 같은 평면에 놓는다 —
    「제조업(산업)」과 「반등(밖)」이 붙어 다니는 것이 곧 프레임이다."""
    return ({h.split(':', 1)[1] for h in a['hits']} | set(a['kw']) | set(a['tone']))


def build_round(release, month, hwpx, reg, reg_v, fol=None, fol_v=None):
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
            # 수집 기준을 화면이 직접 말할 수 있게 같이 넘긴다. 검색어는 회차마다
            # 다르다(보도자료 요약부에서 파생하므로) — 화면에 박으면 틀린다.
            # 실제로 '26.6월분은 11개, 7·8월분은 3개로 긁었다. 그물 폭이 다르다는
            # 사실이 인용률 옆에 같이 보여야 한다.
            'queries': [q['query'] for q in reg.get('queries', [])],
            'anchors': list(ANCHOR),
        },
        'follow': ({'collected': fol['volume']['collected'], 'kept': len(f_all),
                    'cited': len(f_cited), 'press': len({a['press'] for a in f_cited}),
                    'window': fol.get('window', []), 'at': fol.get('collected_at', '')}
                   if fol else None),
        'coverage': cov,
        'outside': outside,
        'tone': tone,
        'stance': stance(r_cited),
        'issues': issues(r_cited),
        'rivals': rivals([a for a in r_all if not a['cites']]),
        'graph': graph(r_cited),
        'frames': frames(r_cited, f_cited) if fol else [],
        'truncated': reg.get('truncated_queries', []),
        'unjudged': sum(1 for a in r_all + f_all if not a['judged']),
    }
    return summary, {'regular': r_all, 'follow': f_all}
