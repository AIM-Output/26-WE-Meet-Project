import { exports } from 'cloudflare:workers';

/** 앱이 만들 법한 무작위 토큰 (64자 hex = 256비트) */
export function newToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

type ApiOptions = { token?: string; body?: unknown; rawBody?: string; accept?: string };

/**
 * 서버 코드에 요청 하나 — 실제 진입점(src/index.ts 의 default export)을 그대로 지난다.
 * public/ 의 정적 파일은 Cloudflare 가 코드보다 먼저 내주므로 여기로는 오지 않는다(그쪽은 env.ASSETS 로 확인).
 */
export async function api(method: string, path: string, options: ApiOptions = {}) {
  const headers = new Headers();
  if (options.accept) headers.set('Accept', options.accept);
  if (options.token) headers.set('Authorization', `Bearer ${options.token}`);
  let body: string | undefined = options.rawBody;
  if (options.body !== undefined) body = JSON.stringify(options.body);
  if (body !== undefined) headers.set('Content-Type', 'application/json');

  const response = await exports.default.fetch(
    new Request(`https://server.test${path}`, { method, headers, body, redirect: 'manual' }),
  );
  const isJson = (response.headers.get('Content-Type') ?? '').includes('application/json');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const json: any = isJson ? await response.json() : null;
  const text = isJson ? '' : await response.text();
  return { status: response.status, headers: response.headers, json, text };
}

/** 새 익명 사용자를 등록하고 토큰과 id 를 돌려준다. 테스트끼리 데이터가 섞이지 않게 매번 새로 만든다. */
export async function registerUser(): Promise<{ token: string; id: string }> {
  const token = newToken();
  const res = await api('POST', '/v1/users', { token });
  if (res.status !== 201) throw new Error(`사용자 등록 실패: ${res.status}`);
  return { token, id: res.json.user.id };
}
