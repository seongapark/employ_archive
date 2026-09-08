import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { normalize, TYPES, 카테고리_SYN, 축_SYN } from '../../worker/src/core/classify.mjs';

// **어휘는 실데이터에서 유도한다 — 손으로 적지 않는다.**
// 예전 이 파일은 어휘를 리터럴로 적어 뒀고 집단축에 `직업` 을 손으로 넣어 뒀다.
// 그런데 실제 어휘는 routes.mjs 가 `capability.집단축` 합집합으로 만들고 그 값은
// `[산업, 성, 연령]` 이라 `직업` 이 없다 — 손으로 적어 둔 어휘가 실데이터와 어긋나
// "간판 질문(청년 사무직은 왜 줄었나)이 1패스를 태우는 순간 메타한계로 떨어진다" 는
// 결함을 통째로 가렸다(최종 리뷰 Critical 2). 그래서 routes.mjs 의 `어휘()` 와 **같은
// 식**으로 capabilities.json 에서 유도한다 — 카탈로그가 바뀌면 픽스처도 따라간다.
//
// 어휘.주제 는 capability.주제 **원문**이다(짧은 정규형이 아니다). route() 가 슬롯.주제 를
// capability.주제 와 정확 일치로 대조하므로, 짧은 정규형("취업자")을 어휘에 넣으면
// route 단계에서 후보가 통째로 사라진다.
const CAPS = JSON.parse(readFileSync(
  new URL('../../data/capabilities.json', import.meta.url), 'utf8')).capabilities;
const 어휘 = {
  주제: [...new Set(CAPS.flatMap((c) => c.주제 ?? []))],
  집단축: [...new Set(CAPS.flatMap((c) => c.집단축 ?? []))],
};

test('어휘 픽스처는 카탈로그에서 유도된다 — 손으로 적은 값이 아니다', () => {
  assert.deepEqual([...어휘.주제].sort(), ['상시가입자수', '종사자수', '취업자수'].sort());
  // `직업` 은 카탈로그 어휘에 **없다**. 이 단언이 깨지는 날은 보유 출처가 직업축을
  // 내기 시작한 날이고, 그때는 아래 '직업' 테스트의 전제가 사라진 것이다.
  assert.ok(!어휘.집단축.includes('직업'),
            'capability 가 직업축을 내기 시작했다면 아래 직업축 테스트의 전제를 다시 봐라');
});
const ok = { 유형: '수치조회', 확신도: 0.9,
  슬롯: { 주제: '취업자수', 집단축: ['연령'], 지역입도: '전국', 시간입도: '월',
          기간: { from: '2026-07', to: '2026-07' }, 출처: [] } };

test('유형 6종을 고정한다', () => {
  assert.deepEqual(TYPES,
    ['수치조회', '출처비교', '메타한계', '전망', '원인탐색', '범위밖']);
});

test('정상 입력은 그대로 통과한다', () => {
  const r = normalize(ok, { 어휘 });
  assert.equal(r.유형, '수치조회');
  assert.equal(r.저확신, false);
});

test('모르는 유형은 메타한계로 떨어진다', () => {
  const r = normalize({ ...ok, 유형: '수치조회x' }, { 어휘 });
  assert.equal(r.유형, '메타한계');
  assert.ok(r.저확신사유.some((s) => s.includes('유형')));
});

test('확신도가 임계 미만이면 메타한계로 떨어진다', () => {
  const r = normalize({ ...ok, 확신도: 0.4 }, { 어휘 });
  assert.equal(r.유형, '메타한계');
  assert.equal(r.저확신, true);
});

test('동의어를 카탈로그 어휘로 매핑한다', () => {
  // Task 0 실측: LLM 이 실제로 내는 값은 "고용"·"청년"·"성별"·"30대" 다.
  // enum 으로 스키마를 좁히면 45초를 넘겨 못 쓰므로, 어휘 강제는 코드가 한다.
  const r = normalize({ ...ok, 슬롯: { ...ok.슬롯, 주제: '고용', 집단축: ['성별', '30대'] } },
                      { 어휘 });
  assert.equal(r.슬롯.주제, '취업자수');
  assert.deepEqual(r.슬롯.집단축, ['성', '연령']);
  assert.equal(r.저확신, false);
});

