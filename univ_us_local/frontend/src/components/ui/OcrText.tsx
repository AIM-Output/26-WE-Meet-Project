/** 이미지(본문 포스터·스캔 첨부)에서 OS 내장 OCR 로 읽은 글자 — 장학·대외활동 상세에서 원문과 맞춰 보게 접어 둔다. */
export function OcrText({ text }: { text: string }) {
  return (
    <details className="rounded-xl border border-border px-3 py-2 text-[13px]">
      <summary className="cursor-pointer font-semibold text-muted">이미지에서 읽은 글자 (OCR — 틀릴 수 있음)</summary>
      {/* '[본문 이미지 OCR]' · '[첨부 OCR: 이름]' 머리는 수집기가 붙인 표시라 화면에서는 뺀다 */}
      <p className="mt-2 whitespace-pre-wrap text-muted">{text.replace(/^\[(?:본문 이미지 OCR|첨부 OCR:[^\]]*)\]\n?/gm, "")}</p>
    </details>
  );
}
