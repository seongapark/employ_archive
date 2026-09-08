// 슬롯 ↔ capability 대조. **이 판정은 코드가 한다** — LLM 에 맡기면 같은 질문에
// 매번 다른 소스를 골라 재현성이 없어지고, 보고서 근거로 못 쓴다(기획서 §2-2).

const J = (s) => { try { return JSON.parse(s ?? '[]'); } catch { return []; } };

export async function route(deps, 슬롯) {
  const caps = await deps.db.all(
    'SELECT source_id, 주제, 집단축, 지역입도, 시간입도, 기간_from, 기간_to FROM capability');
  const limits = await deps.db.all(
    'SELECT id, source_id, 유형, axis, category, 내용, 사유 FROM capability_limit');

  const 가능 = [], 부분 = [], 불가 = [];
  const 요청축 = 슬롯.집단축 ?? [];

  for (const c of caps) {
    const 축 = J(c.집단축);
    const 시간 = J(c.시간입도);
    const 지역 = J(c.지역입도);
    const 되는축 = 요청축.filter((a) => 축.includes(a));
    const 안되는축 = 요청축.filter((a) => !축.includes(a));

    const 시간불가 = 슬롯.시간입도 && !시간.includes(슬롯.시간입도);
    const 지역불가 = 슬롯.지역입도 && !지역.includes(슬롯.지역입도);

    if (시간불가 || 지역불가 || (요청축.length && 되는축.length === 0)) {
      const lim = limits.find((l) => l.source_id === c.source_id && 안되는축.includes(l.axis));
      const 사유 = lim ? `${lim.내용} (${lim.사유})`
        : 시간불가 ? `${슬롯.시간입도} 단위를 내지 않는다`
        : 지역불가 ? `${슬롯.지역입도} 입도를 내지 않는다`
        : '요청한 축을 내지 않는다';
      // 요청축이 아예 어휘 밖이면 그 출처는 후보가 아니다 — 불가로도 세지 않는다
      if (요청축.length && !축.some((a) => 요청축.includes(a)) && !lim && !시간불가 && !지역불가) continue;
      불가.push({ source: c.source_id, 사유, limit_id: lim?.id ?? null });
    } else if (안되는축.length) {
      부분.push({ source: c.source_id,
                  사유: `${되는축.join('·')} 은 되고 ${안되는축.join('·')} 은 안 된다` });
    } else {
      가능.push(c.source_id);
    }
  }

  // "못 준다" 로 끝내지 않는다 — 같은 축을 내는 다른 출처를 우회로 제시한다
  const 우회 = 불가.length && 가능.length
    ? [{ 경로: `${가능.join(' · ')} 는 같은 축을 발표한다`, 제약: '모집단이 달라 증감 방향만 대조', 승인: '불요' }]
    : [];

  return { 가능, 부분, 불가, 우회 };
}
