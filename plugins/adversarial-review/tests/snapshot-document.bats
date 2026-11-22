#!/usr/bin/env bats
#
# snapshot-document.sh: the scanned, approved and uploaded bytes are one copy.
#   create  private read-only copy, prints snapshot / sha256 / bytes
#   check   exit 0 UNCHANGED, exit 1 CHANGED (snapshot altered or source moved on)
#   remove  deletes only a directory `create` made

setup() {
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

@test "remove deletes the snapshot directory and nothing else" {
  create_snapshot "$DOC"
  local dir
  dir="$(dirname "$SNAPSHOT")"

  run "$SNAP" remove "$SNAPSHOT"
  [ "$status" -eq 0 ]
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
