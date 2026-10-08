#!/usr/bin/env bash
# Generate docs/html-report.html from a real mock-provider run, then screenshot
# it with headless Chrome into docs/html-report.png.
#
# Usage:
#   ./docs/record-report.sh                  # new failing mock run (new run ID)
#   ./docs/record-report.sh path/to/run.json # render a saved --save-run JSON
#
# After ./docs/record-hero.sh, /tmp/llm-regress-demo/current.json is the failing
# run shown in the GIF. Pass that path (or rely on the auto-detect) so the
# report, screenshot, and GIF share one run ID.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v llm-regress >/dev/null 2>&1; then
  echo "llm-regress is not on PATH. Install with: pip install -e ." >&2
  exit 1
fi

CHROME=""
for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then
    CHROME="$candidate"
    break
  fi
done
if [[ -z "$CHROME" ]]; then
  echo "Chrome/Chromium is required to screenshot the HTML report." >&2
  exit 1
fi

SAVED_RUN="${1:-}"
if [[ -z "$SAVED_RUN" && -f /tmp/llm-regress-demo/current.json ]]; then
  SAVED_RUN=/tmp/llm-regress-demo/current.json
  echo "Using failing run from hero recording: $SAVED_RUN"
fi

WORK=""
USER_DATA=""
cleanup() {
  if [[ -n "$WORK" ]]; then
    rm -rf "$WORK"
  fi
  if [[ -n "$USER_DATA" ]]; then
    rm -rf "$USER_DATA"
  fi
}
trap cleanup EXIT

if [[ -n "$SAVED_RUN" ]]; then
  if [[ ! -f "$SAVED_RUN" ]]; then
    echo "Saved run not found: $SAVED_RUN" >&2
    exit 1
  fi
  python3 - "$SAVED_RUN" "$ROOT/docs/html-report.html" <<'PY'
import sys

from llm_regress.compare import load_run_result
from llm_regress.reporters import HtmlReporter

src, dest = sys.argv[1], sys.argv[2]
result = load_run_result(src)
HtmlReporter(dest).report_run(result)
print(f"Rendered docs/html-report.html from saved run {result.run_id}")
PY
else
  WORK="$(mktemp -d)"
  cp examples/basic.yaml "$WORK/suite.yaml"
  sed -i 's/value: Paris/value: Lyon/' "$WORK/suite.yaml"
  # The suite is expected to fail; keep going to save the report.
  llm-regress run "$WORK/suite.yaml" --output "$ROOT/docs/html-report.html" || true
fi

USER_DATA="$(mktemp -d)"

# --screenshot writes the PNG then Chrome may linger; treat a written file as success.
if ! timeout 25 "$CHROME" \
  --headless=new \
  --user-data-dir="$USER_DATA" \
  --no-first-run \
  --disable-gpu \
  --hide-scrollbars \
  --disable-background-networking \
  --disable-sync \
  --disable-extensions \
  --force-device-scale-factor=2 \
  --window-size=980,740 \
  --screenshot="$ROOT/docs/html-report.png" \
  "file://$ROOT/docs/html-report.html"
then
  if [[ ! -f "$ROOT/docs/html-report.png" ]]; then
    echo "Chrome screenshot failed." >&2
    exit 1
  fi
fi

echo "Wrote docs/html-report.html and docs/html-report.png"
