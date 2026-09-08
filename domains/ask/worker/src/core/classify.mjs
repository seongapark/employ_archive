// 1패스 LLM 출력을 검증·정규화한다. LLM 이 무엇을 주든 여기서 형태가 고정된다.

export const TYPES = ['수치조회', '출처비교', '메타한계', '전망', '원인탐색', '범위밖'];
export const SLOT_KEYS = ['주제', '집단축', '지역입도', '시간입도', '기간', '출처'];
export const THRESHOLD = 0.6;
// 틀려도 손해가 가장 적은 자리로 떨어뜨린다
const FALLBACK = '메타한계';

const EMPTY = {
  주제: '', 집단축: [], 지역입도: '', 시간입도: '',
  기간: { from: '', to: '' }, 출처: [],
};

// 동의어 표. Task 0 실측에서 LLM 이 실제로 낸 값들을 담았다 —
// 스키마 enum 으로 좁히면 45초를 넘겨 못 쓰므로, 어휘 강제는 여기서 한다.
export const 주제_SYN = {
  고용: '취업자', 취업: '취업자', 취업자수: '취업자', 청년: '취업자',
  종사자수: '종사자', 피보험자: '상시가입자수', 가입자: '상시가입자수',
  구인: '신규구인', 채용: '신규구인',
};
export const 축_SYN = {
  업종: '산업', 산업별: '산업',
  성별: '성', 남녀: '성',
  연령대: '연령', 연령별: '연령', 청년: '연령',
  '10대': '연령', '20대': '연령', '30대': '연령', '40대': '연령',
  '50대': '연령', '60대': '연령',
  직종: '직업', 직업별: '직업',
};

// 어휘에 그대로 있으면 그것, 아니면 동의어 표, 둘 다 아니면 null
function mapVocab(v, syn, 어휘) {
  const s = String(v ?? '').trim();
  if (!s) return null;
  if (어휘?.length && 어휘.includes(s)) return s;
  const m = syn[s];
  if (m && (!어휘?.length || 어휘.includes(m))) return m;
  return 어휘?.length ? null : (m ?? s);
}

// LLM 이 0~1 을 안 지키는 경우가 실측됐다(60). 백분율이면 되돌리고 잘라낸다.
function clampConfidence(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0;
  const x = v > 1 && v <= 100 ? v / 100 : v;
  return Math.min(1, Math.max(0, x));
}

export function normalize(raw, { 어휘 = {} } = {}) {
  const 사유 = [];
  const r = raw ?? {};
  let 유형 = r.유형;
  if (!TYPES.includes(유형)) { 사유.push(`유형이 6종 밖이다: ${유형}`); 유형 = null; }

  const 원문슬롯 = { ...EMPTY, ...(r.슬롯 ?? {}) };
  원문슬롯.집단축 = Array.isArray(원문슬롯.집단축) ? 원문슬롯.집단축 : [];
  원문슬롯.출처 = Array.isArray(원문슬롯.출처) ? 원문슬롯.출처 : [];
  원문슬롯.기간 = { from: '', to: '', ...(원문슬롯.기간 ?? {}) };

  const 확신도 = clampConfidence(r.확신도);
  if (확신도 < THRESHOLD) 사유.push(`확신도 ${확신도} < ${THRESHOLD}`);

  // 코드 측 신호 — LLM 자기보고만 믿지 않는다
  const 주제 = mapVocab(원문슬롯.주제, 주제_SYN, 어휘.주제);
  if (!원문슬롯.주제) 사유.push('주제가 비었다');
  else if (!주제) 사유.push(`주제를 카탈로그 어휘로 매핑하지 못했다: ${원문슬롯.주제}`);

  const 집단축 = [];
  for (const ax of 원문슬롯.집단축) {
    const m = mapVocab(ax, 축_SYN, 어휘.집단축);
    if (m) { if (!집단축.includes(m)) 집단축.push(m); }
    else 사유.push(`집단축을 매핑하지 못했다: ${ax}`);
  }

  // 어휘가 아닌 값을 슬롯에 남기지 않는다 — 남기면 조회가 조용히 빈손이 된다
  const 슬롯 = { ...원문슬롯, 주제: 주제 ?? '', 집단축 };

  const 저확신 = 사유.length > 0;
  return { 유형: 저확신 ? FALLBACK : 유형, 슬롯, 원문슬롯, 확신도, 저확신, 저확신사유: 사유 };
}
