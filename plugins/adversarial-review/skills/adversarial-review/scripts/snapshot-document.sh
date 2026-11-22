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
#       Delete that one snapshot file, then remove its directory if it is now
#       empty. Nothing else is deleted: the path must be an existing regular
#       file directly inside a directory `create` made.
#       exit 0  removed
#       exit 1  KEPT — the file is gone but its directory holds other
#               entries, which are left alone and listed
#
#   exit 2  usage error, a path that is not what the action needs, or a
#           digest that could not be computed

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

# Prints the lowercase sha256 of a file. Returns 1, printing nothing, unless
# the tool succeeded and produced 64 hex digits: a blank or partial digest
# must never be reported as one.
sha256_of() {
  local out=""
  if command -v sha256sum >/dev/null 2>&1; then
    out=$(sha256sum -- "$1") || return 1
  elif command -v shasum >/dev/null 2>&1; then
    out=$(shasum -a 256 -- "$1") || return 1
  else
    out=$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1") || return 1
  fi
  out=$(lower "${out%% *}")
  if [[ ! "$out" =~ ^[0-9a-f]{64}$ ]]; then
    return 1
  fi
  printf '%s\n' "$out"
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

# Undo a half-made snapshot: the one file this run copied, then its directory.
discard() {
  rm -f -- "$2"
  rmdir -- "$1" 2>/dev/null || true
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

  local dir snap sha bytes
  dir=$(mktemp -d "$parent/$PREFIX.XXXXXX")
  snap="$dir/$(basename -- "$file")"
  if ! cp -- "$file" "$snap" || ! chmod 400 "$snap"; then
    discard "$dir" "$snap"
    echo "snapshot-document.sh: could not copy $file" >&2
    exit 2
  fi
  # Nothing is reported until the digest and the size are known to be good.
  if ! sha=$(sha256_of "$snap") || ! bytes=$(wc -c <"$snap") || [[ -z "${bytes//[[:space:]]/}" ]]; then
    discard "$dir" "$snap"
    echo "snapshot-document.sh: could not compute the sha256 of $snap; no snapshot was made" >&2
    exit 2
  fi

  printf 'snapshot: %s\n' "$snap"
  printf 'sha256: %s\n' "$sha"
  printf 'bytes: %s\n' "${bytes//[[:space:]]/}"
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
  if ! got=$(sha256_of "$snap"); then
    echo "snapshot-document.sh: could not compute the sha256 of $snap" >&2
    exit 2
  fi
  if [[ "$got" != "$(lower "$want")" ]]; then
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
  # Only an existing regular file, directly inside a real directory that
  # `create` named. The directory name alone proves nothing about what else
  # is in it, so nothing but this one file is ever deleted.
  if [[ "${dir##*/}" != "$PREFIX".?* || -L "$dir" || ! -d "$dir" ]]; then
    echo "snapshot-document.sh: refusing to remove $snap: not inside a directory this script created" >&2
    exit 2
  fi
  if [[ -L "$snap" || ! -f "$snap" ]]; then
    echo "snapshot-document.sh: refusing to remove $snap: not an existing snapshot file; nothing was deleted" >&2
    exit 2
  fi
  rm -f -- "$snap"
  if rmdir -- "$dir" 2>/dev/null; then
    echo "removed: $snap"
    return 0
  fi
  echo "KEPT: $snap was removed, but $dir holds other entries, which were left alone:"
  ls -A -- "$dir"
  exit 1
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
