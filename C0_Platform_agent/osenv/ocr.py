"""OS 내장 OCR — 이미지(·스캔 PDF)의 글자. 모델을 묶지 않고 OS 가 가진 엔진을 쓴다 (2026-10-25).

    Windows  Windows.Media.Ocr (WinRT) — PowerShell 5.1 이 osenv/ocr_win.ps1 을 돌린다. 설치할 것 없음.
             한국어 OCR 은 Windows 의 한국어 언어 기능에 들어 있다(한국어 Windows 는 기본). 없으면 사용자 언어로 읽고 available() 이 알린다.
             스캔 PDF 도 읽는다(Windows.Data.Pdf 로 쪽을 그려서).
    macOS    Vision (VNRecognizeTextRequest, 한국어는 macOS 13 이상) — pyobjc-framework-Vision·Quartz (desktop/sidecar/requirements.txt,
             맥에서만 설치). 스캔 PDF 는 아직 안 읽는다(None).
    그 외    없음 — available()["ok"] 가 False, 함수는 None.

    available()                 {"ok", "engine", "lang", "korean", "reason"} — 한 번 확인하고 기억한다
    image_texts([bytes, …])     이미지마다 글자(못 읽으면 None) — Windows 는 PowerShell 을 한 번만 띄워 한꺼번에
    pdf_text(bytes, pages=3)    스캔 PDF 앞 몇 쪽의 글자

UNIVUS_OCR=off 면 끈다(테스트·문제 해결용). 읽은 글자는 틀릴 수 있다 — 쓰는 쪽(F11·F12)이 'OCR 로 읽음'을 표시하고 신뢰도를 낮춘다.
파일을 만들지 않는다 — 이미지는 표준입력으로 넘기고(base64) PowerShell 은 메모리 스트림으로 연다.
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import IS_MAC, IS_WINDOWS, NO_WINDOW

PS1 = Path(__file__).with_name("ocr_win.ps1")
TIMEOUT_PER_ITEM = 60                     # 초 — 긴 포스터 한 장이 보통 2~5초
MAX_BYTES = 15 * 1024 * 1024
_avail: Optional[dict] = None


def _off() -> bool:
    return os.environ.get("UNIVUS_OCR", "").strip().lower() in ("off", "0", "false", "no")


# ── Windows (PowerShell + WinRT) ───────────────────────────────

def _powershell() -> str:
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(p) if p.exists() else "powershell.exe"


def _run_windows(items: list[tuple[str, int, bytes]], runner=subprocess.run) -> list[tuple[bool, str]]:
    """[(종류, 쪽수, 내용)] → [(성공, 글자 또는 이유)]. PowerShell 을 한 번 띄운다."""
    payload = "".join(f"{kind}\t{pages}\t{base64.b64encode(data).decode('ascii')}\n" for kind, pages, data in items)
    try:
        r = runner([_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(PS1)],
                   input=payload.encode("ascii"), capture_output=True, timeout=30 + TIMEOUT_PER_ITEM * len(items),
                   creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        return [(False, f"PowerShell 실행 실패: {type(e).__name__}")] * len(items)
    out: list[tuple[bool, str]] = []
    for line in (r.stdout or b"").decode("utf-8", "replace").splitlines():      # 글자는 base64, 이유(ERR)는 UTF-8 그대로
        head, _, rest = line.partition("\t")
        if head == "OK":
            try:
                out.append((True, base64.b64decode(rest).decode("utf-8", "replace")))
            except ValueError:
                out.append((False, "출력 해석 실패"))
        elif head == "ERR":
            out.append((False, rest.strip() or "읽기 실패"))
    out += [(False, "응답 없음")] * (len(items) - len(out))
    return out[:len(items)]


# ── macOS (Vision) ─────────────────────────────────────────────

def _vision_image(data: bytes) -> Optional[str]:
    import Quartz                                        # pyobjc-framework-Quartz
    import Vision                                        # pyobjc-framework-Vision
    from Foundation import NSData
    ns = NSData.dataWithBytes_length_(data, len(data))
    src = Quartz.CGImageSourceCreateWithData(ns, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None) if src else None
    if img is None:
        return None
    w, h = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    if w < 200 or h < 60:
        return ""
    # 세로로 긴 포스터는 나눠 읽는다(regionOfInterest — 정규화 좌표, 원점은 왼쪽 아래). 한 조각 높이 = 폭의 1.5배
    step = min(1.0, (w * 1.5) / h)
    lines: list[str] = []
    top = 1.0
    while top > 0:
        hh = min(step, top)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setRecognitionLanguages_(["ko-KR", "en-US"])
        req.setUsesLanguageCorrection_(True)
        req.setRegionOfInterest_(Quartz.CGRectMake(0, top - hh, 1, hh))
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
        ok, _err = handler.performRequests_error_([req], None)
        if not ok:
            return None
        rows = []
        for obs in req.results() or []:
            cand = obs.topCandidates_(1)
            if cand:
                bb = obs.boundingBox()
                rows.append((-(bb.origin.y + bb.size.height), bb.origin.x, str(cand[0].string())))
        lines += [t for _, _, t in sorted(rows)]
        top -= hh
    return "\n".join(lines)


def _vision_ok() -> tuple[bool, str]:
    try:
        import Vision
        req = Vision.VNRecognizeTextRequest.alloc().init()
        langs, _err = req.supportedRecognitionLanguagesAndReturnError_(None)
        return any(str(x).startswith("ko") for x in (langs or [])), "Vision"
    except Exception as e:                               # noqa: BLE001 — pyobjc 없음·오래된 macOS
        return False, f"Vision 없음 ({type(e).__name__})"


# ── 진입점 ────────────────────────────────────────────────────

def available(refresh: bool = False, runner=subprocess.run) -> dict:
    global _avail
    if _avail is not None and not refresh:
        return _avail
    res = {"ok": False, "engine": None, "lang": None, "korean": False, "reason": ""}
    if _off():
        res["reason"] = "UNIVUS_OCR=off"
    elif IS_WINDOWS:
        ok, text = _run_windows([("probe", 0, b"")], runner)[0]
        if ok:
            lang, korean, _max = (text.split("\t") + ["", "", ""])[:3]
            res.update(ok=True, engine="windows", lang=lang, korean=korean.strip().lower() == "true",
                       reason="" if korean.strip().lower() == "true" else "한국어 OCR 이 없습니다 — Windows 설정 > 언어에서 한국어를 추가하세요")
        else:
            res["reason"] = text
    elif IS_MAC:
        korean, why = _vision_ok()
        res.update(ok=korean, engine="vision" if korean else None, lang="ko-KR" if korean else None, korean=korean,
                   reason="" if korean else f"{why} — macOS 13 이상의 Vision 이 필요합니다")
    else:
        res["reason"] = f"{sys.platform} 에는 내장 OCR 이 없습니다"
    _avail = res
    return res


def image_texts(images: list[bytes], runner=subprocess.run) -> list[Optional[str]]:
    if not images:
        return []
    if not available(runner=runner)["ok"]:
        return [None] * len(images)
    keep = [d if d and len(d) <= MAX_BYTES else None for d in images]
    if IS_WINDOWS:
        todo = [(i, d) for i, d in enumerate(keep) if d]
        res = _run_windows([("image", 0, d) for _, d in todo], runner) if todo else []
        out: list[Optional[str]] = [None] * len(images)
        for (i, _), (ok, text) in zip(todo, res):
            out[i] = text if ok else None
        return out
    out = []
    for d in keep:
        try:
            out.append(_vision_image(d) if d else None)
        except Exception:                                # noqa: BLE001
            out.append(None)
    return out


def pdf_text(data: bytes, pages: int = 3, runner=subprocess.run) -> Optional[str]:
    if not data or len(data) > MAX_BYTES or not IS_WINDOWS or not available(runner=runner)["ok"]:
        return None
    ok, text = _run_windows([("pdf", pages, data)], runner)[0]
    return text if ok else None


if __name__ == "__main__":                               # python -m osenv.ocr <이미지·PDF …> — 손으로 확인
    sys.stdout.reconfigure(encoding="utf-8")
    print(available())
    for p in sys.argv[1:]:
        b = Path(p).read_bytes()
        t = pdf_text(b) if p.lower().endswith(".pdf") else image_texts([b])[0]
        print(f"── {p} ({len(t or '')}자)\n{t}")
