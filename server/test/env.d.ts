// 테스트에서 `import { env, exports } from 'cloudflare:workers'` 가 알아야 하는 모양.
declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    ASSETS: Fetcher;
    RELEASES_URL: string;
    TEST_MIGRATIONS: import('cloudflare:test').D1Migration[];
  }
  interface GlobalProps {
    mainModule: typeof import('../src/index');
  }
}
