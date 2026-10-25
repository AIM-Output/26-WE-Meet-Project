"""osenv.ocr — OS 내장 OCR. 응답 해석은 가짜 PowerShell 로, 실제 엔진은 그 OS 에서만(Windows: 그림을 그려 읽기, macOS: Vision)."""
import base64
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from osenv import ocr


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv("UNIVUS_OCR", raising=False)
    ocr._avail = None
    yield
    ocr._avail = None


def fake_runner(lines, seen=None):
    def run(cmd, input=None, **kw):
        if seen is not None:
            seen.append((cmd, input))
        return SimpleNamespace(stdout="".join(f"{x}\n" for x in lines).encode("utf-8"), returncode=0)
    return run


def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def test_run_windows_parses_lines():
    seen = []
    out = ocr._run_windows([("image", 0, b"A"), ("pdf", 3, b"B"), ("image", 0, b"C")],
                           fake_runner([f"OK\t{b64('신청기간 : 10. 1.')}", "ERR\t그림을 열지 못했습니다"], seen))
    assert out == [(True, "신청기간 : 10. 1."), (False, "그림을 열지 못했습니다"), (False, "응답 없음")]
    cmd, payload = seen[0]
    assert cmd[-2:] == ["-File", str(ocr.PS1)] and "-ExecutionPolicy" in cmd
    assert payload.decode("ascii").splitlines() == ["image\t0\tQQ==", "pdf\t3\tQg==", "image\t0\tQw=="]   # 파일 없이 표준입력으로


def test_off_switch(monkeypatch):
    monkeypatch.setenv("UNIVUS_OCR", "off")
    st = ocr.available(runner=fake_runner([]))
    assert not st["ok"] and st["reason"] == "UNIVUS_OCR=off"
    assert ocr.image_texts([b"x"]) == [None] and ocr.pdf_text(b"x") is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 경로")
def test_windows_probe_and_batch():
    st = ocr.available(runner=fake_runner([f"OK\t{b64('ko' + chr(9) + 'True' + chr(9) + '10000')}"]))
    assert st == {"ok": True, "engine": "windows", "lang": "ko", "korean": True, "reason": ""}
    seen = []
    texts = ocr.image_texts([b"one", b"", b"two"], runner=fake_runner([f"OK\t{b64('첫째')}", f"OK\t{b64('둘째')}"], seen))
    assert texts == ["첫째", None, "둘째"]                     # 빈 그림은 보내지 않는다
    assert len(seen[0][1].decode("ascii").splitlines()) == 2
    ocr._avail = None
    st = ocr.available(runner=fake_runner([f"OK\t{b64('en-US' + chr(9) + 'False' + chr(9) + '10000')}"]))
    assert st["ok"] and not st["korean"] and "한국어" in st["reason"]


def _ps_png(path, lines):
    """Windows 의 System.Drawing 으로 글자 그림을 만든다(맑은 고딕)."""
    script = ("Add-Type -AssemblyName System.Drawing; $b = New-Object System.Drawing.Bitmap 900, 300; "
              "$g = [System.Drawing.Graphics]::FromImage($b); $g.Clear([System.Drawing.Color]::White); "
              "$f = New-Object System.Drawing.Font 'Malgun Gothic', 24; $y = 20; "
              "foreach ($t in $env:OCR_LINES.Split('|')) { $g.DrawString($t, $f, [System.Drawing.Brushes]::Black, 20, $y); $y += 60 }; "
              "$b.Save($env:OCR_OUT, [System.Drawing.Imaging.ImageFormat]::Png)")
    env = {**os.environ, "OCR_LINES": "|".join(lines), "OCR_OUT": str(path)}
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=env, check=True,
                   capture_output=True, timeout=60)


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell.exe"), reason="Windows 내장 OCR")
def test_windows_real_ocr(tmp_path):
    st = ocr.available()
    if not st["ok"] or not st["korean"]:
        pytest.skip(f"이 PC 에 한국어 OCR 이 없음: {st['reason']}")
    png = tmp_path / "notice.png"
    _ps_png(png, ["신청기간 : 2026. 10. 1. ~ 10. 20.", "모집대상 : 전남대학교 재학생", "선발인원 : 30명"])
    text = ocr.image_texts([png.read_bytes(), b"not an image"])
    flat = text[0].replace(" ", "")                            # 띄어쓰기는 엔진이 마음대로 넣는다('모집 대상')
    assert "모집대상" in flat and "전남대학교재학생" in flat and "2026" in flat
    assert text[1] is None                                     # 깨진 그림 하나로 나머지가 실패하지 않는다


def _mac_png(lines) -> bytes:
    """AppKit 으로 글자 그림을 만든다 (pyobjc-framework-Quartz 가 Cocoa 를 함께 깐다)."""
    from AppKit import (NSBitmapImageRep, NSCalibratedRGBColorSpace, NSColor, NSFont, NSFontAttributeName,
                        NSForegroundColorAttributeName, NSGraphicsContext, NSPNGFileType, NSRectFill, NSString)
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, 900, 300, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    NSColor.whiteColor().set()
    NSRectFill(((0, 0), (900, 300)))
    attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(28), NSForegroundColorAttributeName: NSColor.blackColor()}
    for i, t in enumerate(lines):
        NSString.stringWithString_(t).drawAtPoint_withAttributes_((20, 230 - i * 60), attrs)
    NSGraphicsContext.restoreGraphicsState()
    return bytes(rep.representationUsingType_properties_(NSPNGFileType, {}))


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Vision")
def test_mac_vision_real_ocr():
    st = ocr.available()
    if not st["ok"]:
        pytest.skip(st["reason"])                              # pyobjc 가 없거나 macOS 12 이하
    assert st["engine"] == "vision" and st["korean"]
    png = _mac_png(["신청기간 : 2026. 10. 1. ~ 10. 20.", "모집대상 : 전남대학교 재학생", "선발인원 : 30명"])
    text = ocr.image_texts([png, b"not an image"])
    flat = (text[0] or "").replace(" ", "")
    assert "재학생" in flat and "2026" in flat and text[0].index("2026") < text[0].index("재학생")   # 위에서 아래 순서
    assert text[1] is None