test('매핑 결과에서 중복 축을 없앤다', () => {
  const r = normalize({ ...ok, 슬롯: { ...ok.슬롯, 집단축: ['연령', '연령대', '30대'] } },
                      { 어휘 });
  assert.deepEqual(r.슬롯.집단축, ['연령']);
});

test('매핑되지 않는 주제는 저확신이고 원문을 남긴다', () => {
  const r = normalize({ ...ok, 확신도: 0.99,
    슬롯: { ...ok.슬롯, 주제: '카페 매출' } }, { 어휘 });
  assert.equal(r.저확신, true);
  assert.equal(r.유형, '메타한계');
  assert.equal(r.슬롯.주제, '');            // 어휘가 아닌 값을 슬롯에 남기지 않는다
  assert.equal(r.원문슬롯.주제, '카페 매출'); // 화면이 "이렇게 이해했습니다" 를 보여줄 수 있게
});

// ── Critical 2(최종 리뷰): 아는 축인데 아직 못 주는 것 ≠ 알아들을 수 없는 말 ─────
test('직업축은 어휘 밖이어도 슬롯에 남고 저확신이 아니다 — 간판 질문이 도달한다', () => {
  // SYS_CLASSIFY 가 LLM 에게 직접 시키는 축이 `산업/성/연령/직업` 인데, 어휘
  // (capability.집단축 합집합)에는 `직업` 이 없다. 예전엔 여기서 저확신 → 메타한계로
  // 떨어져 "청년 사무직은 왜 줄었나"(스펙의 간판 예시)가 1패스를 태우면 답이 안 나왔다.
  // `직업` 은 정당한 축이고(카탈로그 지표가 참조한다) 다만 보유 출처가 없을 뿐이다 —
  // 그건 메타한계가 아니라 "원인탐색인데 데이터가 없다" 로 답해야 한다.
  const r = normalize({ 유형: '원인탐색', 확신도: 0.9,
    슬롯: { 주제: '청년', 집단축: ['연령', '직업'], 지역입도: '전국', 시간입도: '반기',
            기간: { from: '2023S1', to: '2025S2' }, 출처: [] } }, { 어휘 });
  assert.equal(r.저확신, false);
  assert.equal(r.유형, '원인탐색');            // 메타한계로 떨어지지 않는다
  assert.deepEqual(r.슬롯.집단축, ['연령', '직업']);
  assert.deepEqual(r.저확신사유, []);
});

test('직종·직업별 같은 동의어도 직업축으로 접힌다 — 표가 곧 아는 축의 정의다', () => {
  for (const 입력 of ['직업', '직종', '직업별']) {
    const r = normalize({ ...ok, 유형: '원인탐색',
      슬롯: { ...ok.슬롯, 집단축: [입력] } }, { 어휘 });
    assert.deepEqual(r.슬롯.집단축, ['직업'], `'${입력}' 이 직업축으로 안 접힌다`);
    assert.equal(r.저확신, false, `'${입력}' 이 저확신으로 떨어진다`);
  }
});

test('매핑되지 않는 축은 버리고 저확신으로 만든다', () => {
  const r = normalize({ ...ok, 슬롯: { ...ok.슬롯, 집단축: ['연령', '혈액형'] } }, { 어휘 });
  assert.deepEqual(r.슬롯.집단축, ['연령']);
  assert.equal(r.저확신, true);
  assert.ok(r.저확신사유.some((s) => s.includes('혈액형')));
});

test('확신도가 백분율로 오면 0~1 로 되돌린다', () => {
  // Task 0 실측: 프롬프트에 범위를 안 적으면 60 같은 값이 온다
  const r = normalize({ ...ok, 확신도: 60 }, { 어휘 });
  assert.equal(r.확신도, 0.6);
  assert.equal(r.저확신, false);
});

test('확신도가 범위 밖이면 잘라낸다', () => {
  assert.equal(normalize({ ...ok, 확신도: -3 }, { 어휘 }).확신도, 0);
  assert.equal(normalize({ ...ok, 확신도: 1000 }, { 어휘 }).확신도, 1);
});

