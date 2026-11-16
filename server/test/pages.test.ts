import { env } from 'cloudflare:workers';
import { describe, expect, it } from 'vitest';

// public/ 의 웹 페이지 — Cloudflare 가 코드보다 먼저 내주는 파일이라 env.ASSETS 로 직접 읽어 확인한다.
// 여기서 지키는 것: 깨진 링크가 없다 · 차례와 스케치북의 쪽이 맞는다 · CSP(_headers)가 막을 인라인 코드가 없다.

const ORIGIN = 'https://server.test';

async function read(path: string): Promise<string> {
  const res = await env.ASSETS.fetch(`${ORIGIN}${path}`);
  expect(res.status, path).toBe(200);
  return res.text();
}

async function exists(path: string): Promise<void> {
  const res = await env.ASSETS.fetch(`${ORIGIN}${path}`);
  expect(res.status, path).toBe(200);
  await res.arrayBuffer();
}

/** 페이지가 가리키는 이 서버의 파일들 (/download 같은 코드 주소와 # 는 뺀다) */
function localFiles(html: string): string[] {
  const found = [...html.matchAll(/(?:href|src)="(\/[^"#?]+)"/g)].map((m) => m[1]!);
  return [...new Set(found)].filter((path) => path !== '/download');
}

describe('웹 페이지 (public/)', () => {
  it('첫 화면에 제목과 내려받기 버튼이 있다', async () => {
    const html = await read('/');
    expect(html).toContain('<title>유니버스 Univ-Us</title>');
    expect(html).toContain('href="/download"');
    expect(html).toMatch(/<h1[^>]*>[^<]+/);
  });

  it('첫 화면과 404 페이지가 가리키는 파일이 전부 있다', async () => {
    for (const page of ['/', '/404']) {
      const files = localFiles(await read(page));
      expect(files.length, page).toBeGreaterThan(2);
      for (const file of files) await exists(file);
    }
  });

  it('글꼴 CSS 가 가리키는 글꼴 파일이 전부 있다', async () => {
    const pretendard = await read('/fonts/pretendard/pretendardvariable-dynamic-subset.css');
    const subsets = [...pretendard.matchAll(/url\(\.\/(woff2-dynamic-subset\/[^)]+\.woff2)\)/g)].map((m) => m[1]!);
    expect(subsets.length).toBeGreaterThan(50);
    for (const file of subsets) await exists(`/fonts/pretendard/${file}`);

    const styles = await read('/styles.css');
    const fonts = [...styles.matchAll(/url\('(\/fonts\/[^']+)'\)/g)].map((m) => m[1]!);
    expect(fonts.length).toBeGreaterThan(0);
    for (const file of fonts) await exists(file);
  });

  it('인라인 스타일·스크립트가 없다 — _headers 의 CSP 가 막기 때문', async () => {
    for (const page of ['/', '/404']) {
      const html = await read(page);
      expect(html, page).not.toMatch(/\sstyle="/);
      expect(html, page).not.toMatch(/<style[\s>]/);
      expect(html, page).not.toMatch(/<script(?![^>]*\ssrc=)[^>]*>/);
      expect(html, page).not.toMatch(/\son[a-z]+="/);
    }
  });
});

describe('스케치북', () => {
  it('종이 한 장(.leaf)마다 앞뒤 두 쪽이 있다', async () => {
    const html = await read('/');
    const leaves = html.match(/class="leaf"/g)?.length ?? 0;
    const faces = html.match(/class="page[ "]/g)?.length ?? 0;
    expect(leaves).toBeGreaterThan(1);
    expect(faces).toBe(leaves * 2);
  });

  it('# 링크마다 가리키는 곳이 있고, 그림이 있는 쪽은 전부 차례에 있다', async () => {
    const html = await read('/');
    const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]!));
    const anchors = [...html.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]!);
    for (const anchor of anchors) expect(ids.has(anchor), `#${anchor}`).toBe(true);

    const plates = [...html.matchAll(/<article class="page plate[^"]*" id="([^"]+)"/g)].map((m) => m[1]!);
    expect(plates.length).toBeGreaterThan(8);
    for (const plate of plates) expect(anchors, `차례에 #${plate} 없음`).toContain(plate);
  });

  it('쪽마다 제목(data-title)이 있다 — 화면 낭독기에 지금 쪽을 알려 줄 때 쓴다', async () => {
    const html = await read('/');
    const pages = [...html.matchAll(/<article class="page [^>]*>/g)].map((m) => m[0]);
    expect(pages.length).toBeGreaterThan(8);
    for (const tag of pages) expect(tag).toMatch(/data-title="[^"]+"/);
  });
});
