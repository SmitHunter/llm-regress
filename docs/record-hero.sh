#!/usr/bin/env bash
# Record docs/hero.gif from a real mock-provider run via VHS (docs/hero.tape).
# After recording, render the matching HTML report from the failing --save-run
# JSON so the GIF, HTML, and screenshot share one run ID.
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

if [[ -f /tmp/llm-regress-demo/current.json ]]; then
  echo "Failing run saved at /tmp/llm-regress-demo/current.json"
  "$ROOT/docs/record-report.sh" /tmp/llm-regress-demo/current.json
else
  echo "Warning: /tmp/llm-regress-demo/current.json missing; HTML report not updated." >&2
fi
