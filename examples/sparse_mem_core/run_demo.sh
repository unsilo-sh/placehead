#!/usr/bin/env bash
# Run the export workflow on the synthetic design, as a partner would on theirs.
# Usage: examples/sparse_mem_core/run_demo.sh
# Writes demo/work/ (real names: stays here) and demo/export/ (the file a partner would send).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
kit="$(cd "$here/../../skills/placehead-export" && pwd)"
cd "$here"
[ -f pdk/fakeram45_1024x32.lef ] || ./fetch_pdk.sh
rm -rf demo
mkdir demo
cd demo
lefs=(../pdk/*.lef)
libs=(../pdk/*.lib)
def=../sparse_mem_core_placed.def

python3 "$kit/tools/extract.py" --def "$def" --lef "${lefs[@]}" --lib "${libs[@]}" --work work
python3 "$kit/tools/obfuscate.py" work/graph.json --key work/key.json -o export/design.export.json
python3 "$kit/tools/verify.py" work/graph.json export/design.export.json --key work/key.json
python3 "$kit/tools/audit.py" export/design.export.json --key work/key.json \
    --def "$def" --lef "${lefs[@]}" --lib "${libs[@]}"
