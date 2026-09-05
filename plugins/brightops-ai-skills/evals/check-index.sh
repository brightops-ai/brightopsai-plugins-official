#!/usr/bin/env bash
# Compare cases/* directories against the "What the cases cover" table in
# README.md. Exit 1 naming each missing or extra case.
#
#   check-index.sh           # this script's directory (the real evals tree)
#   check-index.sh <dir>     # a substitute tree (used by tests)
set -euo pipefail

usage() {
  echo "usage: check-index.sh [evals-dir]" >&2
  exit 2
}

if [[ $# -gt 1 ]]; then
  usage
fi

if [[ $# -eq 1 ]]; then
  EVALS_DIR="$(cd "$1" && pwd)"
else
  EVALS_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
fi

README="$EVALS_DIR/README.md"
CASES_DIR="$EVALS_DIR/cases"

if [[ ! -f "$README" ]]; then
  echo "check-index.sh: no README.md in $EVALS_DIR" >&2
  exit 1
fi
if [[ ! -d "$CASES_DIR" ]]; then
  echo "check-index.sh: no cases/ in $EVALS_DIR" >&2
  exit 1
fi

table_cases() {
  awk -v q='`' '
    /^## What the cases cover$/ { in_section = 1; next }
    in_section && /^## / { exit }
    in_section {
      prefix = "| " q
      if (index($0, prefix) != 1) next
      rest = substr($0, length(prefix) + 1)
      end = index(rest, q)
      if (end < 2) next
      print substr(rest, 1, end - 1)
    }
  ' "$README"
}

disk_cases() {
  local d
  for d in "$CASES_DIR"/*; do
    [[ -d "$d" ]] || continue
    basename "$d"
  done
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

disk_cases | sort -u >"$tmp/disk"
table_cases | sort -u >"$tmp/table"

missing=$(comm -23 "$tmp/disk" "$tmp/table")
extra=$(comm -13 "$tmp/disk" "$tmp/table")

status=0
if [[ -n "$missing" ]]; then
  status=1
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    echo "missing from table: $name"
  done <<<"$missing"
fi
if [[ -n "$extra" ]]; then
  status=1
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    echo "extra in table: $name"
  done <<<"$extra"
fi

exit "$status"
