#!/bin/sh
# Store a 1Password service account token for T3 Code without printing it or putting it in argv.
# Each subcommand prints one "ok: ..." or "FAIL: ..." line and exits non-zero on failure. The
# token file is validated first (readable regular file, non-empty, one line, starts with ops_,
# no characters that could break a command line); on any validation failure nothing changes.
#
# Usage:
#   op_token.sh keychain <token-file>
#       write the token to the keychain item op_service_account, feeding the command to
#       `security -i` on stdin, then read the item back and compare inside this script
#   op_token.sh service-env <token-file> <t3-home>
#       replace the OP_SERVICE_ACCOUNT_TOKEN= line of <t3-home>/service.env: build the new
#       file in a 0600 temporary file in the same directory (other lines kept, a missing
#       trailing newline handled), then rename it into place
#   op_token.sh remove-service-env <t3-home>
#       remove that one line the same atomic way
#
# Environment:
#   T3_OP_TOKEN_SECURITY  security to use (default /usr/bin/security); for tests only, the
#                         default is what runs live

SECURITY="${T3_OP_TOKEN_SECURITY:-/usr/bin/security}"
ACCOUNT="${USER:-$(id -un)}"
LINE_NAME="OP_SERVICE_ACCOUNT_TOKEN"
USAGE="usage: op_token.sh keychain <token-file> | service-env <token-file> <t3-home> | remove-service-env <t3-home>"
TOKEN=""
TMP=""

trap '[ -z "$TMP" ] || rm -f "$TMP"' EXIT HUP INT TERM

fail() { echo "FAIL: $*"; exit 1; }
ok() { echo "ok: $*"; }

# Read and validate the token file into TOKEN. Print nothing about its content.
load_token() {
  [ -n "$1" ] || fail "no token file given"
  [ -f "$1" ] && [ ! -L "$1" ] || fail "token file is not a regular file"
  [ -r "$1" ] || fail "token file is not readable"
  [ -s "$1" ] || fail "token file is empty"
  [ "$(wc -l <"$1" | tr -d ' ')" -le 1 ] || fail "token file holds more than one line"
  TOKEN="$(cat "$1")" || fail "token file could not be read"
  [ -n "$TOKEN" ] || fail "token file is empty"
  case "$TOKEN" in
    ops_*) ;;
    *) fail "token does not start with ops_" ;;
  esac
  case "$TOKEN" in
    *[!A-Za-z0-9_=.+/-]*) fail "token holds a character a service account token does not" ;;
  esac
}

load_home() {
  [ -n "$1" ] || fail "no T3 home given"
  [ -d "$1" ] || fail "T3 home is not a directory"
  [ ! -L "$1/service.env" ] || fail "service.env is a symlink; refusing to replace it"
  [ ! -e "$1/service.env" ] || [ -f "$1/service.env" ] || fail "service.env is not a regular file"
}

# Rewrite $1/service.env without its token line; with $2 set, append "OP_SERVICE_ACCOUNT_TOKEN=$2".
rewrite_service_env() {
  _home="$1"; _new="$2"
  _file="$_home/service.env"
  umask 077
  TMP="$(mktemp "$_home/.service.env.XXXXXX")" || fail "could not create a temporary file in the T3 home"
  if [ -f "$_file" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
      case "$_line" in
        "$LINE_NAME="*) ;;
        *) printf '%s\n' "$_line" ;;
      esac
    done <"$_file" >"$TMP" || fail "could not copy service.env"
  fi
  if [ -n "$_new" ]; then
    printf '%s=%s\n' "$LINE_NAME" "$_new" >>"$TMP" || fail "could not write the temporary file"
  fi
  chmod 600 "$TMP" || fail "could not set the mode of the temporary file"
  mv -f "$TMP" "$_file" || fail "could not rename the new service.env into place"
  TMP=""
}

cmd_keychain() {
  load_token "$1"
  case "$ACCOUNT" in
    ''|*[!A-Za-z0-9._-]*) fail "the account name holds a character the keychain command cannot take" ;;
  esac
  # printf is a shell builtin, so the token is on stdin of security and in no argument list.
  if ! printf 'add-generic-password -U -a "%s" -s op_service_account -w "%s"\n' "$ACCOUNT" "$TOKEN" | "$SECURITY" -i >/dev/null 2>&1; then
    fail "security did not accept the keychain write"
  fi
  _back="$("$SECURITY" find-generic-password -a "$ACCOUNT" -s op_service_account -w 2>/dev/null)"
  if [ "$_back" = "$TOKEN" ]; then
    ok "keychain item op_service_account written and read back"
  else
    fail "keychain item op_service_account does not read back as the given token"
  fi
}

cmd_service_env() {
  load_token "$1"
  load_home "$2"
  rewrite_service_env "$2" "$TOKEN"
  ok "service.env holds one $LINE_NAME line, mode 0600"
}

cmd_remove_service_env() {
  load_home "$1"
  if [ ! -e "$1/service.env" ]; then ok "service.env does not exist; nothing to remove"; return; fi
  rewrite_service_env "$1" ""
  ok "service.env holds no $LINE_NAME line"
}

case "$1" in
  keychain) [ $# -eq 2 ] || { echo "$USAGE" >&2; exit 2; }; cmd_keychain "$2" ;;
  service-env) [ $# -eq 3 ] || { echo "$USAGE" >&2; exit 2; }; cmd_service_env "$2" "$3" ;;
  remove-service-env) [ $# -eq 2 ] || { echo "$USAGE" >&2; exit 2; }; cmd_remove_service_env "$2" ;;
  *) echo "$USAGE" >&2; exit 2 ;;
esac
