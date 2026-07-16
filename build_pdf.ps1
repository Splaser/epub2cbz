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
        --collect-data rapidocr `
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
