import { applyD1Migrations } from 'cloudflare:test';
import { env } from 'cloudflare:workers';

// 테스트 파일마다 먼저 돈다. 이미 적용된 마이그레이션은 건너뛴다.
await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
