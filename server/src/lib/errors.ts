import type { ContentfulStatusCode } from 'hono/utils/http-status';

/**
 * 클라이언트에 그대로 돌려줄 수 있는 오류.
 * 응답 모양은 항상 `{ "error": { "code": "...", "message": "..." } }` — 앱은 code 로 분기하고 message 는 참고용이다.
 */
export class ApiError extends Error {
  constructor(
    readonly status: ContentfulStatusCode,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export function errorBody(code: string, message: string) {
  return { error: { code, message } };
}
