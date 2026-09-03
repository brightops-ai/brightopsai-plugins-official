#!/usr/bin/env bash
# Test suite for the brightops-ai-skills plugin: lint every shell file, then
# run the bats specs.
#
#   tests/run.sh          everything
#   tests/run.sh --unit   pure specs only — no multiplexer binary required
#
# Specs that drive a terminal multiplexer address a private server by socket
# name (see helpers/tmux-sandbox.bash) and only ever create zz-spawn-*
# sessions, so running this suite from inside a live session is safe. No spec
# launches the real CLI.
#
# -x follows sourced files; -P SCRIPTDIR resolves them relative to the file
# being checked rather than the working directory. The helpers are linted too:
# the file every live spec trusts to keep the server private must not escape
# lint.

set -euo pipefail

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."

shell_files() {
  find skills -name '*.sh' -type f
  echo tests/run.sh
  find tests/helpers -name '*.bash' -type f
}

echo "== shellcheck =="
# shellcheck disable=SC2046 # word splitting is the point: one arg per file
shellcheck -x -P SCRIPTDIR $(shell_files | sort)
echo "ok"

echo
echo "== bats =="
if [[ "${1:-}" == "--unit" ]]; then
  bats --filter-tags '!live' tests/spawn-session.bats
else
  bats tests/spawn-session.bats
fi