test('슬롯 필드가 빠지면 채워 넣는다', () => {
  const r = normalize({ 유형: '전망', 확신도: 0.8, 슬롯: { 주제: '취업자' } }, { 어휘 });
  // category 는 LLM 슬롯이 아니라 코드가 집단축에서 뽑아 붙이는 파생 필드다 —
  // 그래서 SLOT_KEYS 는 6개 그대로이고, 슬롯 객체에는 7번째 키로 나온다.
  assert.deepEqual(Object.keys(r.슬롯).sort(),
    ['기간', '지역입도', '집단축', '출처', '시간입도', '주제', 'category'].sort());
  assert.deepEqual(r.슬롯.집단축, []);
  assert.deepEqual(r.슬롯.category, {});
});

test('집단축의 카테고리 값을 축과 함께 건져 낸다', () => {
  // '30대' 를 축으로만 접으면 그 값이 사라져 조회가 연령 전 구간을 돌려주고,
  // 파생이 20대와 40대 사이의 "차이" 를 만든다. 코드값은 segments.json 이 정본이다.
  const r = normalize({ 유형: '수치조회', 확신도: 0.9,
                        슬롯: { 주제: '취업자', 집단축: ['30대'] } }, { 어휘 });
  assert.deepEqual(r.슬롯.집단축, ['연령']);
  assert.deepEqual(r.슬롯.category, { 연령: '30-39' });
  assert.equal(r.저확신, false);
});

test('카테고리_SYN 의 키는 전부 축_SYN 에도 있어 실제로 도달한다', () => {
  // 한쪽에만 있으면 축 매핑이 실패해 저확신 → 메타한계로 떨어지고, 건진 카테고리가
  // 영영 안 쓰인다. '여성 취업자 몇 명' 이 답변 불가로 떨어지던 자리다.
  for (const [키, { 축, code }] of Object.entries(카테고리_SYN)) {
    assert.equal(축_SYN[키], 축, `축_SYN 에 '${키}' 가 없거나 축이 다르다`);
    const r = normalize({ 유형: '수치조회', 확신도: 0.9,
                          슬롯: { 주제: '취업자', 집단축: [키] } }, { 어휘 });
    assert.equal(r.저확신, false, `'${키}' 가 저확신으로 떨어진다`);
    assert.equal(r.유형, '수치조회', `'${키}' 가 메타한계로 떨어진다`);
    assert.deepEqual(r.슬롯.집단축, [축], `'${키}' 의 집단축`);
    assert.deepEqual(r.슬롯.category, { [축]: code }, `'${키}' 의 category`);
  }
});

test('카테고리를 못 집으면 빈 객체다 — 지어내지 않는다', () => {
  // '10대' 는 축으로는 연령이지만 segments.json 에 대응 구간이 없다
  const r = normalize({ 유형: '수치조회', 확신도: 0.9,
                        슬롯: { 주제: '취업자', 집단축: ['10대'] } }, { 어휘 });
  assert.deepEqual(r.슬롯.집단축, ['연령']);
  assert.deepEqual(r.슬롯.category, {});
});

test('LLM 이 아예 빈 응답을 줘도 떨어지지 않는다', () => {
  const r = normalize(null, { 어휘 });
  assert.equal(r.유형, '메타한계');
  assert.equal(r.저확신, true);
});

test('청년은 주제 자리와 축 자리에서 각각 다르게 매핑된다(이중 동의어 회귀)', () => {
  // 실측: LLM 은 "청년" 을 주제("청년 고용")로도, 집단축("청년별")으로도 낸다.
  // 주제_SYN 은 청년→취업자수, 축_SYN 은 청년→연령 으로 서로 다른 표에 등록돼 있다 —
  // 표가 섞이면 조용히 깨지므로 두 방향을 각각 확인한다.
  const r = normalize({ ...ok, 슬롯: { ...ok.슬롯, 주제: '청년', 집단축: ['청년'] } }, { 어휘 });
  assert.equal(r.슬롯.주제, '취업자수');
  assert.deepEqual(r.슬롯.집단축, ['연령']);
  assert.equal(r.저확신, false);
});
