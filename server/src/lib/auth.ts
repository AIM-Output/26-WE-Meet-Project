import type { Context } from 'hono';
import { createMiddleware } from 'hono/factory';
import type { AppEnv } from '../env';
import { nowIso, sha256Hex } from './crypto';
import { ApiError } from './errors';

// 익명 식별 (F16 D5, 전역 결정 G5)
//   앱(사이드카)이 기기 키를 로컬에서 만들고, 거기서 뽑은 토큰을 `Authorization: Bearer <토큰>` 으로 보낸다.
//   서버는 토큰의 SHA-256 만 저장한다 — DB 가 새도 토큰을 되살릴 수 없다.
//   토큰은 무작위 128비트 이상이어야 하므로 길이·문자를 강제한다(추측 가능한 짧은 값 거절).
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{40,128}$/;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Authorization 헤더에서 토큰을 꺼내 해시한다. 없거나 형식이 틀리면 401. */
export async function bearerKeyHash(c: Context): Promise<string> {
  const header = c.req.header('Authorization') ?? '';
  const token = header.startsWith('Bearer ') ? header.slice('Bearer '.length) : '';
  if (!TOKEN_PATTERN.test(token)) {
    throw new ApiError(401, 'unauthorized', '인증 토큰이 없거나 형식이 맞지 않습니다');
  }
  return sha256Hex(token);
}

/** 등록된 사용자만 통과시키고 `c.get('userId')` 를 채운다. */
export const requireUser = createMiddleware<AppEnv>(async (c, next) => {
  const keyHash = await bearerKeyHash(c);
  const user = await c.env.DB.prepare('SELECT id, last_seen_at FROM users WHERE key_hash = ?')
    .bind(keyHash)
    .first<{ id: string; last_seen_at: string }>();
  if (!user) {
    throw new ApiError(401, 'unknown_user', '등록되지 않은 기기입니다');
  }

  // 마지막 접속 시각은 하루에 한 번만 고친다 — 요청마다 쓰면 D1 무료 쓰기 한도(하루 10만 행)를 깎는다.
  const now = nowIso();
  if (Date.parse(now) - Date.parse(user.last_seen_at) > DAY_MS) {
    c.executionCtx.waitUntil(
      c.env.DB.prepare('UPDATE users SET last_seen_at = ? WHERE id = ?').bind(now, user.id).run(),
    );
  }

  c.set('userId', user.id);
  await next();
});
