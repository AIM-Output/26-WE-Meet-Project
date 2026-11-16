import { env } from 'cloudflare:workers';
import { describe, expect, it } from 'vitest';
import { api } from './helpers';

describe('기본 주소', () => {
  it('GET /health — DB 까지 닿으면 ok', async () => {
    const res = await api('GET', '/health');
    expect(res.status).toBe(200);
    expect(res.json).toMatchObject({ ok: true, service: 'univ-us-server' });
    expect(res.json.version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it('GET /download — GitHub Releases 최신 버전으로 넘긴다', async () => {
    const res = await api('GET', '/download');
    expect(res.status).toBe(302);
    expect(res.headers.get('Location')).toBe(env.RELEASES_URL);
  });

  it('없는 주소는 JSON 404', async () => {
    const res = await api('GET', '/nope');
    expect(res.status).toBe(404);
    expect(res.json).toEqual({ error: { code: 'not_found', message: expect.any(String) } });
  });

  it('브라우저로 연 없는 주소는 404 페이지', async () => {
    const res = await api('GET', '/nope', { accept: 'text/html,application/xhtml+xml' });
    expect(res.status).toBe(404);
    expect(res.headers.get('Content-Type')).toContain('text/html');
    expect(res.text).toContain('페이지를 찾을 수 없습니다');
  });

  it('API 주소(/v1)는 브라우저로 열어도 JSON 404', async () => {
    const res = await api('GET', '/v1/nope', { accept: 'text/html' });
    expect(res.status).toBe(404);
    expect(res.json.error.code).toBe('not_found');
  });

  it('64KB 를 넘는 본문은 413', async () => {
    const res = await api('POST', '/v1/users', { rawBody: 'x'.repeat(70 * 1024) });
    expect(res.status).toBe(413);
    expect(res.json.error.code).toBe('payload_too_large');
  });
});
