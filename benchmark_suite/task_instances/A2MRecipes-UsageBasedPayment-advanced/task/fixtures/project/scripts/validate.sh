#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"

cd "${COZE_WORKSPACE_PATH}"
PNPM="pnpm"
if ! command -v pnpm >/dev/null 2>&1; then
  PNPM="corepack pnpm"
fi

echo "🔍 Running validate..."
$PNPM validate
echo "✅ Validate passed!"
