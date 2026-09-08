// D1 을 얇게 감싼다. core 는 이 모양만 알면 되고, 테스트는 가짜를 주입한다.
export function d1(binding) {
  return {
    async all(sql, params = []) {
      const { results } = await binding.prepare(sql).bind(...params).all();
      return results ?? [];
    },
  };
}
