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
MAX_TURNS = os.environ.get("EVAL_MAX_TURNS", "8")
RUNS = int(os.environ.get("EVAL_RUNS", "1"))
TIMEOUT = int(os.environ.get("EVAL_TIMEOUT", "300"))

FENCE = re.compile(r"^```", re.M)


def harness_error(out: str):
    """Return a reason string when the run failed for a non-behavioural cause."""
    t = out.strip()
    if not t:
        return "empty output from claude -p"
    if t.startswith("Error:"):
        return t.splitlines()[0]
    if "```" not in t and len(t) < 200:
        return f"no brief emitted; output was {t[:120]!r}"
    return None


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
        ["claude", "-p", "--model", MODEL, "--max-turns", MAX_TURNS,
         "--append-system-prompt", sysprompt, prompt],
        capture_output=True, text=True, timeout=TIMEOUT,
    ).stdout
    # A harness problem is not a behavioural regression. Reporting it as one
    # sends you debugging the skill when the runner is what is misconfigured.
    err = harness_error(out)
    if err:
        return None, err, out
    inside, outside = split_fences(out)
    cs = exp.get("case_sensitive")
    brief = inside if cs else inside.lower()
    whole = out if cs else out.lower()

    def norm(s):
        return s if cs else s.lower()

    fails = []
    q = count_questions(outside)
    want = exp.get("questions")
    if want == "none" and q != 0:
        fails.append(f"asked {q} question(s); none should be asked when nothing blocks")
    if want == "1-3" and not (1 <= q <= 3):
        fails.append(f"asked {q} question(s); expected 1-3 for a blocking gap")

    for s in exp.get("must_contain", []):
        if norm(s) not in brief:
            fails.append(f"missing verbatim from brief: {s!r}")
    for key in ("must_contain_any", "must_contain_any_2"):
        opts = exp.get(key)
        if opts and not any(norm(s) in brief for s in opts):
            fails.append(f"brief contains none of {opts}")
    for s in exp.get("must_not_contain", []):
        if norm(s) in brief:
            fails.append(f"present in brief but should not be: {s!r}")
    for s in exp.get("must_not_contain_anywhere", []):
        if norm(s) in whole:
            fails.append(f"present in output but should not be: {s!r}")

    a = exp.get("assumptions", "optional")
    has_a = "what i assumed" in out.lower()
    if a == "required" and not has_a:
        fails.append("no 'What I assumed' block")
    if a == "forbidden" and has_a:
        fails.append("'What I assumed' block present but nothing was assumed")

    if want == "none" and len(FENCE.findall(out)) != 2:
        fails.append(f"expected exactly one fenced brief, found {len(FENCE.findall(out))//2}")

    return fails, None, out


def main():
    names = sorted(p.name for p in (EVALS / "cases").iterdir() if p.is_dir())
    if len(sys.argv) > 1:
        names = [n for n in names if any(a in n for a in sys.argv[1:])]
    sysprompt = system_prompt()
    print(f"model={MODEL} runs={RUNS} cases={len(names)}\n")
    failed = errored = 0
    for name in names:
        for r in range(RUNS):
            tag = f"{name}" + (f" (run {r+1})" if RUNS > 1 else "")
            try:
                fails, err, out = run_case(name, sysprompt)
            except subprocess.TimeoutExpired:
                print(f"  ERROR {tag}: timed out after {TIMEOUT}s"); errored += 1; continue
            if err:
                print(f"  ERROR {tag}: {err}")
                print("          harness problem, not a behavioural result")
                errored += 1
                continue
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
    if errored:
        print(f"{errored} run(s) did not produce a result (harness problem — fix before trusting the rest)")
    if failed:
        print(f"{failed} case run(s) FAILED (output in evals/results/)")
    if not failed and not errored:
        print("ALL CASES PASSED")
    return 1 if (failed or errored) else 0


if __name__ == "__main__":
    sys.exit(main())
