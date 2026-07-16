#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: $PYTHON not found. Please create the project venv first." >&2
    exit 1
fi

build_onefile() {
    local entry="$1"
    local name="$2"
    shift 2

    if [ ! -f "$ROOT_DIR/$entry" ]; then
        echo "ERROR: $ROOT_DIR/$entry not found." >&2
        exit 1
    fi

    "$PYTHON" -m PyInstaller \
        --clean \
        --noconfirm \
        --onefile \
        --name "$name" \
        --distpath "$DIST_DIR" \
        --workpath "$BUILD_DIR" \
        --specpath "$ROOT_DIR" \
        --paths "$ROOT_DIR" \
        "$@" \
        "$ROOT_DIR/$entry"
}

build_onefile "main.py" "epub2cbz"
build_onefile "pdf_main.py" "pdf2cbz" \
    --collect-data rapidocr \
    --hidden-import rapidocr.inference_engine.onnxruntime \
    --exclude-module torch \
    --exclude-module torchvision \
    --exclude-module openvino \
    --exclude-module paddle \
    --exclude-module tensorrt \
    --exclude-module MNN
build_onefile "probing.py" "probing"

echo ""
echo "Binaries created:"
echo "  $DIST_DIR/epub2cbz"
echo "  $DIST_DIR/pdf2cbz"
echo "  $DIST_DIR/probing"
echo ""
echo "Run examples:"
echo "  cd <epub-series-dir> && $DIST_DIR/epub2cbz"
echo "  cd <pdf-series-dir> && $DIST_DIR/pdf2cbz"
echo "  cd <image-dir> && $DIST_DIR/probing"
