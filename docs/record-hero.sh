#!/usr/bin/env bash
# Record docs/hero.gif from a real mock-provider run via VHS (docs/hero.tape).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v llm-regress >/dev/null 2>&1; then
  echo "llm-regress is not on PATH. Install with: pip install -e ." >&2
  exit 1
fi

if ! command -v vhs >/dev/null 2>&1; then
  echo "vhs is not on PATH. See https://github.com/charmbracelet/vhs" >&2
  exit 1
fi

rm -rf /tmp/llm-regress-demo
vhs docs/hero.tape
