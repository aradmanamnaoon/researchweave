#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../.."
uv sync --locked --extra dev --extra formats --extra release
uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
test -x dist/ResearchWeave/ResearchWeave
tar -C dist -czf dist/ResearchWeave-linux-x86_64.tar.gz ResearchWeave
sha256sum dist/ResearchWeave-linux-x86_64.tar.gz
