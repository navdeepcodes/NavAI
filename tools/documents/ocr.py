"""Reading text out of pictures: scanned pages, photos of notes, screenshots.

Windows ships an OCR engine of its own (Windows.Media.Ocr, the one Snipping
Tool uses): offline, fast (measured: three printed lines, exactly right, in
0.8s including starting PowerShell), and nothing to download or bundle. Mike
asks it through PowerShell, in batches -- starting it is most of the cost --
and rasterises PDF pages for it with Qt's own PDF renderer.

Only printed text is read well; handwriting mostly isn't. Where the engine is
missing (an old Windows, no language installed) `available()` says so and
everything that would have used it says why it couldn't.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from hostplatform.processes import NO_WINDOW
from logs.logger import logger

#: A batch gets this long, plus a share per image.
OCR_BASE_TIMEOUT = 25.0
OCR_PER_IMAGE = 6.0
#: The engine won't take an image larger than this on a side.
MAX_SIDE = 4000
#: Resolution PDF pages are drawn at for reading.
PDF_DPI = 200

_SCRIPT = r'''
param([string]$ListFile, [string]$ResultFile, [switch]$Probe)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
}
if (-not $engine) { Set-Content -LiteralPath $ResultFile -Value '{"error":"no OCR language installed"}' -Encoding UTF8; exit 2 }
if ($Probe) { Set-Content -LiteralPath $ResultFile -Value '{"ok":true}' -Encoding UTF8; exit 0 }
$paths = Get-Content -LiteralPath $ListFile -Encoding UTF8
$out = New-Object System.Collections.ArrayList
foreach ($p in $paths) {
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
        [void]$out.Add((($res.Lines | ForEach-Object { $_.Text }) -join "`n"))
    } catch { [void]$out.Add('') }
}
$json = ConvertTo-Json -InputObject @{ texts = @($out) } -Compress
Set-Content -LiteralPath $ResultFile -Value $json -Encoding UTF8
'''

_lock = threading.Lock()
_state: dict = {"checked": False, "ok": False, "why": ""}


def _run(args_extra: list[str], timeout: float, images: list[str] | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="mike-ocr-") as tmp:
        tmp_path = Path(tmp)
        script, result, listing = tmp_path / "ocr.ps1", tmp_path / "result.json", tmp_path / "list.txt"
        script.write_text(_SCRIPT, encoding="utf-8-sig")       # PowerShell 5.1 wants the BOM
        listing.write_text("\n".join(images or []), encoding="utf-8")
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), "-ListFile", str(listing), "-ResultFile", str(result), *args_extra],
                capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"error": "reading the pictures took too long"}
        except OSError as exc:
            return {"error": f"couldn't start Windows' text reader ({exc})"}
        try:
            return json.loads(result.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {"error": (proc.stderr or "Windows' text reader gave no answer").strip()[:200]}


def available() -> bool:
    """Is Windows' OCR usable here? Asked once, then remembered."""
    if sys.platform != "win32":
        return False
    with _lock:
        if not _state["checked"]:
            answer = _run(["-Probe"], timeout=30.0)
            _state.update(checked=True, ok=bool(answer.get("ok")),
                          why=str(answer.get("error") or ""))
            if not _state["ok"]:
                logger.info("OCR isn't available: %s", _state["why"])
        return bool(_state["ok"])


def unavailable_reason() -> str:
    if sys.platform != "win32":
        return "reading text from pictures is only built for Windows"
    return _state["why"] or "Windows' text reader isn't available"


def read_images(paths: list[str]) -> list[str]:
    """The text in each image, in order ("" for one that couldn't be read).
    One PowerShell start for the whole batch."""
    if not paths or not available():
        return [""] * len(paths)
    answer = _run([], OCR_BASE_TIMEOUT + OCR_PER_IMAGE * len(paths), images=[str(p) for p in paths])
    texts = answer.get("texts")
    if not isinstance(texts, list):
        logger.info("OCR failed: %s", answer.get("error"))
        return [""] * len(paths)
    texts = [str(t or "") for t in texts]
    return (texts + [""] * len(paths))[:len(paths)]


def tidy(text: str) -> str:
    """OCR's lines as a reader would want them: trailing spaces gone, a word
    broken across a line end by a hyphen joined back."""
    import re
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    joined = re.sub(r"(\w)-\n(\w)", r"\1\2", "\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def rasterize_pdf(path: str, page_numbers: list[int], out_dir: Path, dpi: int = PDF_DPI) -> dict[int, Path]:
    """Draw PDF pages (1-based) as PNG files, white-backed, sized for reading.
    {page: file} for those that could be drawn."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(str(path))
    if doc.status() != QPdfDocument.Status.Ready:
        return {}
    made: dict[int, Path] = {}
    for number in page_numbers:
        index = number - 1
        if not 0 <= index < doc.pageCount():
            continue
        size = doc.pagePointSize(index)
        scale = dpi / 72.0
        width, height = max(1, int(size.width() * scale)), max(1, int(size.height() * scale))
        biggest = max(width, height)
        if biggest > MAX_SIDE:
            width, height = int(width * MAX_SIDE / biggest), int(height * MAX_SIDE / biggest)
        image = doc.render(index, QSize(width, height))
        if image.isNull():
            continue
        page = QImage(image.size(), QImage.Format.Format_RGB32)
        page.fill(QColor("white"))
        painter = QPainter(page)
        painter.drawImage(0, 0, image)
        painter.end()
        target = out_dir / f"page-{number}.png"
        if page.save(str(target), "PNG"):
            made[number] = target
    return made


def read_pdf_pages(path: str, page_numbers: list[int]) -> dict[int, str]:
    """OCR the given pages (1-based) of a PDF: {page: text}."""
    if not page_numbers or not available():
        return {}
    with tempfile.TemporaryDirectory(prefix="mike-pages-") as tmp:
        drawn = rasterize_pdf(path, page_numbers, Path(tmp))
        order = [n for n in page_numbers if n in drawn]
        texts = read_images([str(drawn[n]) for n in order])
        return {n: tidy(t) for n, t in zip(order, texts)}
