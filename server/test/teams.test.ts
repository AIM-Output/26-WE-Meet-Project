import { describe, expect, it } from 'vitest';
import { api, registerUser } from './helpers';

async function createTeam(token: string, name = '캡스톤 3조', displayName = '서연') {
  const res = await api('POST', '/v1/teams', { token, body: { name, displayName } });
  expect(res.status).toBe(201);
  return res.json.team as { id: string; inviteCode: string };
}

describe('팀 만들기·합류 (F16 가)', () => {
  it('팀을 만들면 팀장이 되고 6자리 초대 코드를 받는다', async () => {
    const owner = await registerUser();
    const res = await api('POST', '/v1/teams', { token: owner.token, body: { name: ' 캡스톤 3조 ', displayName: '서연' } });
    expect(res.status).toBe(201);
    expect(res.json.team).toMatchObject({ name: '캡스톤 3조', isOwner: true, memberCount: 1 });
    expect(res.json.team.inviteCode).toMatch(/^[A-HJ-NP-Z2-9]{6}$/);
  });

  it('코드로 합류한다 — 소문자로 쳐도 되고, 두 번 합류해도 한 사람이다', async () => {
    const owner = await registerUser();
    const member = await registerUser();
    const team = await createTeam(owner.token);

    const joined = await api('POST', '/v1/teams/join', {
      token: member.token,
      body: { inviteCode: team.inviteCode.toLowerCase(), displayName: '민준' },
    });
    expect(joined.status).toBe(201);
    expect(joined.json.team).toMatchObject({ id: team.id, isOwner: false, memberCount: 2 });

    const again = await api('POST', '/v1/teams/join', {
      token: member.token,
      body: { inviteCode: team.inviteCode, displayName: '민준2' },
    });
    expect(again.status).toBe(200);
    expect(again.json.team.memberCount).toBe(2);
  });

  it('틀린 코드는 404 invite_not_found', async () => {
    const user = await registerUser();
    const res = await api('POST', '/v1/teams/join', { token: user.token, body: { inviteCode: 'ZZZZZZ', displayName: '민준' } });
    expect(res.status).toBe(404);
    expect(res.json.error.code).toBe('invite_not_found');
  });

  it('내 팀 목록에는 내가 속한 팀만 나온다', async () => {
    const a = await registerUser();
    const b = await registerUser();
    const teamA1 = await createTeam(a.token, 'A-1');
    const teamA2 = await createTeam(a.token, 'A-2');
    await createTeam(b.token, 'B-1');

    const res = await api('GET', '/v1/teams', { token: a.token });
    expect(res.status).toBe(200);
    expect(res.json.teams.map((t: { id: string }) => t.id).sort()).toEqual([teamA1.id, teamA2.id].sort());
  });

  it('팀 보기 — 팀원의 표시 이름과 팀장 여부', async () => {
    const owner = await registerUser();
    const member = await registerUser();
    const team = await createTeam(owner.token);
    await api('POST', '/v1/teams/join', { token: member.token, body: { inviteCode: team.inviteCode, displayName: '민준' } });

    const res = await api('GET', `/v1/teams/${team.id}`, { token: member.token });
    expect(res.status).toBe(200);
    expect(res.json.members).toHaveLength(2);
    expect(res.json.members).toContainEqual(
      expect.objectContaining({ id: owner.id, displayName: '서연', isOwner: true, isMe: false }),
    );
    expect(res.json.members).toContainEqual(
      expect.objectContaining({ id: member.id, displayName: '민준', isOwner: false, isMe: true }),
    );
  });

  it('팀원이 아니면 팀이 없는 것처럼 404', async () => {
    const owner = await registerUser();
    const outsider = await registerUser();
    const team = await createTeam(owner.token);
    const res = await api('GET', `/v1/teams/${team.id}`, { token: outsider.token });
    expect(res.status).toBe(404);
    expect(res.json.error.code).toBe('team_not_found');
  });

  it('입력 검사 — 빈 이름·깨진 JSON 은 400, 토큰 없으면 401', async () => {
    const user = await registerUser();
    const empty = await api('POST', '/v1/teams', { token: user.token, body: { name: '   ', displayName: '서연' } });
    expect(empty.status).toBe(400);
    expect(empty.json.error.code).toBe('invalid_field');

    const broken = await api('POST', '/v1/teams', { token: user.token, rawBody: '{not json' });
    expect(broken.status).toBe(400);
    expect(broken.json.error.code).toBe('invalid_json');

    const anonymous = await api('POST', '/v1/teams', { body: { name: 'x', displayName: 'y' } });
    expect(anonymous.status).toBe(401);
  });
});
