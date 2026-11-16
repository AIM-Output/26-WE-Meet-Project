export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// 32자 — 헷갈리는 0/O, 1/I 를 뺐다. 256 이 32 의 배수라 `% 32` 에 치우침이 없다.
const INVITE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
export const INVITE_CODE_LENGTH = 6;

/** 초대 코드 6자리 (F16-R01) */
export function newInviteCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(INVITE_CODE_LENGTH));
  return [...bytes].map((b) => INVITE_ALPHABET.charAt(b % INVITE_ALPHABET.length)).join('');
}

export function nowIso(): string {
  return new Date().toISOString();
}
