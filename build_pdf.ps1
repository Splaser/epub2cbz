param(
    [string]$Python = "python",
    [string]$PopplerBin = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $PopplerBin) {
    $bundledRuntime = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin"
    if (Test-Path (Join-Path $bundledRuntime "pdftoppm.exe")) {
        $PopplerBin = $bundledRuntime
    }
    else {
        $pdftoppm = Get-Command pdftoppm.exe -ErrorAction SilentlyContinue
        if ($pdftoppm) {
            $PopplerBin = Split-Path -Parent $pdftoppm.Source
        }
    }
}

if (-not $PopplerBin -or -not (Test-Path (Join-Path $PopplerBin "pdftoppm.exe"))) {
    throw "Poppler pdftoppm.exe not found. Pass -PopplerBin <directory>."
}

Push-Location $root
try {
    & $Python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name pdf_main `
        --collect-data rapidocr `
        --collect-all pypdfium2 `
        --add-binary "$PopplerBin\*;poppler" `
        --hidden-import rapidocr.inference_engine.onnxruntime `
        --exclude-module torch `
        --exclude-module torchvision `
        --exclude-module openvino `
        --exclude-module paddle `
        --exclude-module tensorrt `
        --exclude-module MNN `
        --paths $root `
        pdf_main.py

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    Write-Host "Built: $root\dist\pdf_main.exe"
}
finally {
    Pop-Location
}
