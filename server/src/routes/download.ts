import { Hono } from 'hono';
import type { AppEnv } from '../env';

export const download = new Hono<AppEnv>();

// 설치파일 원본은 GitHub Releases 에 둔다(Workers 정적 파일은 하나에 25 MiB 까지라 47MB 설치파일을 못 올린다).
// 여기서는 버전이 바뀌어도 변하지 않는 주소만 내준다 — 공유하는 링크는 항상 `/download`.
download.get('/', (c) => c.redirect(c.env.RELEASES_URL, 302));
