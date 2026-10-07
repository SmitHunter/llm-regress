# Record the README hero GIF from a real mock-provider run.
#
# Re-run from the repo root (requires vhs, ttyd, ffmpeg, and llm-regress on PATH):
#   ./docs/record-hero.sh
#
# Sequence: passing suite → assertion change (Paris → Lyon) → failing suite →
# llm-regress compare reports the regression and exits 1.

Output docs/hero.gif

Set Shell bash
Set FontFamily "JetBrains Mono"
Set FontSize 15
Set Width 920
Set Height 500
Set Padding 16
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set PlaybackSpeed 0.9
Set Framerate 12
Set CursorBlink false

Hide
Type `export PATH="$HOME/.local/bin:$PATH"`
Enter
Type `export PS1='demo $ '`
Enter
Type `mkdir -p /tmp/llm-regress-demo && cp examples/basic.yaml /tmp/llm-regress-demo/suite.yaml && cd /tmp/llm-regress-demo`
Enter
Ctrl+L
Show

Type "llm-regress run suite.yaml --save-run baseline.json"
Enter
Sleep 2.5s
Ctrl+L

Type `sed -i 's/value: Paris/value: Lyon/' suite.yaml`
Enter
Sleep 700ms

Type "llm-regress run suite.yaml --save-run current.json"
Enter
Sleep 2.5s
Ctrl+L

Type `llm-regress compare baseline.json current.json; echo "exit: $?"`
Enter
Sleep 3.5s
