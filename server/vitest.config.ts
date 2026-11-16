import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-pool-workers';
import { defineConfig } from 'vitest/config';

// 테스트는 Node 가 아니라 실제 Workers 런타임(workerd) 안에서 돈다 — D1 도 로컬에 진짜로 뜬다.
// 인터넷·Cloudflare 계정 없이 돌고, 배포된 DB 는 건드리지 않는다.
export default defineConfig(async () => {
  const migrations = await readD1Migrations('./migrations');
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: './wrangler.jsonc' },
        // migrations/ 의 SQL 을 테스트 안으로 넘긴다 → test/apply-migrations.ts 가 적용
        miniflare: { bindings: { TEST_MIGRATIONS: migrations } },
      }),
    ],
    test: {
      setupFiles: ['./test/apply-migrations.ts'],
    },
  };
});
