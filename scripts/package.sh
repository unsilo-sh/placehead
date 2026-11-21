#!/usr/bin/env bash
# Zip the export skill for a partner who does not clone this repository.
# Usage: scripts/package.sh       Writes dist/placehead-export.zip.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
skill="$root/skills/placehead-export"
if grep -rqE 'https?://' "$skill/viewer.html"; then echo "viewer.html names a URL" >&2; exit 1; fi

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -R "$skill" "$stage/placehead-export"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +
{
  echo "placehead $(git -C "$root" rev-parse --short HEAD)$(git -C "$root" diff --quiet || echo ' (uncommitted changes)')"
  echo "built $(date -u +%Y-%m-%dT%H:%MZ)"
} > "$stage/placehead-export/VERSION"
mkdir -p "$root/dist"
rm -f "$root/dist/placehead-export.zip"
(cd "$stage" && zip -qr "$root/dist/placehead-export.zip" placehead-export)
echo "wrote $root/dist/placehead-export.zip"
