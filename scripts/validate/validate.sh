#!/usr/bin/env bash
# validate.sh <invaders.html> <screenshot.png> [virtual_ms]
html=$(readlink -f "$1"); shot=$2; budget=${3:-2600}
echo "== $html"
[[ -f "$html" ]] || { echo "MISSING"; exit 1; }
# 1. syntax-check inline scripts
python3 - "$html" <<'PY' > /tmp/validate/script.js
import re,sys
s=open(sys.argv[1],errors='ignore').read()
print("\n".join(re.findall(r'<script[^>]*>(.*?)</script>', s, re.S|re.I)))
PY
if node --check /tmp/validate/script.js 2>/tmp/validate/syntax.err; then echo "syntax: OK ($(wc -l < /tmp/validate/script.js) js lines)"; else echo "syntax: FAIL"; head -5 /tmp/validate/syntax.err; fi
# 2. structural features
for f in '<canvas' requestAnimationFrame keydown fillRect imageSmoothingEnabled; do grep -qi -- "$f" "$html" && printf '  has %s\n' "$f" || printf '  MISSING %s\n' "$f"; done
# 3. real-time headless chrome via CDP with simulated keys
(cd /tmp/validate && timeout 90 node cdp-run.mjs "$html" "$shot" --keys) | sed "s/^/  /"
echo "  screenshot: $shot ($(stat -c %s "$shot" 2>/dev/null) bytes)"
