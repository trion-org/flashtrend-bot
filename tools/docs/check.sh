#!/usr/bin/env bash
# Browser-check docs/*.html (Archify readability/layout gate). ARCHIFY_CHROME picks the browser.
set -uo pipefail
cd "$(dirname "$0")/../.."
ARCHIFY="${ARCHIFY:-$HOME/.cache/archify}"
pages=("$@"); [ ${#pages[@]} -eq 0 ] && pages=($(cd tools/docs && ls *.archify.md | sed 's/\.archify\.md$//'))
rc=0
for p in "${pages[@]}"; do
  node "$ARCHIFY/archify/bin/archify.mjs" browser-check "docs/$p.html" --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);const m={};
    for(const d of r.diagnostics||[]){const k=(d.subject?.component||"-")+": "+d.message.slice(0,70);m[k]=(m[k]||0)+1}
    console.log(r.status.padEnd(5),process.argv[1],Object.keys(m).length?JSON.stringify(m):""); process.exit(r.status==="pass"?0:1)})' "$p" || rc=1
done
rm -f docs/*.browser-check.json
exit $rc
