import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalize, TYPES } from '../../worker/src/core/classify.mjs';

// 어휘.주제 는 capability.주제 원문이다(2026-09-08 실측, domains/ask/data/capabilities.json:
// eaps=["취업자수"], est=["종사자수"], ei=["상시가입자수"]) — 짧은 정규형이 아니다.
// route() 가 슬롯.주제 를 capability.주제 와 정확 일치로 대조하므로, 여기서
// 짧은 정규형("취업자")을 어휘에 넣으면 route 단계에서 후보가 통째로 사라진다.
const 어휘 = { 주제: ['취업자수', '종사자수', '상시가입자수'], 집단축: ['산업', '성', '연령', '직업'] };
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
  assert.deepEqual(Object.keys(r.슬롯).sort(),
    ['기간', '지역입도', '집단축', '출처', '시간입도', '주제'].sort());
  assert.deepEqual(r.슬롯.집단축, []);
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
