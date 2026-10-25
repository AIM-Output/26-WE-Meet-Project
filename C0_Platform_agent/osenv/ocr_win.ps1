# 유니버스 OCR — Windows 내장 OCR(Windows.Media.Ocr)로 이미지·PDF 쪽의 글자를 읽는다. osenv/ocr.py 가 부른다(Windows PowerShell 5.1).
# 설치할 것 없음 — Windows 10·11 의 언어 기능(한국어 OCR)을 쓴다. 파일을 만들지 않는다(메모리 스트림만).
#
# 표준입력: 한 줄에 하나  "<종류>`t<쪽수>`t<base64>"   종류 = probe | image | pdf (쪽수는 pdf 만 — 앞에서부터 몇 쪽)
# 표준출력: 입력 한 줄마다 "OK`t<base64(UTF-8 글자)>" 또는 "ERR`t<이유>"
#
# 긴 이미지(세로 포스터)는 세로로 잘라 읽는다 — 엔진 최대 크기(MaxImageDimension, 보통 10000px)를 넘지 않게, 그리고 글자가
# 너무 작아지지 않게. 폭이 좁은 이미지는 2배까지 키워 읽는다(작은 글자를 잘 못 읽는다). 아이콘 크기(200×60 미만)는 건너뛴다.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

function Fail([string]$why) { [Console]::Out.WriteLine("ERR`t$why"); [Console]::Out.Flush() }
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
} catch {
    while ($null -ne [Console]::In.ReadLine()) { Fail "WinRT 를 불러오지 못했습니다" }
    exit 0
}

$ext = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskOp = $ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$asTaskAct = $ext | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
function Await($op, [Type]$type) { $t = $asTaskOp.MakeGenericMethod($type).Invoke($null, @($op)); $null = $t.Wait(-1); $t.Result }
function AwaitAction($op) { $t = $asTaskAct.Invoke($null, @($op)); $null = $t.Wait(-1) }

$ko = New-Object Windows.Globalization.Language 'ko'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($ko)
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$maxDim = [int][Windows.Media.Ocr.OcrEngine]::MaxImageDimension

function Read-Decoder($dec) {
    $w = [int]$dec.OrientedPixelWidth; $h = [int]$dec.OrientedPixelHeight
    if ($w -lt 200 -or $h -lt 60) { return '' }
    $s = 1.0
    if ($w -lt 1000) { $s = [Math]::Min(2.0, 1400.0 / $w) }          # 좁은 이미지는 키운다
    if ($w * $s -gt 4000) { $s = 4000.0 / $w }                         # 넓은 이미지는 줄인다
    $sw = [int][Math]::Round($w * $s); $sh = [int][Math]::Round($h * $s)
    $chunk = [Math]::Min([Math]::Max([int]($sw * 1.5), 1600), [Math]::Min(4000, $maxDim))
    $overlap = 80
    $lines = New-Object System.Collections.Generic.List[string]
    $y = 0
    while ($y -lt $sh) {
        $ch = [Math]::Min($chunk, $sh - $y)
        if ($ch -lt 24) { break }
        $tr = New-Object Windows.Graphics.Imaging.BitmapTransform
        $tr.ScaledWidth = [uint32]$sw; $tr.ScaledHeight = [uint32]$sh
        $tr.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Fant
        $b = New-Object Windows.Graphics.Imaging.BitmapBounds
        $b.X = 0; $b.Y = [uint32]$y; $b.Width = [uint32]$sw; $b.Height = [uint32]$ch
        $tr.Bounds = $b
        $bmp = Await ($dec.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore, $tr,
            [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
            [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
        $tail = @(); if ($lines.Count) { $tail = $lines.GetRange([Math]::Max(0, $lines.Count - 3), [Math]::Min(3, $lines.Count)) }
        $i = 0
        foreach ($ln in $res.Lines) {
            $t = $ln.Text
            if ($y -gt 0 -and $i -lt 3 -and $tail -contains $t) { $i++; continue }   # 겹쳐 읽은 줄
            $lines.Add($t); $i++
        }
        $bmp.Dispose()
        if ($y + $ch -ge $sh) { break }
        $y += $chunk - $overlap
    }
    return ($lines -join "`n")
}

function Open-Stream([byte[]]$bytes) {
    $ms = New-Object System.IO.MemoryStream(, $bytes)
    return [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ms)
}

function Read-Image([byte[]]$bytes) {
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync((Open-Stream $bytes))) ([Windows.Graphics.Imaging.BitmapDecoder])
    return Read-Decoder $dec
}

function Read-Pdf([byte[]]$bytes, [int]$pages) {
    $doc = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromStreamAsync((Open-Stream $bytes))) ([Windows.Data.Pdf.PdfDocument])
    $out = New-Object System.Collections.Generic.List[string]
    $n = [Math]::Min([int]$doc.PageCount, $pages)
    for ($i = 0; $i -lt $n; $i++) {
        $page = $doc.GetPage([uint32]$i)
        $opt = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $opt.DestinationWidth = [uint32]2000                            # A4 폭 기준 약 240dpi
        $ras = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
        AwaitAction ($page.RenderToStreamAsync($ras, $opt))
        $ras.Seek(0)
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($ras)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $out.Add((Read-Decoder $dec))
        $page.Dispose()
    }
    return ($out -join "`n`n")
}

while ($null -ne ($line = [Console]::In.ReadLine())) {
    $parts = $line.Split("`t")
    try {
        if ($parts[0] -eq 'probe') {
            if ($null -eq $engine) { Fail 'OCR 언어가 설치돼 있지 않습니다'; continue }
            $text = "$($engine.RecognizerLanguage.LanguageTag)`t$([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($ko))`t$maxDim"
        } elseif ($null -eq $engine) {
            Fail 'OCR 언어가 설치돼 있지 않습니다'; continue
        } else {
            $bytes = [Convert]::FromBase64String($parts[2])
            if ($parts[0] -eq 'pdf') { $text = Read-Pdf $bytes ([int]$parts[1]) } else { $text = Read-Image $bytes }
        }
        [Console]::Out.WriteLine("OK`t" + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$text)))
        [Console]::Out.Flush()
    } catch {
        Fail ($_.Exception.Message -replace "[`t`r`n]+", ' ')
    }
}
