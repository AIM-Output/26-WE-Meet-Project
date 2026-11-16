import { Hono } from 'hono';
import { bodyLimit } from 'hono/body-limit';
import type { AppEnv } from './env';
import { ApiError, errorBody } from './lib/errors';
import { download } from './routes/download';
import { health } from './routes/health';
import { teams } from './routes/teams';
import { users } from './routes/users';

// 유니버스 얇은 서버 — 남의 데이터가 필요한 기능(F16·F17)만 맡는다(요구사항정의서 G5).
// 새 기능은 routes/ 에 파일을 만들고 아래에 한 줄 붙인다. API 는 /v1 아래에 둔다.
const app = new Hono<AppEnv>();

// 이 서버가 받는 본문은 전부 작은 JSON 이다 — 큰 요청은 읽기 전에 거절한다.
app.use(
  '*',
  bodyLimit({
    maxSize: 64 * 1024,
    onError: (c) => c.json(errorBody('payload_too_large', '요청이 너무 큽니다'), 413),
  }),
);

app.route('/health', health);
app.route('/download', download);
app.route('/v1/users', users);
app.route('/v1/teams', teams);

// 여기까지 왔다면 public/ 에도, 위 주소에도 없는 것이다.
// 사람이 브라우저로 연 주소면 404 페이지를, API(/v1)나 프로그램이 부른 것이면 JSON 을 준다.
app.notFound(async (c) => {
  const openedInBrowser = (c.req.header('Accept') ?? '').includes('text/html');
  if (openedInBrowser && !c.req.path.startsWith('/v1/')) {
    const page = await c.env.ASSETS.fetch(new URL('/404', c.req.url));
    return new Response(page.body, { status: 404, headers: page.headers });
  }
  return c.json(errorBody('not_found', '없는 주소입니다'), 404);
});

app.onError((err, c) => {
  if (err instanceof ApiError) {
    return c.json(errorBody(err.code, err.message), err.status);
  }
  console.error(err);
  return c.json(errorBody('internal_error', '서버 오류입니다. 잠시 후 다시 시도해 주세요'), 500);
});

export default app;
