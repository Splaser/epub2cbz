param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $root
try {
    & $Python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name pdf_main `
        --collect-all rapidocr `
        --collect-all onnxruntime `
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
