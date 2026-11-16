import type { Context } from 'hono';
import { ApiError } from './errors';

export type JsonObject = Record<string, unknown>;

/** 요청 본문을 JSON 객체로 읽는다. 배열·문자열·깨진 JSON 은 400. */
export async function readJson(c: Context): Promise<JsonObject> {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    throw new ApiError(400, 'invalid_json', '요청 본문이 JSON 이 아닙니다');
  }
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    throw new ApiError(400, 'invalid_json', '요청 본문은 JSON 객체여야 합니다');
  }
  return body as JsonObject;
}

/** 앞뒤 공백을 뗀 글자 수가 min~max 인 문자열 칸. 아니면 400. */
export function text(body: JsonObject, field: string, min: number, max: number): string {
  const value = body[field];
  if (typeof value !== 'string') {
    throw new ApiError(400, 'invalid_field', `${field}: 문자열이 필요합니다`);
  }
  const trimmed = value.trim();
  const length = [...trimmed].length; // 한글·이모지도 한 글자로 센다
  if (length < min || length > max) {
    throw new ApiError(400, 'invalid_field', `${field}: ${min}~${max}자여야 합니다`);
  }
  return trimmed;
}
