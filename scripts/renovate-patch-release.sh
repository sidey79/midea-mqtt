#!/usr/bin/env bash
#
# Turn a dependency update into a regular patch release.
#
# Renovate runs this from postUpgradeTasks after it has updated something that
# ships inside the image, so that the update takes the normal release path: the
# patch version is raised and the changelog gains a section for it. Merging the
# pull request then publishes the image the same way any other release does.
#
# Without this, a dependency update would never reach a user: published images
# come only from releases, and a merge without a version bump publishes nothing.
#
# The script refuses to act when the changelog already lists pending entries.
# Choosing the version for a release that contains real changes is a human
# decision, not something a dependency bot should make.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version_file="VERSION"
changelog="CHANGELOG.md"

for required in "$version_file" "$changelog"; do
  if [ ! -f "$required" ]; then
    echo "refusing to bump: ${required} not found" >&2
    exit 1
  fi
done

current="$(tr -d '[:space:]' < "$version_file")"

if ! printf '%s' "$current" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "refusing to bump: VERSION must be a plain x.y.z release, found '${current}'" >&2
  exit 1
fi

pending="$(awk '
  /^## \[Unreleased\]/ { collecting = 1; next }
  collecting && /^## \[/ { exit }
  collecting && /[^[:space:]]/ { count++ }
  END { print count + 0 }
' "$changelog")"

if [ "$pending" -ne 0 ]; then
  {
    echo "refusing to bump: CHANGELOG.md already has entries under [Unreleased]."
    echo "Cut that release deliberately; picking its version is a human decision."
  } >&2
  exit 1
fi

next="${current%.*}.$(( ${current##*.} + 1 ))"
today="$(date -u +%Y-%m-%d)"

# Benennen, was aktualisiert wurde, damit der Changelog-Eintrag etwas aussagt.
changed="$(git diff --name-only HEAD 2>/dev/null || true)"
dockerfile_touched=false
requirements_touched=false

case "$changed" in
  *Dockerfile*) dockerfile_touched=true ;;
esac
case "$changed" in
  *requirements.txt*) requirements_touched=true ;;
esac

if [ "$dockerfile_touched" = true ] && [ "$requirements_touched" = true ]; then
  subject="the container base image and the Python dependencies"
elif [ "$dockerfile_touched" = true ]; then
  subject="the container base image"
elif [ "$requirements_touched" = true ]; then
  subject="the Python dependencies"
else
  subject="the dependencies that ship inside the image"
fi

printf '%s\n' "$next" > "$version_file"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

awk -v version="$next" -v today="$today" -v subject="$subject" '
  !inserted && /^## \[Unreleased\]$/ {
    print
    print ""
    print "## [" version "] - " today
    print ""
    print "### Changed"
    print ""
    print "- Update " subject ", picking up the latest upstream changes."
    inserted = 1
    next
  }
  { print }
  END {
    if (!inserted) {
      print "no [Unreleased] heading found in the changelog" > "/dev/stderr"
      exit 1
    }
  }
' "$changelog" > "$tmp"

mv "$tmp" "$changelog"
trap - EXIT

echo "bumped ${current} -> ${next} and added its changelog section"
