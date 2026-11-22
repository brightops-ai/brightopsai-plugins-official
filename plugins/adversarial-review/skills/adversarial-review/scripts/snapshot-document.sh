#!/usr/bin/env bash
#
# snapshot-document.sh — freeze the bytes that are scanned, approved and sent.
#
# The secret scan reads a file, the user approves a file, and the upload reads
# it again later, after questions and browser navigation. By path, those are
# three reads of content that can change in between. A snapshot makes them the
# same bytes: scan the snapshot, approve its sha256, upload the snapshot.
#
# Usage:
#   snapshot-document.sh create <file> [<parent-dir>]
#       Copy <file>, read-only and under its own name, into a new private
#       directory (mode 700) inside <parent-dir> (default: the system
#       temporary directory). Prints:
#         snapshot: <path>
#         sha256: <64 hex digits>
#         bytes: <n>
#   snapshot-document.sh check <snapshot> <sha256> <source>
#       exit 0  UNCHANGED — the snapshot still has that sha256 and <source> is
#               byte-identical to it
#       exit 1  CHANGED — the snapshot was altered, or <source> differs from
#               it or is gone. Send nothing; snapshot, scan and ask again.
#   snapshot-document.sh remove <snapshot>
#       Delete the snapshot and the directory `create` made for it. Refuses
#       any path that is not inside such a directory.
#
#   exit 2  usage error, or a path that is not a regular file / directory

set -euo pipefail

PREFIX=".adversarial-review-snapshot"

usage() {
  cat >&2 <<'EOF'
usage: snapshot-document.sh create <file> [<parent-dir>]
       snapshot-document.sh check <snapshot> <sha256> <source>
       snapshot-document.sh remove <snapshot>
EOF
  exit 2
}

sha256_of() {
  local out
  if command -v sha256sum >/dev/null 2>&1; then
    out=$(sha256sum -- "$1")
  elif command -v shasum >/dev/null 2>&1; then
    out=$(shasum -a 256 -- "$1")
  else
    out=$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1")
  fi
  printf '%s\n' "${out%% *}"
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

cmd_create() {
  [[ $# -ge 1 && $# -le 2 ]] || usage
  local file=$1 parent=${2:-}
  if [[ ! -f "$file" ]]; then
    echo "snapshot-document.sh: not a file: $file" >&2
    exit 2
  fi
  if [[ -z "$parent" ]]; then
    parent=${TMPDIR:-/tmp}
  fi
  parent=${parent%/}
  if [[ ! -d "$parent" ]]; then
    echo "snapshot-document.sh: not a directory: $parent" >&2
    exit 2
  fi

  local dir snap
  dir=$(mktemp -d "$parent/$PREFIX.XXXXXX")
  snap="$dir/$(basename -- "$file")"
  if ! cp -- "$file" "$snap" || ! chmod 400 "$snap"; then
    rm -rf -- "$dir"
    echo "snapshot-document.sh: could not copy $file" >&2
    exit 2
  fi

  printf 'snapshot: %s\n' "$snap"
  printf 'sha256: %s\n' "$(sha256_of "$snap")"
  printf 'bytes: %s\n' "$(wc -c <"$snap" | tr -d '[:space:]')"
}

changed() {
  echo "CHANGED: $1; an upload now SENDS bytes that were not scanned or approved. Send nothing. Make a new snapshot, scan it, and ask the user again."
  exit 1
}

cmd_check() {
  [[ $# -eq 3 ]] || usage
  local snap=$1 want=$2 source=$3 got
  if [[ ! "$want" =~ ^[0-9A-Fa-f]{64}$ ]]; then
    echo "snapshot-document.sh: not a sha256: $want" >&2
    exit 2
  fi
  if [[ ! -f "$snap" ]]; then
    changed "the snapshot $snap is gone"
  fi
  got=$(sha256_of "$snap")
  if [[ "$(lower "$got")" != "$(lower "$want")" ]]; then
    changed "the snapshot $snap no longer has the approved sha256"
  fi
  if [[ ! -f "$source" ]]; then
    changed "the source $source is gone"
  fi
  if ! cmp -s -- "$source" "$snap"; then
    changed "the source $source differs from the approved snapshot"
  fi
  echo "UNCHANGED: $snap sha256 $got"
}

cmd_remove() {
  [[ $# -eq 1 ]] || usage
  local snap=$1 dir
  dir=$(dirname -- "$snap")
  if [[ "${dir##*/}" != "$PREFIX".?* || ! -d "$dir" ]]; then
    echo "snapshot-document.sh: refusing to remove $snap: not inside a directory this script created" >&2
    exit 2
  fi
  rm -rf -- "$dir"
  echo "removed: $dir"
}

[[ $# -ge 1 ]] || usage
action=$1
shift
case "$action" in
  create) cmd_create "$@" ;;
  check) cmd_check "$@" ;;
  remove) cmd_remove "$@" ;;
  *) usage ;;
esac
