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
# When entries are already pending, the update is recorded at the top of
# [Unreleased] and VERSION is left alone. Choosing the version for a release
# that contains real changes is a human decision — but the update must not merge
# silently either, so it is written down and travels with the next release that
# is cut deliberately.
#
# Either way the entries live under their own "### Dependencies" heading, so a
# bot entry never mixes into the hand-written notes of a pending release.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version_file="VERSION"
changelog="CHANGELOG.md"
heading="### Dependencies"

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

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
entries="${work}/entries"

# Name what was updated. Renovate passes the upgrades of this branch through the
# file named by RENOVATE_POST_UPGRADE_COMMAND_DATA_FILE; renovate.json fills it
# with one tab-separated record per upgrade. Wording it here rather than in the
# Handlebars template keeps the phrasing testable outside of Renovate.
data_file="${RENOVATE_POST_UPGRADE_COMMAND_DATA_FILE:-}"

if [ -n "$data_file" ] && [ -s "$data_file" ]; then
  awk -F'\t' '
    /^[[:space:]]*$/ { next }
    {
      name = $1; from = $2; to = $3; digest = $5
      if (name == "") next
      if (from != "" && to != "" && from != to)
        printf "- Update %s from %s to %s.\n", name, from, to
      else if (digest != "")
        printf "- Update the %s image to digest %s.\n", name, digest
      else if (to != "")
        printf "- Update %s to %s.\n", name, to
      else
        printf "- Update %s.\n", name
    }
  ' "$data_file" | sort -u > "$entries"
fi

if [ ! -s "$entries" ]; then
  # No usable upgrade data — a manual run, or a Renovate version that does not
  # provide it. Fall back to naming the files that changed.
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

  printf -- '- Update %s, picking up the latest upstream changes.\n' "$subject" > "$entries"
fi

pending="$(awk '
  /^## \[Unreleased\]/ { collecting = 1; next }
  collecting && /^## \[/ { exit }
  collecting && /[^[:space:]]/ { count++ }
  END { print count + 0 }
' "$changelog")"

result="${work}/changelog"

if [ "$pending" -ne 0 ]; then
  # A release is already taking shape. Record the updates at the top of
  # [Unreleased] and leave the version to whoever cuts that release.
  awk -v heading="$heading" '
    NR == FNR { entry[++entries] = $0; next }
    { line[++lines] = $0 }
    END {
      for (i = 1; i <= lines; i++)
        if (line[i] ~ /^## \[Unreleased\]$/) { start = i; break }

      # The [Unreleased] section runs up to the next release heading.
      stop = lines + 1
      for (i = start + 1; i <= lines; i++)
        if (line[i] ~ /^## \[/) { stop = i; break }

      # Drop entries this section already carries, so a rerun on the same branch
      # does not repeat itself.
      for (i = start + 1; i < stop; i++)
        seen[line[i]] = 1
      for (i = 1; i <= entries; i++)
        if (!(entry[i] in seen)) fresh[++n] = entry[i]
      if (n == 0) { for (i = 1; i <= lines; i++) print line[i]; exit }

      # Reuse our own heading when it already opens the section.
      for (i = start + 1; i < stop; i++) {
        if (line[i] ~ /^[ \t]*$/) continue
        if (line[i] == heading) head = i
        break
      }

      if (head) {
        at = stop
        for (i = head + 1; i < stop; i++)
          if (line[i] ~ /^### /) { at = i; break }
        while (at > head + 1 && line[at - 1] ~ /^[ \t]*$/) at--
      } else {
        at = start + 1
      }

      for (i = 1; i <= lines; i++) {
        if (i == at) {
          if (!head) { print ""; print heading; print "" }
          for (j = 1; j <= n; j++) print fresh[j]
        }
        print line[i]
      }
      if (at == lines + 1) {
        if (!head) { print ""; print heading; print "" }
        for (j = 1; j <= n; j++) print fresh[j]
      }
    }
  ' "$entries" "$changelog" > "$result"

  if cmp -s "$result" "$changelog"; then
    echo "left VERSION at ${current}; [Unreleased] already lists these updates"
    exit 0
  fi

  cp "$result" "$changelog"
  echo "left VERSION at ${current}; recorded the updates at the top of [Unreleased]"
  exit 0
fi

next="${current%.*}.$(( ${current##*.} + 1 ))"
today="$(date -u +%Y-%m-%d)"

printf '%s\n' "$next" > "$version_file"

awk -v version="$next" -v today="$today" -v heading="$heading" '
  NR == FNR { entry[++entries] = $0; next }
  !inserted && /^## \[Unreleased\]$/ {
    print
    print ""
    print "## [" version "] - " today
    print ""
    print heading
    print ""
    for (i = 1; i <= entries; i++) print entry[i]
    inserted = 1
    next
  }
  { print }
' "$entries" "$changelog" > "$result"

cp "$result" "$changelog"

echo "bumped ${current} -> ${next} and added its changelog section"
