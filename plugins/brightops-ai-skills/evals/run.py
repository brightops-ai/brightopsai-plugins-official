#!/usr/bin/env python3
"""Behavioural eval runner for the improve-prompt skill.

Drives the skill through headless `claude -p` and asserts on observable output.
See README.md in this directory for what it covers and what it does not.
"""
import json, os, re, subprocess, sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SKILL = EVALS.parent / "skills" / "prompting" / "improve-prompt"
MODEL = os.environ.get("EVAL_MODEL", "claude-sonnet-5")
RUNS = int(os.environ.get("EVAL_RUNS", "1"))
TIMEOUT = int(os.environ.get("EVAL_TIMEOUT", "300"))

FENCE = re.compile(r"^```", re.M)


def system_prompt() -> str:
    body = (SKILL / "SKILL.md").read_text()
    body = re.sub(r"^---\n.*?\n---\n", "", body, flags=re.S)
    parts = [
        "Execute the skill defined below on the user's message. The skill's "
        "reference files follow it inline; do not look for them on disk.",
        body,
    ]
    for ref in sorted((SKILL / "references").glob("*.md")):
        parts.append(f"# Reference: references/{ref.name}\n\n{ref.read_text()}")
    return "\n\n".join(parts)


def split_fences(text: str):
    """Return (inside_fences, outside_fences) as strings."""
    inside, outside, in_fence = [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        (inside if in_fence else outside).append(line)
    return "\n".join(inside), "\n".join(outside)


def count_questions(outside: str) -> int:
    return sum(1 for ln in outside.splitlines() if ln.strip().endswith("?"))


def run_case(name: str, sysprompt: str):
    case = EVALS / "cases" / name
    prompt = (case / "input.txt").read_text()
    exp = json.loads((case / "expect.json").read_text())
    out = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--max-turns", "3",
         "--append-system-prompt", sysprompt, prompt],
        capture_output=True, text=True, timeout=TIMEOUT,
    ).stdout
    inside, outside = split_fences(out)
    hay = out if exp.get("case_sensitive") else out.lower()

    def norm(s):
        return s if exp.get("case_sensitive") else s.lower()

    fails = []
    q = count_questions(outside)
    want = exp.get("questions")
    if want == "none" and q != 0:
        fails.append(f"asked {q} question(s); none should be asked when nothing blocks")
    if want == "1-3" and not (1 <= q <= 3):
        fails.append(f"asked {q} question(s); expected 1-3 for a blocking gap")

    for s in exp.get("must_contain", []):
        if norm(s) not in hay:
            fails.append(f"missing verbatim {s!r}")
    for key in ("must_contain_any", "must_contain_any_2"):
        opts = exp.get(key)
        if opts and not any(norm(s) in hay for s in opts):
            fails.append(f"none of {opts} present")
    for s in exp.get("must_not_contain", []):
        if norm(s) in hay:
            fails.append(f"present but should not be: {s!r}")

    a = exp.get("assumptions", "optional")
    has_a = "what i assumed" in out.lower()
    if a == "required" and not has_a:
        fails.append("no 'What I assumed' block")
    if a == "forbidden" and has_a:
        fails.append("'What I assumed' block present but nothing was assumed")

    if want == "none" and len(FENCE.findall(out)) != 2:
        fails.append(f"expected exactly one fenced brief, found {len(FENCE.findall(out))//2}")

    return fails, out


def main():
    names = sorted(p.name for p in (EVALS / "cases").iterdir() if p.is_dir())
    if len(sys.argv) > 1:
        names = [n for n in names if any(a in n for a in sys.argv[1:])]
    sysprompt = system_prompt()
    print(f"model={MODEL} runs={RUNS} cases={len(names)}\n")
    failed = 0
    for name in names:
        for r in range(RUNS):
            tag = f"{name}" + (f" (run {r+1})" if RUNS > 1 else "")
            try:
                fails, out = run_case(name, sysprompt)
            except subprocess.TimeoutExpired:
                print(f"  FAIL  {tag}: timed out after {TIMEOUT}s"); failed += 1; continue
            if fails:
                failed += 1
                print(f"  FAIL  {tag}")
                for f in fails:
                    print(f"          {f}")
                (EVALS / "results").mkdir(exist_ok=True)
                (EVALS / "results" / f"{name}.out").write_text(out)
            else:
                print(f"  PASS  {tag}")
    print()
    print("ALL CASES PASSED" if not failed else f"{failed} case run(s) FAILED (output in evals/results/)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
