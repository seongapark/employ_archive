// 도메인 공통 셸 유틸. 도메인이 무엇을 다루는지 몰라도 되는 것만 둔다.

// 조립된 사이트에서 앱과 데이터는 항상 같은 폴더 아래 있으므로 후보 경로 폴백이
// 필요 없다. 로컬(tools.serve)도 배포와 동일한 트리를 서빙한다.
export async function loadJson(path) {
  try {
    const res = await fetch(path, { cache: 'no-cache' });
    if (res.ok) return await res.json();
  } catch {
    /* 오프라인 등 네트워크 실패 */
  }
  return null;
}
