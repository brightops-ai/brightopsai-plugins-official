#!/usr/bin/env bats
#
# scan-secrets.sh: exit 0 = clean, 1 = hit (do not upload), 2 = usage.
#
# Secret-shaped material is built at runtime under $BATS_TEST_TMPDIR so the
# repo's gitleaks hook never sees a key-shaped tracked file.
#
# SCAN_SECRETS_GITLEAKS= (empty) forces the bundled fallback; see the script
# header. Do not put a gitleaks shim on PATH.

setup() {
  PLUGIN_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCAN="$PLUGIN_ROOT/skills/adversarial-review/scripts/scan-secrets.sh"
}

# Assemble a PEM-looking block without storing a contiguous header in this file.
write_key_fixture() {
  local path="$1"
  if command -v ssh-keygen >/dev/null 2>&1; then
    local keydir="$BATS_TEST_TMPDIR/ssh"
    mkdir -p "$keydir"
    ssh-keygen -t ed25519 -f "$keydir/id" -N "" -q
    cat "$keydir/id" >"$path"
    return
  fi
  local beg mid end
  beg="-----BEGIN"
  mid="OPENSSH PRIVATE"
  end="KEY-----"
  printf '%s\n' "${beg} ${mid} ${end}" \
    "REPLACE_ME_NOT_A_REAL_KEY_BODY" \
    "-----END ${mid} ${end}" >"$path"
}

@test "missing argument exits 2" {
  run "$SCAN"
  [ "$status" -eq 2 ]
}

@test "clean file exits 0" {
  local doc="$BATS_TEST_TMPDIR/plan.md"
  cat >"$doc" <<'EOF'
# Plan
Discuss token rotation and the password reset flow in docs.
No credentials belong in this file.
EOF
  run "$SCAN" "$doc"
  [ "$status" -eq 0 ]
  [[ "$output" != *"BLOCKED:"* ]]
}

@test "private key fixture exits 1 and names the rule and file" {
  local doc="$BATS_TEST_TMPDIR/leaky.md"
  write_key_fixture "$doc"
  run "$SCAN" "$doc"
  [ "$status" -eq 1 ]
  [[ "$output" == *"rule: "* ]]
  [[ "$output" == *"file: "*"$doc"* ]]
  [[ "$output" == *"BLOCKED: do not upload"* ]]
}

@test "SCAN_SECRETS_GITLEAKS= empty forces the fallback and still blocks a key" {
  local doc="$BATS_TEST_TMPDIR/leaky-fallback.md"
  write_key_fixture "$doc"
  run env SCAN_SECRETS_GITLEAKS= "$SCAN" "$doc"
  [ "$status" -eq 1 ]
  [[ "$output" == *"fallback"* ]] || [[ "$output" == *"FALLBACK"* ]]
  [[ "$output" == *"gitleaks"* ]]
  [[ "$output" == *"rule: "* ]]
  [[ "$output" == *"file: "*"$doc"* ]]
  [[ "$output" == *"BLOCKED: do not upload"* ]]
}

@test "gitleaks uses the enclosing repo .gitleaks.toml when present" {
  if ! command -v gitleaks >/dev/null 2>&1; then
    skip "gitleaks not on PATH"
  fi
  local repo="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$repo"
  git -C "$repo" init -q
  printf '%s\n' 'title = "canary"' '[[rules]]' 'id = "canary"' \
    'description = "test canary"' 'regex = "CANARYTOKEN12345"' \
    >"$repo/.gitleaks.toml"
  printf '%s\n' "marker CANARYTOKEN12345 in prose" >"$repo/doc.md"
  run "$SCAN" "$repo/doc.md"
  [ "$status" -eq 1 ]
  [[ "$output" == *"rule: canary"* ]]
  [[ "$output" == *"file: "*"$repo/doc.md"* ]]
  [[ "$output" == *"BLOCKED: do not upload"* ]]
}
