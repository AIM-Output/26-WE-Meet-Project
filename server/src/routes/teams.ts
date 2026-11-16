import { Hono } from 'hono';
import type { AppEnv } from '../env';
import { requireUser } from '../lib/auth';
import { INVITE_CODE_LENGTH, newInviteCode, nowIso } from '../lib/crypto';
import { ApiError } from '../lib/errors';
import { readJson, text } from '../lib/validate';

// F16 가. 팀 만들기·합류 — 뼈대에서는 만들기 · 코드로 합류 · 내 팀 목록 · 팀 보기까지.
// 탈퇴·삭제·팀장 넘기기·코드 재발급·바쁜 시간·투표·팀 할 일은 F16 구현 때 이 폴더에 파일을 더한다.

export const teams = new Hono<AppEnv>();
teams.use('*', requireUser);

const TEAM_NAME_MAX = 40;
const DISPLAY_NAME_MAX = 20;

type TeamRow = {
  id: string;
  name: string;
  owner_id: string;
  invite_code: string;
  created_at: string;
  member_count: number;
};

const TEAM_SELECT = `
  SELECT t.id, t.name, t.owner_id, t.invite_code, t.created_at,
         (SELECT COUNT(*) FROM team_members c WHERE c.team_id = t.id) AS member_count
    FROM teams t
    JOIN team_members m ON m.team_id = t.id AND m.user_id = ?`;

function teamJson(row: TeamRow, userId: string) {
  return {
    id: row.id,
    name: row.name,
    inviteCode: row.invite_code,
    isOwner: row.owner_id === userId,
    memberCount: row.member_count,
    createdAt: row.created_at,
  };
}

/** 내가 속한 팀 하나. 팀이 없거나 내가 팀원이 아니면 똑같이 404 — 남의 팀이 있는지 알려 주지 않는다. */
async function myTeam(db: D1Database, teamId: string, userId: string): Promise<TeamRow> {
  const row = await db.prepare(`${TEAM_SELECT} WHERE t.id = ?`).bind(userId, teamId).first<TeamRow>();
  if (!row) throw new ApiError(404, 'team_not_found', '팀을 찾을 수 없습니다');
  return row;
}

// 팀 만들기 (F16-R01) — 만든 사람이 팀장이 되고 초대 코드를 받는다.
teams.post('/', async (c) => {
  const body = await readJson(c);
  const name = text(body, 'name', 1, TEAM_NAME_MAX);
  const displayName = text(body, 'displayName', 1, DISPLAY_NAME_MAX);
  const userId = c.get('userId');
  const db = c.env.DB;
  const teamId = crypto.randomUUID();
  const now = nowIso();

  // 초대 코드가 겹치면(UNIQUE) 새 코드로 다시. batch 는 한 트랜잭션이라 팀만 생기고 팀원이 빠지는 일이 없다.
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      await db.batch([
        db
          .prepare(
            'INSERT INTO teams (id, name, owner_id, invite_code, created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?)',
          )
          .bind(teamId, name, userId, newInviteCode(), now, now),
        db
          .prepare('INSERT INTO team_members (team_id, user_id, display_name, joined_at) VALUES (?, ?, ?, ?)')
          .bind(teamId, userId, displayName, now),
      ]);
      return c.json({ team: teamJson(await myTeam(db, teamId, userId), userId) }, 201);
    } catch (err) {
      if (!String(err).includes('teams.invite_code')) throw err;
    }
  }
  throw new ApiError(503, 'try_again', '잠시 후 다시 시도해 주세요');
});

// 코드로 합류 (F16-R02) — 표시 이름만 받는다. 이미 팀원이면 그대로 둔다(8절 "같은 사람이 두 번 합류").
teams.post('/join', async (c) => {
  const body = await readJson(c);
  const inviteCode = text(body, 'inviteCode', INVITE_CODE_LENGTH, INVITE_CODE_LENGTH).toUpperCase();
  const displayName = text(body, 'displayName', 1, DISPLAY_NAME_MAX);
  const userId = c.get('userId');
  const db = c.env.DB;

  const team = await db.prepare('SELECT id FROM teams WHERE invite_code = ?').bind(inviteCode).first<{ id: string }>();
  if (!team) throw new ApiError(404, 'invite_not_found', '코드를 다시 확인해 주세요');

  const now = nowIso();
  const [joined] = await db.batch([
    db
      .prepare(
        'INSERT INTO team_members (team_id, user_id, display_name, joined_at) VALUES (?, ?, ?, ?) ON CONFLICT(team_id, user_id) DO NOTHING',
      )
      .bind(team.id, userId, displayName, now),
    db.prepare('UPDATE teams SET last_active_at = ? WHERE id = ?').bind(now, team.id),
  ]);
  const isNew = (joined?.meta.changes ?? 0) > 0;
  return c.json({ team: teamJson(await myTeam(db, team.id, userId), userId) }, isNew ? 201 : 200);
});

// 내가 속한 팀 (F16-R06 — 여러 팀)
teams.get('/', async (c) => {
  const userId = c.get('userId');
  const { results } = await c.env.DB.prepare(`${TEAM_SELECT} ORDER BY t.created_at`).bind(userId).all<TeamRow>();
  return c.json({ teams: results.map((row) => teamJson(row, userId)) });
});

// 팀 하나 + 팀원 (팀원 탭 F16-S10 의 바탕)
teams.get('/:teamId', async (c) => {
  const userId = c.get('userId');
  const db = c.env.DB;
  const team = await myTeam(db, c.req.param('teamId'), userId);
  const { results } = await db
    .prepare('SELECT user_id, display_name, joined_at FROM team_members WHERE team_id = ? ORDER BY joined_at')
    .bind(team.id)
    .all<{ user_id: string; display_name: string; joined_at: string }>();
  return c.json({
    team: teamJson(team, userId),
    members: results.map((m) => ({
      id: m.user_id,
      displayName: m.display_name,
      joinedAt: m.joined_at,
      isOwner: m.user_id === team.owner_id,
      isMe: m.user_id === userId,
    })),
  });
});
