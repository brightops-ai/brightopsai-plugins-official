#!/usr/bin/env bash
# Behavioural evals for the improve-prompt skill.
#   ./evals/run.sh              # every case
#   ./evals/run.sh referent     # cases matching a substring
# EVAL_MODEL, EVAL_RUNS, EVAL_TIMEOUT override the defaults.
set -euo pipefail
exec python3 "$(dirname "$0")/run.py" "$@"
