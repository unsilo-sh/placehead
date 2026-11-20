#!/usr/bin/env bash
# Assemble the export kit for a partner: dist/placehead-export/ and dist/placehead-export.zip.
# Usage: kit/build_kit.sh /path/to/factory
# It copies the kit's own files, placehead's make_graph_json.py, and def2graph from factory.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
factory="${1:?usage: $0 /path/to/factory}"
d2g="$factory/adapters/def2graph/def2graph"
[ -d "$d2g" ] || { echo "no def2graph at $d2g" >&2; exit 1; }

out="$root/dist/placehead-export"
rm -rf "$out" "$root/dist/placehead-export.zip"
mkdir -p "$out/tools" "$out/vendor/def2graph"
cp "$here/SKILL.md" "$here/DATA.md" "$here/README.md" "$out/"
cp "$here"/tools/*.py "$out/tools/"
cp "$root/make_graph_json.py" "$out/vendor/"
# The kit's viewer must make no network request: drop the web-font links, keep the fallback fonts.
grep -v 'fonts.googleapis.com\|fonts.gstatic.com' "$root/viewer.html" > "$out/viewer.html"
if grep -qE 'https?://' "$out/viewer.html"; then echo "viewer.html still names a URL" >&2; exit 1; fi
# viz.py draws pictures for factory's own use. The kit does not need it.
for f in "$d2g"/*.py; do [ "$(basename "$f")" = viz.py ] || cp "$f" "$out/vendor/def2graph/"; done
{
  echo "placehead $(git -C "$root" rev-parse --short HEAD)"
  echo "def2graph from factory $(git -C "$factory" log -1 --format=%h -- adapters/def2graph)"
  echo "built $(date -u +%Y-%m-%dT%H:%MZ)"
} > "$out/VERSION"
(cd "$root/dist" && zip -qr placehead-export.zip placehead-export -x '*/__pycache__/*')
echo "wrote $out and $root/dist/placehead-export.zip"
