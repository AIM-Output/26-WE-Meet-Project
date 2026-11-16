import { Hono } from 'hono';
import pkg from '../../package.json';
import type { AppEnv } from '../env';
import { nowIso } from '../lib/crypto';

export const health = new Hono<AppEnv>();

// 앱이 "팀 기능은 인터넷 연결이 필요합니다"(F16 7절)를 띄울지 정할 때 부른다. DB 까지 닿는지 본다.
health.get('/', async (c) => {
  await c.env.DB.prepare('SELECT 1').first();
  return c.json({ ok: true, service: pkg.name, version: pkg.version, time: nowIso() });
});
