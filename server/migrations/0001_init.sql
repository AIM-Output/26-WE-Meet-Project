-- 유니버스 서버 첫 스키마 — 익명 사용자 + 팀 (요구사항정의서 F16 6절, 전역 결정 G5)
--
-- 서버에 두는 것: 익명 키의 해시 · 표시 이름 · 팀 · 초대 코드.
-- 두지 않는 것: 이름 · 학번 · 이메일 · 비밀번호 · 일정 제목 · 성적. 이 파일에 그런 칸을 만들지 않는다.
-- 시각은 전부 UTC ISO 8601 문자열(2026-11-16T03:00:00.000Z).

-- 익명 사용자. 기기 키 원본은 서버에 오지 않는다 — 앱이 보낸 토큰의 SHA-256 만 둔다.
-- id 를 key_hash 와 따로 두는 이유: 기기를 바꿀 때(복구 코드) key_hash 만 갈아 끼우고 같은 사람으로 남기기 위해서.
CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  key_hash      TEXT NOT NULL UNIQUE,
  created_at    TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL
);

CREATE TABLE teams (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  owner_id        TEXT NOT NULL REFERENCES users(id),
  invite_code     TEXT NOT NULL UNIQUE,
  created_at      TEXT NOT NULL,
  last_active_at  TEXT NOT NULL
);

-- 표시 이름은 팀마다 정한다 (F16-R02: 합류할 때 표시 이름만 묻는다).
CREATE TABLE team_members (
  team_id       TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  display_name  TEXT NOT NULL,
  joined_at     TEXT NOT NULL,
  PRIMARY KEY (team_id, user_id)
);

-- "내가 속한 팀" 조회용
CREATE INDEX idx_team_members_user ON team_members(user_id);
