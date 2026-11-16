import { Hono } from 'hono';
import type { AppEnv } from '../env';
import { bearerKeyHash, requireUser } from '../lib/auth';
import { nowIso } from '../lib/crypto';

export const users = new Hono<AppEnv>();

// 익명 등록 — 묻는 것이 없다(이메일·비밀번호·이름 없음, F16-R02).
// 같은 토큰으로 다시 부르면 같은 사용자를 돌려준다(앱이 등록 여부를 기억하지 못해도 안전).
users.post('/', async (c) => {
  const keyHash = await bearerKeyHash(c);
  const now = nowIso();
  const inserted = await c.env.DB.prepare(
    'INSERT INTO users (id, key_hash, created_at, last_seen_at) VALUES (?, ?, ?, ?) ON CONFLICT(key_hash) DO NOTHING',
  )
    .bind(crypto.randomUUID(), keyHash, now, now)
    .run();
  const user = await c.env.DB.prepare('SELECT id, created_at FROM users WHERE key_hash = ?')
    .bind(keyHash)
    .first<{ id: string; created_at: string }>();
  const created = inserted.meta.changes > 0;
  return c.json({ user: { id: user!.id, createdAt: user!.created_at } }, created ? 201 : 200);
});

users.get('/me', requireUser, (c) => c.json({ user: { id: c.get('userId') } }));
