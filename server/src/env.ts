// 이 서버가 Cloudflare 에서 받는 것(wrangler.jsonc 의 바인딩·vars)과 요청마다 들고 다니는 값.

export type Bindings = {
  DB: D1Database;
  /** public/ 의 정적 파일 (첫 화면·404 페이지 …) */
  ASSETS: Fetcher;
  RELEASES_URL: string;
};

export type Variables = {
  /** requireUser 를 지난 요청의 익명 사용자 id */
  userId: string;
};

export type AppEnv = { Bindings: Bindings; Variables: Variables };
