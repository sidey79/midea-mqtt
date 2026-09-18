#!/usr/bin/env bash
#
# Turn a dependency update into a changelog entry, and into a patch release
# where picking the version needs no human judgement.
#
# Renovate runs this from postUpgradeTasks after it has updated something that
# ships inside the image. Published images come only from releases, so an update
# that never reaches a release never reaches a user.
#
# When the changelog has no pending entries, the update becomes a release of its
# own: the patch version is raised and the changelog gains a section for it.
# Merging the pull request then publishes the image the same way any other
# release does.
#
# When entries are already pending, the update is recorded under [Unreleased]
# and VERSION is left alone. Choosing the version for a release that contains
# real changes is a human decision — but the update must not merge silently
# either, so it is written down and travels with the next release that is cut
# deliberately.

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

entry="- Update ${subject}, picking up the latest upstream changes."

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

if [ "$pending" -ne 0 ]; then
  # A release is already taking shape. Record the update under [Unreleased] so it
  # ships with that release, and leave the version for whoever cuts it.
  recorded="$(awk -v entry="$entry" '
    /^## \[Unreleased\]/ { collecting = 1; next }
    collecting && /^## \[/ { exit }
    collecting && $0 == entry { found = 1 }
    END { print found + 0 }
  ' "$changelog")"

  if [ "$recorded" -ne 0 ]; then
    echo "left VERSION at ${current}; [Unreleased] already mentions this update"
    exit 0
  fi

  awk -v entry="$entry" '
    { line[NR] = $0 }
    END {
      for (i = 1; i <= NR; i++)
        if (line[i] ~ /^## \[Unreleased\]$/) { start = i; break }

      # The [Unreleased] section runs up to the next release heading.
      stop = NR + 1
      for (i = start + 1; i <= NR; i++)
        if (line[i] ~ /^## \[/) { stop = i; break }

      for (i = start + 1; i < stop; i++)
        if (line[i] ~ /^### Changed[ \t]*$/) { changed = i; break }

      if (changed) {
        # Append to the existing list, after its last item.
        at = stop
        for (i = changed + 1; i < stop; i++)
          if (line[i] ~ /^### /) { at = i; break }
        while (at > changed + 1 && line[at - 1] ~ /^[ \t]*$/) at--
        insert[at] = entry
      } else {
        # No Changed list yet; start one at the end of the section.
        insert[stop] = "### Changed\n\n" entry "\n"
      }

      for (i = 1; i <= NR; i++) {
        if (i in insert) print insert[i]
        print line[i]
      }
      if ((NR + 1) in insert) print insert[NR + 1]
    }
  ' "$changelog" > "$tmp"

  mv "$tmp" "$changelog"
  trap - EXIT

  echo "left VERSION at ${current}; recorded the update under [Unreleased]"
  exit 0
fi

next="${current%.*}.$(( ${current##*.} + 1 ))"
today="$(date -u +%Y-%m-%d)"

printf '%s\n' "$next" > "$version_file"

awk -v version="$next" -v today="$today" -v entry="$entry" '
  !inserted && /^## \[Unreleased\]$/ {
    print
    print ""
    print "## [" version "] - " today
    print ""
    print "### Changed"
    print ""
    print entry
    inserted = 1
    next
  }
  { print }
' "$changelog" > "$tmp"

mv "$tmp" "$changelog"
trap - EXIT

echo "bumped ${current} -> ${next} and added its changelog section"
