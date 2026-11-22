#!/usr/bin/env bats
#
# snapshot-document.sh: the scanned, approved and uploaded bytes are one copy.
#   create  private read-only copy, prints snapshot / sha256 / bytes
#   check   exit 0 UNCHANGED, exit 1 CHANGED (snapshot altered or source moved on)
#   remove  deletes one snapshot file, then its directory only if empty

setup() {
  load '../../../scripts/test-support/sandbox-guard'
  PLUGIN_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SNAP="$PLUGIN_ROOT/skills/adversarial-review/scripts/snapshot-document.sh"
  export TMPDIR="$BATS_TEST_TMPDIR/tmp"
  mkdir -p "$TMPDIR" "$BATS_TEST_TMPDIR/work"
  DOC="$BATS_TEST_TMPDIR/work/plan.md"
  printf '%s\n' '# Plan' 'version one' >"$DOC"
}

# Sets SNAPSHOT and SHA from a `create` run.
create_snapshot() {
  run "$SNAP" create "$@"
  [ "$status" -eq 0 ]
  SNAPSHOT="$(printf '%s\n' "$output" | sed -n 's/^snapshot: //p')"
  SHA="$(printf '%s\n' "$output" | sed -n 's/^sha256: //p')"
  [ -n "$SNAPSHOT" ]
  [ -n "$SHA" ]
}

mode_of() {
  # GNU stat first: on Linux `stat -f` means something else and still exits 0.
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"
}

@test "create copies the document read-only into a private directory" {
  create_snapshot "$DOC"

  [ "${SNAPSHOT##*/}" = "plan.md" ]
  [[ "$SNAPSHOT" == "$TMPDIR/.adversarial-review-snapshot."*"/plan.md" ]]
  cmp -s "$DOC" "$SNAPSHOT"
  [ "$(mode_of "$SNAPSHOT")" = "400" ]
  [ "$(mode_of "$(dirname "$SNAPSHOT")")" = "700" ]
  [[ "$SHA" =~ ^[0-9a-f]{64}$ ]]
  [[ "$output" == *"bytes: $(wc -c <"$DOC" | tr -d '[:space:]')"* ]]
}

@test "create under a given parent directory" {
  mkdir -p "$BATS_TEST_TMPDIR/work/sub"
  create_snapshot "$DOC" "$BATS_TEST_TMPDIR/work/sub"
  [[ "$SNAPSHOT" == "$BATS_TEST_TMPDIR/work/sub/.adversarial-review-snapshot."*"/plan.md" ]]
}

@test "check passes while snapshot and source are the approved bytes" {
  create_snapshot "$DOC"
  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 0 ]
  [[ "$output" == "UNCHANGED: $SNAPSHOT sha256 $SHA" ]]
}

@test "source saved after the scan: check fails and the snapshot keeps the old bytes" {
  create_snapshot "$DOC"
  printf '%s\n' 'added after the scan' >>"$DOC"

  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 1 ]
  [[ "$output" == "CHANGED: the source $DOC differs from the approved snapshot"* ]]
  [[ "$output" == *"Send nothing."* ]]
  ! grep -q 'added after the scan' "$SNAPSHOT"
}

@test "snapshot altered after approval: check fails" {
  create_snapshot "$DOC"
  chmod 600 "$SNAPSHOT"
  printf '%s\n' 'tampered' >>"$SNAPSHOT"

  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 1 ]
  [[ "$output" == "CHANGED: the snapshot $SNAPSHOT no longer has the approved sha256"* ]]
}

@test "source deleted or snapshot deleted: check fails" {
  create_snapshot "$DOC"
  rm "$DOC"
  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 1 ]
  [[ "$output" == "CHANGED: the source $DOC is gone"* ]]

  rm -f "$SNAPSHOT"
  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 1 ]
  [[ "$output" == "CHANGED: the snapshot $SNAPSHOT is gone"* ]]
}

@test "a sha256 for other bytes does not pass, whatever its letter case" {
  create_snapshot "$DOC"
  local upper
  upper="$(printf '%s' "$SHA" | tr '[:lower:]' '[:upper:]')"
  run "$SNAP" check "$SNAPSHOT" "$upper" "$DOC"
  [ "$status" -eq 0 ]

  local other="0000000000000000000000000000000000000000000000000000000000000000"
  run "$SNAP" check "$SNAPSHOT" "$other" "$DOC"
  [ "$status" -eq 1 ]

  run "$SNAP" check "$SNAPSHOT" "not-a-hash" "$DOC"
  [ "$status" -eq 2 ]
}

