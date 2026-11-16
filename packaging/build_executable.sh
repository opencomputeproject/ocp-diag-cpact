#!/usr/bin/env bash
# Build a standalone single-file CPACT executable with PyInstaller.
#
# Usage:
#   ./packaging/build_executable.sh            # full build (includes GUI)
#   CPACT_NO_GUI=1 ./packaging/build_executable.sh   # smaller CLI-only build
#
# Output: dist/cpact
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_VENV="${REPO_ROOT}/build/pyinstaller-venv"
PYTHON="${PYTHON:-python3}"

cd "${REPO_ROOT}"

echo "==> Creating build virtualenv at ${BUILD_VENV}"
"${PYTHON}" -m venv "${BUILD_VENV}"
# shellcheck disable=SC1091
source "${BUILD_VENV}/bin/activate"

echo "==> Installing dependencies"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller

echo "==> Building executable"
pyinstaller --clean --noconfirm \
    --distpath "${REPO_ROOT}/dist" \
    --workpath "${REPO_ROOT}/build/pyinstaller" \
    packaging/cpact.spec

echo "==> Smoke-testing executable"
"${REPO_ROOT}/dist/cpact" --help >/dev/null

echo
echo "Build complete: ${REPO_ROOT}/dist/cpact"
echo "Deploy by copying this single file to the target system."
