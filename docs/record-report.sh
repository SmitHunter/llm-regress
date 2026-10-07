#!/usr/bin/env bash
# Generate docs/html-report.html from a real mock-provider run of a copy of
# examples/basic.yaml with the Paris assertion changed to Lyon, then screenshot
# it with headless Chrome into docs/html-report.png.
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp examples/basic.yaml "$WORK/suite.yaml"
sed -i 's/value: Paris/value: Lyon/' "$WORK/suite.yaml"

# The suite is expected to fail; keep going to save the report.
llm-regress run "$WORK/suite.yaml" --output "$ROOT/docs/html-report.html" || true

USER_DATA="$(mktemp -d)"
trap 'rm -rf "$WORK" "$USER_DATA"' EXIT

timeout 25 "$CHROME" \
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

echo "Wrote docs/html-report.html and docs/html-report.png"