@test "remove deletes the snapshot file and its emptied directory" {
  create_snapshot "$DOC"
  local dir
  dir="$(dirname "$SNAPSHOT")"

  run "$SNAP" remove "$SNAPSHOT"
  [ "$status" -eq 0 ]
  [[ "$output" == "removed: $SNAPSHOT" ]]
  [ ! -e "$dir" ]
  [ -f "$DOC" ]
}

@test "remove refuses a path outside a snapshot directory" {
  run "$SNAP" remove "$DOC"
  [ "$status" -eq 2 ]
  [[ "$output" == *"refusing to remove"* ]]
  [ -f "$DOC" ]
  [ -d "$BATS_TEST_TMPDIR/work" ]
}

@test "remove of a nonexistent path under a matching directory deletes nothing" {
  # A directory that only looks like one of ours, holding someone's file.
  local lookalike="$TMPDIR/.adversarial-review-snapshot.lookalike"
  mkdir -p "$lookalike"
  printf '%s\n' 'unrelated' >"$lookalike/sibling.txt"

  run "$SNAP" remove "$lookalike/plan.md"
  [ "$status" -eq 2 ]
  [[ "$output" == *"not an existing snapshot file; nothing was deleted"* ]]
  [ "$(cat "$lookalike/sibling.txt")" = "unrelated" ]
}

@test "remove leaves and reports anything else in the snapshot directory" {
  create_snapshot "$DOC"
  local dir
  dir="$(dirname "$SNAPSHOT")"
  printf '%s\n' 'payload' >"$dir/other.txt"

  run "$SNAP" remove "$SNAPSHOT"
  [ "$status" -eq 1 ]
  [[ "$output" == "KEPT: "* ]]
  [[ "$output" == *"other.txt"* ]]
  [ ! -e "$SNAPSHOT" ]
  [ "$(cat "$dir/other.txt")" = "payload" ]
}

@test "remove refuses a symlink and a symlinked directory" {
  create_snapshot "$DOC"
  local dir real
  dir="$(dirname "$SNAPSHOT")"
  real="$BATS_TEST_TMPDIR/work/keep.md"
  printf '%s\n' 'keep me' >"$real"
  ln -s "$real" "$dir/link.md"

  run "$SNAP" remove "$dir/link.md"
  [ "$status" -eq 2 ]
  [ "$(cat "$real")" = "keep me" ]

  ln -s "$BATS_TEST_TMPDIR/work" "$TMPDIR/.adversarial-review-snapshot.symlinked"
  run "$SNAP" remove "$TMPDIR/.adversarial-review-snapshot.symlinked/plan.md"
  [ "$status" -eq 2 ]
  [ -f "$DOC" ]
}

# A sha256 tool that fails, or prints something that is not a digest.
stub_hash_tools() {
  local bin="$BATS_TEST_TMPDIR/hashbin" tool
  mkdir -p "$bin"
  for tool in sha256sum shasum; do
    printf '%s\n' '#!/bin/sh' "$1" >"$bin/$tool"
    chmod +x "$bin/$tool"
  done
  PATH="$bin:$PATH"
}

@test "create reports no digest and leaves no snapshot when the hash tool fails" {
  stub_hash_tools 'exit 1'
  run "$SNAP" create "$DOC"
  [ "$status" -eq 2 ]
  [[ "$output" != *"sha256:"* ]]
  [[ "$output" != *"snapshot:"* ]]
  [[ "$output" == *"could not compute the sha256"* ]]
  run find "$TMPDIR" -mindepth 1
  [ -z "$output" ]
}

@test "create rejects a hash tool that prints something other than a digest" {
  stub_hash_tools 'echo "not-a-digest  file"; exit 0'
  run "$SNAP" create "$DOC"
  [ "$status" -eq 2 ]
  [[ "$output" != *"sha256:"* ]]
  run find "$TMPDIR" -mindepth 1
  [ -z "$output" ]
}

@test "check stops when the digest cannot be computed" {
  create_snapshot "$DOC"
  stub_hash_tools 'exit 1'
  run "$SNAP" check "$SNAPSHOT" "$SHA" "$DOC"
  [ "$status" -eq 2 ]
  [[ "$output" != *"UNCHANGED"* ]]
}

@test "usage errors exit 2 and create nothing" {
  run "$SNAP"
  [ "$status" -eq 2 ]
  run "$SNAP" create
  [ "$status" -eq 2 ]
  run "$SNAP" create "$BATS_TEST_TMPDIR/work/missing.md"
  [ "$status" -eq 2 ]
  run "$SNAP" create "$DOC" "$BATS_TEST_TMPDIR/no-such-dir"
  [ "$status" -eq 2 ]
  run "$SNAP" bogus "$DOC"
  [ "$status" -eq 2 ]
  run find "$TMPDIR" -mindepth 1
  [ -z "$output" ]
}
