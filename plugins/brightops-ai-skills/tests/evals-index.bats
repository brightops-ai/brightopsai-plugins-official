#!/usr/bin/env bats
#
# check-index.sh: cases on disk vs the "What the cases cover" table.
# Fixtures live under $BATS_TEST_TMPDIR so the real evals tree is untouched.

setup() {
  PLUGIN_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  CHECK="$PLUGIN_ROOT/evals/check-index.sh"
  TREE="$BATS_TEST_TMPDIR/evals"
}

# A README with a decoy field table (so the checker must not scrape every
# backtick cell) plus a "What the cases cover" table of the given names.
write_readme() {
  mkdir -p "$TREE"
  {
    echo "# Behavioural evals"
    echo
    echo "## Adding a case"
    echo
    echo "| Field | Meaning |"
    echo "|---|---|"
    echo "| \`questions\` | how many |"
    echo "| \`must_contain\` | substrings |"
    echo
    echo "## What the cases cover"
    echo
    echo "| Case | Guarantee |"
    echo "|---|---|"
    local name
    for name in "$@"; do
      # shellcheck disable=SC2016  # literal backticks are the table's cell delimiters
      printf '| `%s` | Guarantee for %s |\n' "$name" "$name"
    done
    echo
    echo "## What it deliberately does not cover"
    echo
    echo "- Quality"
  } >"$TREE/README.md"
}

write_cases() {
  local name
  mkdir -p "$TREE/cases"
  for name in "$@"; do
    mkdir -p "$TREE/cases/$name"
  done
}

@test "complete table passes" {
  write_readme alpha beta
  write_cases alpha beta
  run "$CHECK" "$TREE"
  [ "$status" -eq 0 ]
}

@test "missing row fails naming the case" {
  write_readme alpha
  write_cases alpha orphan
  run "$CHECK" "$TREE"
  [ "$status" -eq 1 ]
  [[ "$output" == *"orphan"* ]]
}

@test "extra row fails naming the row" {
  write_readme alpha ghost
  write_cases alpha
  run "$CHECK" "$TREE"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ghost"* ]]
}
