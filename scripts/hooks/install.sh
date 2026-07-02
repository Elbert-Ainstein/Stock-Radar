#!/usr/bin/env bash
# Install the tracked pre-commit hook into this clone (consolidation sprint 3.4).
# Usage: bash scripts/hooks/install.sh
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
chmod +x "$ROOT/scripts/hooks/pre-commit"
ln -sf ../../scripts/hooks/pre-commit "$ROOT/.git/hooks/pre-commit"
echo "[install] pre-commit hook linked -> scripts/hooks/pre-commit"
