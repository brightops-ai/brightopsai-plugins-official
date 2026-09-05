#!/usr/bin/env bash
#
# scan-secrets.sh — scan one document for secrets before uploading it.
#
# Usage: scan-secrets.sh <file>
#   exit 0  clean — safe to upload
#   exit 1  hit(s) found — print each finding, then: BLOCKED: do not upload
#   exit 2  usage / not a file / gitleaks crashed
#
# Finding lines look like:
#   rule: <id>  file: <path>  line: <n>
#
# gitleaks (preferred):
#   gitleaks detect --no-git --no-banner --redact --source <file>
#   plus --report-format json --report-path <tmp>
#   plus --config <repo>/.gitleaks.toml when the file sits in a git work tree
#   that has one (git -C <dir> rev-parse --show-toplevel). Otherwise gitleaks
#   defaults.
#
# SCAN_SECRETS_GITLEAKS (test / override):
#   unset     use `gitleaks` from PATH if present, else the bundled fallback
#   empty     force the bundled python3 fallback (even if gitleaks is on PATH)
#   <path>    use that executable as gitleaks
#
# Fallback: scan_secrets.py in this directory — a small high-confidence set
# (private key blocks, AWS access key ids, GitHub/OpenAI/Slack/Stripe-style
# token prefixes, JWT shape, password/secret/api_key assignments). Prints a
# FALLBACK line recommending gitleaks. Not a substitute for gitleaks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
FALLBACK_PY="$SCRIPT_DIR/scan_secrets.py"
BLOCKED_LINE="BLOCKED: do not upload"

usage() {
  echo "usage: scan-secrets.sh <file>" >&2
  exit 2
}

if [[ $# -ne 1 ]]; then
  usage
fi

FILE=$1
if [[ ! -f "$FILE" ]]; then
  echo "scan-secrets.sh: not a file: $FILE" >&2
  exit 2
fi

emit_blocked() {
  echo "$BLOCKED_LINE"
}

# Prints the gitleaks binary to stdout. Returns 1 when the fallback must run.
gitleaks_bin() {
  if [[ -n "${SCAN_SECRETS_GITLEAKS+x}" ]]; then
    if [[ -z "$SCAN_SECRETS_GITLEAKS" ]]; then
      return 1
    fi
    printf '%s\n' "$SCAN_SECRETS_GITLEAKS"
    return 0
  fi
  if command -v gitleaks >/dev/null 2>&1; then
    command -v gitleaks
    return 0
  fi
  return 1
}

print_gitleaks_findings() {
  local report=$1
  python3 - "$report" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        raw = fh.read().strip()
    data = json.loads(raw or "[]")
except (OSError, json.JSONDecodeError):
    data = []
if not isinstance(data, list):
    data = []
for item in data:
    if not isinstance(item, dict):
        continue
    rule = item.get("RuleID") or "unknown"
    file = item.get("File") or ""
    line = item.get("StartLine") or 0
    print(f"rule: {rule}  file: {file}  line: {line}")
PY
}

run_fallback() {
  local status=0
  python3 "$FALLBACK_PY" "$FILE" || status=$?
  if [[ $status -eq 0 ]]; then
    exit 0
  fi
  if [[ $status -eq 1 ]]; then
    emit_blocked
    exit 1
  fi
  exit "$status"
}

run_gitleaks() {
  local bin=$1
  local report err
  report=$(mktemp)
  err=$(mktemp)
  trap 'rm -f "$report" "$err"' EXIT

  local -a args
  args=(
    detect
    --no-git
    --no-banner
    --redact
    --source "$FILE"
    --report-format json
    --report-path "$report"
  )

  local dir repo
  dir=$(dirname -- "$FILE")
  if repo=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null); then
    if [[ -f "$repo/.gitleaks.toml" ]]; then
      args+=(--config "$repo/.gitleaks.toml")
    fi
  fi

  local status=0
  "$bin" "${args[@]}" >/dev/null 2>"$err" || status=$?

  if [[ $status -eq 0 ]]; then
    exit 0
  fi
  if [[ $status -eq 1 ]]; then
    print_gitleaks_findings "$report"
    emit_blocked
    exit 1
  fi
  cat "$err" >&2
  echo "scan-secrets.sh: gitleaks failed with status $status" >&2
  exit 2
}

if bin=$(gitleaks_bin); then
  run_gitleaks "$bin"
else
  run_fallback
fi
