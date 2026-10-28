#!/usr/bin/env bash
# Build docs/*.html from tools/docs/*.archify.md with Archify (Vietnamese chrome).
#   tools/docs/build.sh            # every page
#   tools/docs/build.sh 03-du-lieu # one page
# ARCHIFY=<clone> reuses an existing clone; otherwise one is cached in ~/.cache/archify.
set -euo pipefail
cd "$(dirname "$0")/../.."
ARCHIFY="${ARCHIFY:-$HOME/.cache/archify}"
if [ ! -d "$ARCHIFY/archify" ]; then
  git clone --depth 1 https://github.com/tt-a1i/archify "$ARCHIFY"
  (cd "$ARCHIFY" && npm install --silent)
fi
node tools/docs/archify/install-vi.mjs "$ARCHIFY"

pages=("$@")
[ ${#pages[@]} -eq 0 ] && pages=($(cd tools/docs && ls *.archify.md | sed 's/\.archify\.md$//'))
for p in "${pages[@]}"; do
  node "$ARCHIFY/archify/bin/archify.mjs" finalize explainer "tools/docs/$p.archify.md" "docs/$p.html" \
    --writing off --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);
      console.log(r.status.padEnd(5), process.argv[1]); if(r.status!=="pass"){console.log(JSON.stringify(r.diagnostics,null,1));process.exit(1)}})' "$p"
done
rm -f docs/*.delivery.json docs/*.finalize.json docs/*.finalize-summary.json docs/*.browser-check.json
