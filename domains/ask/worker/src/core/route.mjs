// 슬롯 ↔ capability 대조. **이 판정은 코드가 한다** — LLM 에 맡기면 같은 질문에
// 매번 다른 소스를 골라 재현성이 없어지고, 보고서 근거로 못 쓴다(기획서 §2-2).

const J = (s) => { try { return JSON.parse(s ?? '[]'); } catch { return []; } };

export async function route(deps, 슬롯) {
  const caps = await deps.db.all(
    'SELECT source_id, 주제, 집단축, 지역입도, 시간입도, 기간_from, 기간_to FROM capability');
  const limits = await deps.db.all(
    'SELECT id, source_id, 유형, axis, category, 내용, 사유 FROM capability_limit');

  const 요청축 = 슬롯.집단축 ?? [];
  const 요청주제 = 슬롯.주제;

  // 1단계: 주제로 후보를 먼저 좁힌다. 취업자수·종사자수·상시가입자수는 각각 다른 것을
  // 재는 통계다 — 주제가 안 맞는 소스는 애초에 그 질문의 대상이 아니므로 불가로도 싣지 않는다.
  const 후보 = 요청주제
    ? caps.filter((c) => J(c.주제).includes(요청주제))
    : caps;

  const 가능 = [], 부분 = [], 불가 = [];

  // 2단계: 후보 안에서만 축·입도를 판정한다. 후보에 든 이상 반드시 셋 중 하나로
  // 떨어진다 — 조용히 증발하는 경로를 두지 않는다(죽은 continue 가드를 없앴다).
  for (const c of 후보) {
    const 축 = J(c.집단축);
    const 시간 = J(c.시간입도);
    const 지역 = J(c.지역입도);
    const 되는축 = 요청축.filter((a) => 축.includes(a));
    const 안되는축 = 요청축.filter((a) => !축.includes(a));

    const 시간불가 = 슬롯.시간입도 && !시간.includes(슬롯.시간입도);
    const 지역불가 = 슬롯.지역입도 && !지역.includes(슬롯.지역입도);
    const 축전부불가 = 요청축.length > 0 && 되는축.length === 0;

    if (시간불가 || 지역불가 || 축전부불가) {
      const lim = limits.find((l) => l.source_id === c.source_id && 안되는축.includes(l.axis));
      const 사유 = lim ? `${lim.내용} (${lim.사유})`
        : 시간불가 ? `${슬롯.시간입도} 단위를 내지 않는다`
        : 지역불가 ? `${슬롯.지역입도} 입도를 내지 않는다`
        // capability_limit 에 기록이 없다고 "안 낸다" 고 단정하지 않는다 —
        // 미등재와 불가는 다르다. evidence_status: "미확인" 항목이 실제로 있다.
        : `${안되는축.join('·')}을 낸다는 기록이 없다(카탈로그 미등재)`;
      불가.push({ source: c.source_id, 사유, limit_id: lim?.id ?? null });
    } else if (안되는축.length) {
      부분.push({ source: c.source_id,
                  사유: `${되는축.join('·')} 은 되고 ${안되는축.join('·')} 은 안 된다` });
    } else {
      가능.push(c.source_id);
    }
  }

  // 3단계: "못 준다" 로 끝내지 않는다.
  let 우회 = [];
  if (불가.length && 가능.length) {
    // 후보 안에서 같은 축을 내는 다른 출처가 있다 — 그것을 우회로 제시한다
    우회 = [{ 경로: `${가능.join(' · ')} 는 같은 축을 발표한다`,
              제약: '모집단이 달라 증감 방향만 대조', 승인: '불요' }];
  } else if (!가능.length && 요청축.length) {
    // 가능이 하나도 없다 — 정작 우회가 필요한 순간이다. 주제를 무시하고 요청 축을
    // (전부든 일부든) 내는 소스를 카탈로그 전체에서 찾아, 주제가 다르다는 것을 밝히며 제시한다.
    const 우회후보 = caps.filter((c) => {
      const 축 = J(c.집단축);
      const 시간 = J(c.시간입도);
      const 지역 = J(c.지역입도);
      const 시간ok = !슬롯.시간입도 || 시간.includes(슬롯.시간입도);
      const 지역ok = !슬롯.지역입도 || 지역.includes(슬롯.지역입도);
      return 시간ok && 지역ok && 요청축.some((a) => 축.includes(a));
    });
    if (우회후보.length) {
      const 주제들 = [...new Set(우회후보.flatMap((c) => J(c.주제)))];
      우회 = [{
        경로: `${우회후보.map((c) => c.source_id).join('·')} 는 ${요청축.join('·')}별을 발표한다`,
        제약: `다만 주제가 다르다(${주제들.join('·')})`,
        승인: '불요',
      }];
    }
  }

  return { 가능, 부분, 불가, 우회 };
}
