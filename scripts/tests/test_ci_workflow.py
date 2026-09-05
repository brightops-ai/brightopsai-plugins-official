"""CI workflow contract — the packaging gate named in CONTRIBUTING.md."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# Commands the issue requires as named, failing steps. Literals are the spec.
REQUIRED_COMMANDS = (
    "claude plugin validate . --strict",
    "python3 scripts/check-marketplace.py",
    "python3 -m unittest discover -s scripts/tests -t scripts",
    "python3 -m unittest discover -s dream/tests -t .",
    "plugins/brightops-ai-skills/tests/run.sh --unit",
    "gitleaks detect --no-git --config .gitleaks.toml --redact",
    "plugins/brightops-ai-skills/evals/check-index.sh",
)


class TestCiWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(
            WORKFLOW.is_file(),
            "missing .github/workflows/ci.yml (packaging gate)",
        )
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_runs_required_gates(self) -> None:
        missing = [item for item in REQUIRED_COMMANDS if item not in self.text]
        self.assertEqual(
            missing,
            [],
            f"ci.yml missing required gate commands: {missing}",
        )

    def test_workflow_triggers_on_pull_request_and_main(self) -> None:
        self.assertIn("pull_request:", self.text)
        self.assertIn("\n      - main\n", self.text)

    def test_validate_uses_isolated_config_dir(self) -> None:
        self.assertIn("CLAUDE_CONFIG_DIR", self.text)

    def test_gitleaks_drops_bytecode_caches(self) -> None:
        # --no-git walks untracked files; unit tests leave __pycache__ behind.
        self.assertIn('find . -name __pycache__', self.text)

    def test_behavioural_evals_stay_manual(self) -> None:
        self.assertIn("evals/run.sh", self.text)
        self.assertIn("stay manual", self.text)

    def test_discovers_other_plugin_bats_suites(self) -> None:
        self.assertIn("plugins/*/tests/*.bats", self.text)

    def test_installs_claude_cli_and_bats_shellcheck(self) -> None:
        self.assertIn("npm install -g", self.text)
        self.assertIn("@anthropic-ai/claude-code", self.text)
        self.assertIn("apt-get install -y bats shellcheck", self.text)
        self.assertIn("ubuntu-latest", self.text)
        self.assertIn("actions/checkout@v4", self.text)
        self.assertIn("actions/setup-node@v4", self.text)
        self.assertIn("actions/setup-python@v5", self.text)
        self.assertIn("node-version:", self.text)
        self.assertIn("22", self.text)
        self.assertIn("python-version:", self.text)
        self.assertIn("3.12", self.text)
