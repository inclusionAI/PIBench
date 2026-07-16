#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"

cd "${COZE_WORKSPACE_PATH}"
PNPM="pnpm"
if ! command -v pnpm >/dev/null 2>&1; then
  PNPM="corepack pnpm"
fi

echo "Installing dependencies..."
$PNPM install --prefer-frozen-lockfile --prefer-offline --loglevel debug --reporter=append-only

echo "Building the Next.js project..."
$PNPM next build

echo "Bundling server with tsup..."
$PNPM tsup src/server.ts --format cjs --platform node --target node20 --outDir dist --no-splitting --no-minify

echo "Build completed successfully!"
