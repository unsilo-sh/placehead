#!/usr/bin/env bash
# Refresh the vendored def2graph from terraine's factory repository. For terraine maintainers.
# Usage: scripts/vendor_def2graph.sh /path/to/factory
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
factory="${1:?usage: $0 /path/to/factory}"
src="$factory/adapters/def2graph/def2graph"
dst="$root/skills/placehead-export/vendor/def2graph"
[ -d "$src" ] || { echo "no def2graph at $src" >&2; exit 1; }
rm -rf "$dst"
mkdir -p "$dst"
# viz.py draws pictures for factory's own use. The skill does not need it.
for f in "$src"/*.py; do [ "$(basename "$f")" = viz.py ] || cp "$f" "$dst/"; done
commit="$(git -C "$factory" log -1 --format=%h -- adapters/def2graph)"
sed -i.bak -E "s/at commit [0-9a-f]+\./at commit $commit./" "$root/skills/placehead-export/vendor/README.md"
rm -f "$root/skills/placehead-export/vendor/README.md.bak"
echo "vendored def2graph from factory $commit"
