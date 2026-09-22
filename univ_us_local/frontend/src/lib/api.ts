import type { CalEvent, Course, Status, SyncState, UserEventInput } from "./types";

// 개발 중에는 next.config.ts 의 rewrites 가 /api → 127.0.0.1:8000 으로 넘기고,
// 정적 export 를 FastAPI 가 서빙할 때는 같은 origin 이라 그대로 /api 가 통한다.
const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  events: () => req<CalEvent[]>("/events"),
  courses: () => req<Course[]>("/courses"),
  status: () => req<Status>("/status"),
  createEvent: (body: UserEventInput) => req<CalEvent>("/events", { method: "POST", body: JSON.stringify(body) }),
  updateEvent: (id: string, body: Partial<UserEventInput>) =>
    req<CalEvent>(`/events/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteEvent: (id: string) => req<void>(`/events/${encodeURIComponent(id)}`, { method: "DELETE" }),
  startSync: () => req<SyncState>("/sync", { method: "POST" }),
};
