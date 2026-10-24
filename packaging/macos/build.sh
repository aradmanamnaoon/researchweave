#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../.."
uv sync --locked --extra dev --extra formats --extra release
uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
test -x dist/ResearchWeave/ResearchWeave
tar -C dist -czf dist/ResearchWeave-macos.tar.gz ResearchWeave
shasum -a 256 dist/ResearchWeave-macos.tar.gz
