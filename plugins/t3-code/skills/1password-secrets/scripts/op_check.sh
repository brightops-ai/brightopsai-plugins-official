#!/bin/sh
# Check the 1Password setup for T3 Code without printing a token or a resolved value.
# Each check prints one "ok: ..." or "FAIL: ..." line; the exit status is non-zero if any failed.
#
# Usage: op_check.sh keychain | launchd | refs | session [NAME ...]
#   keychain  the keychain item op_service_account exists and its value starts with ops_
#   launchd   the launchd environment value equals the keychain value (only match or mismatch
#             is reported)
#   refs      every reference in the references file resolves with `op read`, using the token
#             from the keychain; reported by variable name only
#   session   this session has OP_SERVICE_ACCOUNT_TOKEN, `op whoami` reports a service
#             account, every named variable is set, and no OP_CONNECT_* is set. The names are
#             the arguments; with none, the names in the references file.
#
# The references file is read only through `t3_op_env_sync.py --list-references`, which applies
# the rules of a sync. When it rejects the file, this script prints that script's own
# line-numbered message and does not call op, so a literal value never reaches op.
#
# Environment:
#   T3_OP_ENV               references file (default ~/.config/claude/op.env)
#   T3_OP_CHECK_SYNC        sync script (default: t3_op_env_sync.py beside this script)
#   T3_OP_CHECK_PYTHON      python (default python3)
#   T3_OP_CHECK_SECURITY    security to use (default /usr/bin/security)   } for tests only;
#   T3_OP_CHECK_LAUNCHCTL   launchctl to use (default /bin/launchctl)     } the defaults are
#   T3_OP_CHECK_OP          op to use (default: op on PATH)               } what runs live

# The token is exported only inside a subshell that runs op, so it never reaches argv or this shell.
# shellcheck disable=SC2030,SC2031
SECURITY="${T3_OP_CHECK_SECURITY:-/usr/bin/security}"
LAUNCHCTL="${T3_OP_CHECK_LAUNCHCTL:-/bin/launchctl}"
OP="${T3_OP_CHECK_OP:-op}"
SYNC="${T3_OP_CHECK_SYNC:-$(dirname "$0")/t3_op_env_sync.py}"
PYTHON="${T3_OP_CHECK_PYTHON:-python3}"
ACCOUNT="${USER:-$(id -un)}"
FAILED=0

ok() { echo "ok: $*"; }
bad() { echo "FAIL: $*"; FAILED=1; }

keychain_token() { "$SECURITY" find-generic-password -a "$ACCOUNT" -s op_service_account -w 2>/dev/null; }

# Put "name<TAB>reference" per entry of the references file in REF_LIST, from the sync script's
# validator. Return 1, with the script's own one-line message in REF_ERROR, when it rejects the
# file; nothing from the file is kept in that case. Not called in a command substitution, so the
# variables survive.
REF_LIST=""
REF_ERROR=""
list_references() {
  REF_LIST=""
  REF_ERROR=""
  _errf="$(mktemp)" || { REF_ERROR="could not create a temporary file"; return 1; }
  if REF_LIST="$("$PYTHON" "$SYNC" --list-references 2>"$_errf")"; then rm -f "$_errf"; return 0; fi
  REF_LIST=""
  REF_ERROR="$(head -n 1 "$_errf")"
  rm -f "$_errf"
  [ -n "$REF_ERROR" ] || REF_ERROR="the references file was rejected"
  return 1
}

check_keychain() {
  _tok="$(keychain_token)"
  if [ -z "$_tok" ]; then bad "keychain item op_service_account not found"; return; fi
  case "$_tok" in
    ops_*) ok "keychain item op_service_account exists and starts with ops_" ;;
    *) bad "keychain item op_service_account does not start with ops_" ;;
  esac
}

check_launchd() {
  _tok="$(keychain_token)"
  _env="$("$LAUNCHCTL" getenv OP_SERVICE_ACCOUNT_TOKEN 2>/dev/null)"
  if [ -z "$_tok" ]; then bad "keychain item op_service_account not found"; return; fi
  if [ -z "$_env" ]; then bad "launchd has no OP_SERVICE_ACCOUNT_TOKEN"; return; fi
  if [ "$_env" = "$_tok" ]; then ok "launchd value matches the keychain value"; else bad "launchd value differs from the keychain value"; fi
}

check_refs() {
  _tok="$(keychain_token)"
  if [ -z "$_tok" ]; then bad "keychain item op_service_account not found"; return; fi
  if ! list_references; then bad "references file: $REF_ERROR"; return; fi
  _count=0
  _tab="$(printf '\t')"
  # Read through a here-document, not a pipe, so the loop runs in this shell and can set FAILED.
  while IFS="$_tab" read -r _name _ref; do
    [ -n "$_name" ] || continue
    _count=$((_count+1))
    if ( unset OP_CONNECT_HOST OP_CONNECT_TOKEN; OP_SERVICE_ACCOUNT_TOKEN="$_tok"; export OP_SERVICE_ACCOUNT_TOKEN; "$OP" read "$_ref" >/dev/null 2>&1 ); then
      ok "$_name resolves"
    else
      bad "$_name does not resolve"
    fi
  done <<REFS
$REF_LIST
REFS
  if [ "$_count" = 0 ]; then bad "references file holds no references"; fi
}

check_name() {
  case "$1" in
    ''|[0-9]*|*[!A-Za-z0-9_]*) bad "$1: not a variable name"; return ;;
  esac
  if [ -n "$(printenv "$1" 2>/dev/null)" ]; then ok "$1 is set"; else bad "$1 is not set"; fi
}

check_session() {
  if [ -n "$OP_SERVICE_ACCOUNT_TOKEN" ]; then ok "OP_SERVICE_ACCOUNT_TOKEN is set"; else bad "OP_SERVICE_ACCOUNT_TOKEN is not set"; fi
  if "$OP" whoami 2>/dev/null | grep -q 'SERVICE_ACCOUNT'; then ok "op whoami reports a service account"; else bad "op whoami does not report a service account"; fi
  if [ $# -gt 0 ]; then
    for _name in "$@"; do check_name "$_name"; done
  elif list_references; then
    _tab="$(printf '\t')"
    while IFS="$_tab" read -r _name _ref; do
      [ -n "$_name" ] || continue
      check_name "$_name"
    done <<REFS
$REF_LIST
REFS
  else
    bad "references file: $REF_ERROR"
  fi
  if env | grep -q '^OP_CONNECT_'; then bad "an OP_CONNECT_* variable is set"; else ok "no OP_CONNECT_* variable is set"; fi
}

CMD="$1"
[ $# -eq 0 ] || shift
case "$CMD" in
  keychain) check_keychain ;;
  launchd) check_launchd ;;
  refs) check_refs ;;
  session) check_session "$@" ;;
  *) echo "usage: op_check.sh keychain | launchd | refs | session [NAME ...]" >&2; exit 2 ;;
esac
exit "$FAILED"
