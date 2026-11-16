import { env } from 'cloudflare:workers';
import { describe, expect, it } from 'vitest';
import { api, newToken, registerUser } from './helpers';

describe('익명 등록 · 인증', () => {
  it('처음 등록은 201, 같은 토큰으로 다시 부르면 200 과 같은 사용자', async () => {
    const token = newToken();
    const first = await api('POST', '/v1/users', { token });
    expect(first.status).toBe(201);
    const again = await api('POST', '/v1/users', { token });
    expect(again.status).toBe(200);
    expect(again.json.user.id).toBe(first.json.user.id);
  });

  it('서버에는 토큰이 아니라 해시만 남는다', async () => {
    const { token, id } = await registerUser();
    const row = await env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(id).first<Record<string, unknown>>();
    expect(row).not.toBeNull();
    expect(JSON.stringify(row)).not.toContain(token);
    expect(row!.key_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('토큰이 없거나 짧으면 401', async () => {
    expect((await api('POST', '/v1/users')).status).toBe(401);
    expect((await api('POST', '/v1/users', { token: 'short' })).status).toBe(401);
    expect((await api('GET', '/v1/users/me')).json.error.code).toBe('unauthorized');
  });

  it('등록하지 않은 토큰은 401 unknown_user', async () => {
    const res = await api('GET', '/v1/users/me', { token: newToken() });
    expect(res.status).toBe(401);
    expect(res.json.error.code).toBe('unknown_user');
  });

  it('등록한 토큰은 자기 id 를 받는다', async () => {
    const { token, id } = await registerUser();
    const res = await api('GET', '/v1/users/me', { token });
    expect(res.status).toBe(200);
    expect(res.json.user.id).toBe(id);
  });
});
