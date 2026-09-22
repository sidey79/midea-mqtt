#!/usr/bin/env bash
#
# Turn the pending [Unreleased] changelog entries into a dated release
# section and raise VERSION by one patch level.
#
# This is the single place that decides how a release is cut. It is used for
# every merge to main that touches the shipped image and has not already
# chosen its own version bump (see .github/workflows/docker-image.yml). A PR
# that needs a minor or major bump still makes that choice itself by editing
# VERSION directly; this script only ever raises the patch component, because
# that is the one bump that needs no human judgement.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version_file="VERSION"
changelog="CHANGELOG.md"

for required in "$version_file" "$changelog"; do
  if [ ! -f "$required" ]; then
    echo "refusing to act: ${required} not found" >&2
    exit 1
  fi
done

current="$(tr -d '[:space:]' < "$version_file")"

if ! printf '%s' "$current" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "refusing to act: VERSION must be a plain x.y.z release, found '${current}'" >&2
  exit 1
fi

if ! grep -q '^## \[Unreleased\]$' "$changelog"; then
  echo "refusing to act: no [Unreleased] heading found in ${changelog}" >&2
  exit 1
fi

pending="$(awk '
  /^## \[Unreleased\]/ { collecting = 1; next }
  collecting && /^## \[/ { exit }
  collecting && /[^[:space:]]/ { count++ }
  END { print count + 0 }
' "$changelog")"

if [ "$pending" -eq 0 ]; then
  echo "refusing to act: [Unreleased] has no entries to release" >&2
  exit 1
fi

next="${current%.*}.$(( ${current##*.} + 1 ))"
today="$(date -u +%Y-%m-%d)"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
result="${work}/changelog"

awk -v version="$next" -v today="$today" '
  !inserted && /^## \[Unreleased\]$/ {
    print
    print ""
    print "## [" version "] - " today
    inserted = 1
    next
  }
  { print }
' "$changelog" > "$result"

printf '%s\n' "$next" > "$version_file"
cp "$result" "$changelog"

echo "bumped ${current} -> ${next}"
