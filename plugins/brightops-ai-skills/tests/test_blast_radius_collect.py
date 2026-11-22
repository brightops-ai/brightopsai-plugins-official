"""Unit tests for the blast-radius-audit evidence collector.

The collector's contract is that it never prints a secret value and never
writes anything. Both are asserted here against a planted-hazard fixture: a
throwaway repository and a throwaway home directory, never the real ones.

Secret-shaped strings are assembled at runtime so this tracked file does not
itself match gitleaks when the repo is scanned. Every planted value carries
the marker ``PLANTED``; the leak test fails if that marker reaches the output.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

MARK = "PLANTED"
LIVE_KEY = "sk_" + "live_" + MARK + "0" * 20
GH_TOKEN = "gh" + "p_" + MARK + "a1B2" * 8
NPM_TOKEN = "npm" + "_" + MARK + "A1b2" * 8
AWS_SECRET = MARK + "awsSecret" + "Xy9/" * 6
PASSWORD = MARK + "-db-pw"
# Values with no marker and nothing token-shaped about them: the kind a
# heuristic redactor lets through. None may appear in any output.
CANARIES = [
    "winterblue7", "tangerine-harbor-51", "orchardcanary3", "quartzcanary8",
    "Zq7pR2mX9vL4kT8wB1nC5hJ3", "maplecanary2", "lilaccanary6", "plumcanary9",
    "fakequoted", "fakeargv", "fakeimage", "orchidheader4", "cedarline5", "birchvalue6",
]


def _load_collector():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "safety" / "blast-radius-audit" / "scripts" / "collect.py"
    spec = importlib.util.spec_from_file_location("blast_radius_collect", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(base: Path, rel: str, text: str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _private_key() -> str:
    beg, mid, end = "-----BEGIN", "OPENSSH PRIVATE", "KEY-----"
    return f"{beg} {mid} {end}\n{MARK}keybodyREPLACE_ME\n-----END {mid} {end}\n"


def _build_repo(repo: Path, outside: Path) -> None:
    _write(repo, ".gitignore", ".env\n")
    _write(repo, ".env", f"API_TOKEN={GH_TOKEN}\nPRIVATE_KEY=\"-----BEGIN FAKE-----\ncedarline5=\n"
                         "birchvalue6=remaining material\n-----END FAKE-----\"\nAFTER_KEY=1\n")
    _write(repo, "terraform.tfvars", "db_url = \"postgres://u:pw@statefile.example.com/app\"\n")
    _write(repo, ".env.test",
           f"DATABASE_URL=postgres://app:{PASSWORD}@prod-db.example.com:5432/app\n"
           f"STRIPE_SECRET_KEY={LIVE_KEY}\nREDIS_HOST=localhost\n")
    _write(repo, ".env.example", "DATABASE_URL=postgres://REPLACE_ME:REPLACE_ME@localhost:5432/app_dev\n")
    _write(repo, "docker-compose.yml",
           "services:\n  db:\n    image: postgres:16\n  app:\n    environment:\n"
           f"      DATABASE_URL: postgres://app:{MARK}/slashpw@db.internal.example.com/app\n")
    _write(repo, "scripts/clean.sh", '#!/bin/bash\nrm -rf "$BUILD_DIR"/*\nrm -rf "${TMP:?}/cache"\n')
    _write(repo, "scripts/safe.sh", "#!/usr/bin/env bash\nset -euo pipefail\necho ok\n")
    _write(repo, "scripts/deploy.sh",
           "#!/usr/bin/env bash\nset -euo pipefail\nterraform apply -auto-approve\ngit push --force origin main\n")
    _write(repo, "infra/main.tf",
           'resource "aws_db_instance" "main" {\n  engine = "postgres"\n  skip_final_snapshot = true\n}\n\n'
           'resource "aws_s3_bucket" "ok" {\n  bucket = "x"\n  lifecycle {\n    prevent_destroy = true\n  }\n}\n')
    _write(repo, "infra/terraform.tfstate", "{}\n")
    _write(repo, "AGENTS.md", "Never push to main.\nAlways ask before deleting.\nPlain" + chr(0x200B) + " line.\n")
    _write(repo, ".mcp.json", json.dumps({"mcpServers": {
        "files": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]},
        "pinned": {"command": "npx", "args": ["some-server@1.2.3"]},
        "stripe": {"command": "node", "args": ["server.js", "--token", MARK + "shortarg"],
                   "env": {"STRIPE_API_KEY": MARK + "mcptoken123"}},
        "posargs": {"command": "node", "args": ["server.js", "tangerine-harbor-51"]},
        "scriptish": {"command": "node", "args": ["server.js", "fakeargv.py"]},
        "container": {"command": "docker", "args": ["run", "example/image:1", "user:fakeimage"]},
    }}))
    _write(repo, ".claude/settings.json", json.dumps({
        "permissions": {"defaultMode": "bypassPermissions",
                        "allow": ["Bash", "Read", "Bash(curl -H x-api-key=orchidheader4 https://example.com)"],
                        "deny": ["Bash(echo plumcanary9 > out.txt)", "Bash(git push --force *)"]},
        "hooks": {"SessionStart": [{"hooks": [
            {"type": "command",
             "command": f'curl -H "Authorization: Bearer {MARK}bearer99" https://example.com/hook'},
            {"type": "command",
             "command": 'mysql -u root -pwinterblue7 -h db.internal.example.com -e "select 1"'}]}]},
    }))
    _write(repo, ".github/workflows/agent.yml",
           "name: agent\non:\n  issue_comment:\n    types: [created]\npermissions:\n  contents: write\n"
           "jobs:\n  run:\n    runs-on: ubuntu-latest\n    steps:\n"
           "      - uses: anthropics/claude-code-action@v1\n        with:\n"
           "          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}\n"
           "          prompt: ${{ github.event.comment.body }}\n")
    _write(repo, "tests/setup.py",
           'import os, shutil\nos.environ["HOME"] = "/tmp/x"\nshutil.rmtree(target)\nSQL = "DROP TABLE users"\n')
    _write(repo, "pay.py", "stripe.transfers.create(amount=100)\n")
    _write(repo, "web/package.json", json.dumps({"name": "web", "scripts": {"postinstall": "node setup.js --key=orchardcanary3"}}))
    _write(repo, "docs/runbook.md", "Check it with `printenv DB_PASSWORD`.\nIf blocked: git commit --no-verify\n")
    _write(repo, "noisy.sh", "#!/bin/bash\nset -euo pipefail\n" + "rm -rf build\n" * 9)
    _write(repo, "id_rsa", _private_key())
    _write(repo, "empty.txt", "")
    _write(repo, ".notes.txt.icloud", "placeholder")
    (repo / "link-out").symlink_to(outside)
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["remote", "add", "origin",
                          f"https://x-access-token:{MARK}remote@github.com/acme/widgets.git"], check=True)


def _build_home(home: Path) -> None:
    _write(home, ".aws/credentials", f"[default]\naws_access_key_id = REPLACE_ME\naws_secret_access_key = {AWS_SECRET}\n")
    _write(home, ".aws/config", "[profile prod-admin]\nregion = us-east-1\nrole_arn = REPLACE_ME\n\n[profile lilaccanary6!]\nregion = x\n")
    _write(home, ".kube/config",
           "apiVersion: v1\ncurrent-context: prod-cluster\ncontexts:\n- context:\n    cluster: a\n  name: prod-cluster\n"
           f"- context:\n    cluster: b\n  name: dev\n- context:\n    cluster: c\n  name: ctx;$(maplecanary2)\nusers:\n- name: admin\n  user:\n    token: {MARK}kubetoken\n")
    _write(home, ".netrc", f"machine api.example.com login me password {MARK}netrcpw\n"
                           'machine two.example.com login me password "before machine fakequoted after"\n')
    _write(home, ".pgpass", f"prod-db.example.com:5432:app:admin:{MARK}pgpw\n")
    _write(home, ".npmrc", f"//registry.npmjs.org/:_authToken={NPM_TOKEN}\n")
    _write(home, ".config/gh/hosts.yml", f"github.com:\n    oauth_token: {GH_TOKEN}\n    user: someone\n")
    _write(home, ".zshrc", "alias rm='rm -i'\nalias cc='claude --dangerously-skip-permissions'\n"
           "alias deploy='DEPLOY_PASS=quartzcanary8 ./deploy.sh --yolo'\n")
    _write(home, ".codex/config.toml",
           'approval_policy = "never"\n\n[mcp_servers.docs]\ncommand = "npx"\nargs = ["-y", "docs-mcp@latest"]\n\n'
           f'[mcp_servers.docs.env]\nDOCS_TOKEN = "{MARK}codextoken"\n')
    _write(home, ".claude.json", json.dumps({"mcpServers": {
        "remote": {"type": "http", "url": f"https://mcp.example.com/v1/{MARK}pathkey?key={MARK}query"}}}))
    _write(home, ".claude/skills/demo/SKILL.md", "---\nname: demo\ndescription: demo\n---\n")


def _tree(base: Path) -> list:
    rows = []
    for path in sorted(base.rglob("*")):
        if ".git" in path.parts:
            continue
        info = path.lstat()
        rows.append((path.relative_to(base).as_posix(), info.st_size, info.st_mtime_ns))
    return rows


class CollectorFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_collector()
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name).resolve()
        cls.repo, cls.home, outside = base / "repo", base / "home", base / "outside"
        for directory in (cls.repo, cls.home, outside):
            directory.mkdir()
        _build_repo(cls.repo, outside)
        _build_home(cls.home)
        cls.environ = {
            "PATH": os.environ.get("PATH", ""),
            "STRIPE_SECRET_KEY": LIVE_KEY,
            "DATABASE_URL": f"postgres://admin:{PASSWORD}@prod-db.example.com:5432/main",
            "AWS_PROFILE": "prod-admin",
            "MY_SERVICE_TOKEN": MARK + "envtoken",
            "EDITOR": "vim",
            "APP_ENV": "staging",
            "ENVIRONMENT": "Zq7pR2mX9vL4kT8wB1nC5hJ3",
            "ODD-NAME$(x)": "y",
        }
        cls.before = _tree(base)
        cls.collector = cls.mod.Collector(cls.repo, cls.home, cls.environ, system_paths=False)
        cls.collector.run()
        cls.after = _tree(base)
        cls.text = cls.collector.render()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def leads(self, check: int, kind: str) -> list:
        return [f"{i['loc']} | {i['note']}" for i in self.collector.items if i["check"] == check and i["kind"] == kind]

    def assertLead(self, check: int, kind: str, *needles: str) -> None:
        rows = self.leads(check, kind)
        self.assertTrue(any(all(n in row for n in needles) for row in rows),
                        f"no ({check}, {kind}) lead containing {needles}; got {rows}")

    def test_no_planted_secret_reaches_the_output(self) -> None:
        self.assertNotIn(MARK, self.text)
        self.assertNotIn(MARK, json.dumps(self.collector.items))
        self.assertNotIn(MARK, json.dumps(self.collector.notes))
        everything = self.text + json.dumps([self.collector.items, self.collector.notes, self.collector.coverage])
        for canary in CANARIES:
            self.assertNotIn(canary, everything, canary)

    def test_command_line_output_is_clean_on_both_streams(self) -> None:
        script = Path(self.mod.__file__)
        for extra in ([], ["--json"]):
            done = subprocess.run([sys.executable, str(script), "--repo", str(self.repo), "--home", str(self.home)] + extra,
                                  env=self.environ, capture_output=True, text=True, check=True)
            self.assertEqual(done.stderr, "")
            for needle in [MARK] + CANARIES:
                self.assertNotIn(needle, done.stdout, f"{needle} with {extra}")
            if extra:
                self.assertEqual(sorted(json.loads(done.stdout)), ["examined", "leads", "notes"])

    def test_only_git_is_ever_started(self) -> None:
        started = []
        real = self.mod.subprocess.run

        def recording(cmd, *args, **kwargs):
            started.append(cmd[0])
            return real(cmd, *args, **kwargs)

        self.mod.subprocess.run = recording
        try:
            self.mod.Collector(self.repo, self.home, self.environ, system_paths=False).run()
        finally:
            self.mod.subprocess.run = real
        self.assertEqual(set(started), {"git"})

    def test_nothing_changes_on_disk_git_directory_included(self) -> None:
        def digest() -> dict:
            base = Path(self.tmp.name).resolve()
            return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(base.rglob("*")) if p.is_file() and not p.is_symlink()}

        before = digest()
        self.mod.Collector(self.repo, self.home, self.environ, system_paths=False).run()
        self.assertEqual(before, digest())

    def test_no_environment_value_is_echoed_outside_the_selector_list(self) -> None:
        everything = self.text + json.dumps([self.collector.items, self.collector.notes, self.collector.coverage])
        for name, value in self.environ.items():
            if name in self.mod.SELECTORS or name == "PATH" or len(value) < 6:
                continue
            self.assertNotIn(value, everything, f"value of {name}")

    def test_state_and_variable_files_are_not_pattern_scanned(self) -> None:
        self.assertNotIn("statefile.example.com", self.text)

    def test_selector_values_are_the_only_values_shown(self) -> None:
        self.assertLead(2, "context-selector", "env:APP_ENV", "= staging")
        self.assertLead(2, "context-selector", "env:ENVIRONMENT", "value withheld")
        self.assertLead(2, "env-var", "env |", "1 variables with unusual names not listed")

    def test_no_collector_step_failed(self) -> None:
        self.assertEqual([n for n in self.collector.notes if "failed" in n], [])

    def test_collector_writes_nothing(self) -> None:
        self.assertEqual(self.before, self.after)

    def test_check_1_database_targets(self) -> None:
        self.assertLead(1, "db-target", ".env.test:1", "prod-db.example.com:5432/app", "[non-local]", "role: test")
        self.assertLead(1, "db-target", ".env.example:1", "[local]")
        self.assertLead(1, "db-target", "docker-compose.yml:6", "<unparseable>")
        self.assertLead(1, "db-target", "env:DATABASE_URL", "[non-local]")
        self.assertLead(1, "destructive-db-op", "tests/setup.py:4")

    def test_check_2_credentials(self) -> None:
        self.assertLead(2, "live-payment-key", ".env.test:2", "STRIPE_SECRET_KEY")
        self.assertLead(2, "env-file", ".env.test", "tracked in git", "STRIPE_SECRET_KEY@2")
        self.assertLead(2, "env-file", ".env |", "untracked, ignored")
        self.assertLead(2, "tracked-sensitive-file", "id_rsa", "private key header")
        self.assertLead(2, "credential-in-remote-url", ".git/config")
        self.assertLead(2, "env-var", "env:STRIPE_SECRET_KEY", "live payment secret key")
        self.assertLead(2, "env-var", "env:MY_SERVICE_TOKEN")
        self.assertEqual(self.leads(2, "env-var").count("env:EDITOR | set"), 0)
        self.assertLead(2, "context-selector", "env:AWS_PROFILE", "prod-admin", "PROD-LIKE")
        self.assertLead(2, "credential-file", "~/.aws/credentials", "STATIC LONG-LIVED KEY")
        self.assertLead(2, "default-context", "kubectl current-context: prod-cluster", "PROD-LIKE")
        self.assertLead(2, "credential-file", "~/.kube/config", "STATIC CREDENTIAL")
        self.assertLead(2, "credential-file", "~/.netrc", "logins for: api.example.com, two.example.com")
        self.assertLead(2, "env-file", ".env |", "untracked, ignored", "3 keys", "API_TOKEN@1, PRIVATE_KEY@2")
        self.assertLead(2, "credential-file", "~/.pgpass", "prod-db.example.com:5432/app")
        self.assertLead(2, "credential-file", "~/.npmrc", "LITERAL in file")
        self.assertLead(2, "credential-file", "~/.config/gh/hosts.yml", "PLAINTEXT")

    def test_check_3_deletes(self) -> None:
        self.assertLead(3, "recursive-delete", "scripts/clean.sh:2", "VARIABLE TARGET, no :? guard", "glob")
        self.assertLead(3, "recursive-delete", "scripts/clean.sh:3", "guarded with :?")
        self.assertLead(3, "shell-without-nounset", "scripts/clean.sh:1", "CONTAINS A RECURSIVE DELETE")
        self.assertFalse(any("safe.sh" in row for row in self.leads(3, "shell-without-nounset")))
        self.assertLead(3, "symlink", "link-out", "OUTSIDE REPO")
        self.assertLead(3, "changes-home", "tests/setup.py:2")
        self.assertLead(3, "recursive-delete-call", "tests/setup.py:3")

    def test_check_4_infrastructure(self) -> None:
        self.assertLead(4, "unprotected-data-resource", "infra/main.tf:1", "aws_db_instance.main", "skip_final_snapshot")
        self.assertFalse(any("aws_s3_bucket.ok" in row for row in self.leads(4, "unprotected-data-resource")))
        self.assertLead(4, "tfstate-file", "infra/terraform.tfstate", "tracked in git")
        self.assertLead(4, "auto-approve-flag", "scripts/deploy.sh:3")
        self.assertLead(4, "force-flag", "scripts/deploy.sh:4")
        self.assertLead(4, "local-terraform-state", "infra/main.tf")

    def test_check_5_rules_and_enforcement(self) -> None:
        self.assertLead(5, "rule-file", "AGENTS.md", "2 imperative lines at lines 1, 2")

    def test_check_6_makes_no_network_call_by_default(self) -> None:
        self.assertLead(6, "not-checked", "acme/widgets", "GitHub was not queried")

    def test_check_7_placeholders(self) -> None:
        self.assertLead(7, "zero-byte-file", "empty.txt")
        self.assertLead(7, "cloud-placeholder", ".notes.txt.icloud")
        self.assertLead(7, "synced-folder", "not under a known sync root")

    def test_check_8_agent_config(self) -> None:
        self.assertLead(8, "mcp-server", ".mcp.json", "files:", "UNPINNED", "package has no version")
        pinned = [row for row in self.leads(8, "mcp-server") if "pinned:" in row]
        self.assertTrue(pinned and "UNPINNED" not in pinned[0])
        self.assertLead(8, "mcp-server", ".mcp.json", "stripe:", "LITERAL SECRET stored in config for: STRIPE_API_KEY")
        self.assertLead(8, "mcp-server", "~/.codex/config.toml", "docs:", "latest tag", "env: DOCS_TOKEN")
        self.assertLead(8, "mcp-server", "~/.claude.json", "remote: https://mcp.example.com")
        self.assertLead(8, "hook", ".claude/settings.json", "SessionStart", "runs curl", "arguments not shown")
        self.assertLead(8, "hook", ".claude/settings.json", "SessionStart", "runs mysql", "arguments not shown")
        self.assertLead(8, "mcp-server", ".mcp.json", "posargs:", "runs node server.js (+1 arguments not shown)")
        self.assertLead(8, "mcp-server", ".mcp.json", "scriptish:", "runs node server.js (+1 arguments not shown)")
        self.assertLead(8, "mcp-server", ".mcp.json", "container:", "runs docker (+3 arguments not shown)")
        self.assertLead(8, "install-script", "web/package.json", "postinstall: runs node setup.js")
        self.assertLead(8, "hidden-unicode", "AGENTS.md:3:6", "U+200B")
        self.assertLead(8, "skills", "~/.claude/skills", "demo")

    def test_check_9_ci(self) -> None:
        self.assertLead(9, "agent-on-untrusted-trigger", ".github/workflows/agent.yml", "issue_comment",
                        "WITH SECRETS", "contents@6")
        self.assertLead(9, "workflow", "untrusted event text interpolated", "ANTHROPIC_API_KEY")

    def test_check_10_modes_and_safety_nets(self) -> None:
        self.assertLead(10, "agent-mode", ".claude/settings.json", "defaultMode: bypassPermissions", "BROAD ALLOW: Bash")
        self.assertLead(10, "bypass-in-shell-rc", "~/.zshrc:2", "alias cc")
        self.assertLead(10, "bypass-in-shell-rc", "~/.zshrc:3", "alias deploy")
        self.assertLead(10, "shell-safety-net", "~/.zshrc:1", "named rm", "INTERACTIVE shells only")
        self.assertLead(10, "agent-setting", "~/.codex/config.toml:1", "approval_policy = never")
        self.assertLead(5, "enforcement", ".claude/settings.json", "deny rules: 2",
                        "Bash(echo ...)", "Bash(git push --force *)")
        self.assertLead(10, "agent-mode", ".claude/settings.json", "BROAD ALLOW: Bash; Bash(curl -H ...)")

    def test_check_11_money_and_messages(self) -> None:
        self.assertLead(11, "moves-money", "pay.py:1")
        self.assertLead(11, "mcp-server-can-send", ".mcp.json", "stripe")

    def test_feedback_leads(self) -> None:
        self.assertLead(2, "gitignore-coverage", ".gitignore", ".env: ignored", "key.pem: NOT IGNORED")
        self.assertLead(2, "instruction-prints-secret", "docs/runbook.md:1", "(doc)")
        self.assertLead(5, "skips-a-control", "docs/runbook.md:2")
        self.assertLead(8, "no-lockfile", "web/package.json")
        self.assertLead(8, "install-script", "web/package.json", "postinstall")

    def test_one_noisy_file_is_capped_and_counted(self) -> None:
        rows = [row for row in self.leads(3, "recursive-delete") if row.startswith("noisy.sh:")]
        self.assertEqual(len(rows), self.mod.MAX_PER_FILE)
        self.assertIn("noisy.sh | recursive-delete | ... 4 more in this file not shown", self.text)

    def test_every_check_states_what_it_examined(self) -> None:
        for check in (1, 2, 3, 4, 5, 7, 8, 9, 10, 11):
            self.assertTrue(self.collector.coverage.get(check), f"check {check} reports no coverage")
        self.assertIn("examined: ", self.text)

    def test_the_skill_directory_is_not_exempt(self) -> None:
        skill = Path(self.mod.__file__).resolve().parent.parent
        repo_root = skill.parents[4]
        collector = self.mod.Collector(repo_root, self.home, {"PATH": os.environ.get("PATH", "")},
                                       only={8}, system_paths=False)
        scanned = [name for name in collector.files() if name.endswith("blast-radius-audit/SKILL.md")]
        self.assertEqual(len(scanned), 1)
        collector.run()
        hidden = [i for i in collector.items if i["kind"] == "hidden-unicode" and "blast-radius-audit" in i["loc"]]
        self.assertEqual(hidden, [], "the skill's own files must not contain hidden Unicode")

    def test_only_filter_limits_sections(self) -> None:
        collector = self.mod.Collector(self.repo, self.home, self.environ, only={3}, system_paths=False)
        collector.run()
        self.assertEqual({item["check"] for item in collector.items}, {3})
        self.assertNotIn("## 1.", collector.render())

    def test_only_filter_does_not_run_out_of_scope_steps(self) -> None:
        collector = self.mod.Collector(self.repo, self.home, self.environ, only={6}, system_paths=False)
        collector.run()
        self.assertEqual(collector.steps_run, ["github_checks"])
        self.assertLessEqual(set(collector.coverage), {6})


class TargetedFixtureTests(unittest.TestCase):
    """One small fixture per lead a reviewer showed to be wrong."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_collector()

    def collect(self, files: dict, environ: dict | None = None, only: set | None = None, prepare=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        repo, home = base / "repo", base / "home"
        repo.mkdir()
        home.mkdir()
        for rel, text in files.items():
            _write(repo, rel, text)
        if prepare:
            prepare(repo, home)
        env = {"PATH": os.environ.get("PATH", "")}
        env.update({k: v.replace("{home}", str(home)) for k, v in (environ or {}).items()})
        collector = self.mod.Collector(repo, home, env, only=only, system_paths=False)
        collector.run()
        self.assertEqual([n for n in collector.notes if "failed" in n], [])
        return collector

    @staticmethod
    def rows(collector, kind: str) -> list:
        return [f"{i['loc']} | {i['note']}" for i in collector.items if i["kind"] == kind]

    def test_netrc_is_read_by_token_position(self) -> None:
        machines = self.mod.netrc_machines
        self.assertEqual(machines('machine a.example.com login x password "p machine fakequoted q"\ndefault login y password z\n'),
                         ["a.example.com"])
        self.assertEqual(machines('machine a.example.com password z\nmacdef sample\necho "unbalanced shell text\n\n'),
                         ["a.example.com"])
        self.assertIsNone(machines('machine a.example.com password "unterminated\n'))

    def test_dotenv_continuation_lines_are_not_keys(self) -> None:
        text = 'A=1\nKEY="-----BEGIN-----\ncedarline5=\nbirchvalue6=x\n-----END-----"\nB=2\n'
        self.assertEqual([(line, key) for line, key, _ in self.mod.env_assignments(text)], [(1, "A"), (2, "KEY"), (6, "B")])

    def test_keys_mode_prints_names_and_never_values(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        _write(base, "a.env", f'A={MARK}one\nKEY="x\ncedarline5=\n{MARK}two"\nB={MARK}three\n')
        _write(base, "c.json", json.dumps({"mcpServers": {"x": {"env": {"API_KEY": MARK + "four"}, "args": [MARK + "five"]}}}))
        _write(base, "d.toml", f'[mcp_servers.docs]\ncommand = "npx"\n\n[mcp_servers.docs.env]\nTOKEN = "{MARK}six"\n'
                               'prompt = """\nFAKE_KEY_CANARY=inline\n[mcp_servers.tomlcanary]\n"""\n')
        _write(base, "key.pem", "-----BEGIN FAKE-----\nFAKEPEMBODY=\n-----END FAKE-----\n")
        _write(base, ".envrc", "cat <<EOT\nENVRC_CANARY=privatebody\nEOT\n")
        _write(base, "outside.env", "FAKE_OUTSIDE_KEY=1\n")
        (base / "repo").mkdir()
        (base / "repo" / "linked.env").symlink_to(base / "outside.env")
        script = Path(self.mod.__file__)
        for name, wanted in (("a.env", ["1: A", "2: KEY (multi-line value)", "5: B"]),
                             ("c.json", ["mcpServers.x.env.API_KEY (str)", "mcpServers.x.args[0] (str)"]),
                             ("d.toml", ["[mcp_servers.docs] command", "[mcp_servers.docs.env] TOKEN, prompt"])):
            done = subprocess.run([sys.executable, str(script), "--keys", str(base / name)],
                                  capture_output=True, text=True, check=True, env={"PATH": os.environ.get("PATH", "")})
            self.assertNotIn(MARK, done.stdout + done.stderr)
            self.assertNotIn("cedarline5", done.stdout)
            self.assertEqual(done.stdout.splitlines(), wanted)
        for name in ("key.pem", ".envrc", "repo/linked.env"):
            done = subprocess.run([sys.executable, str(script), "--repo", str(base / "repo"), "--keys", str(base / name)],
                                  capture_output=True, text=True, check=True, env={"PATH": os.environ.get("PATH", "")})
            for leaked in ("FAKEPEMBODY", "ENVRC_CANARY", "FAKE_OUTSIDE_KEY"):
                self.assertNotIn(leaked, done.stdout, name)
            self.assertEqual(len(done.stdout.splitlines()), 1, name)

    def test_toml_multiline_strings_are_values_not_tables(self) -> None:
        tables = self.mod.parse_toml_tables('prompt = """\n[mcp_servers.tomlcanary]\ncommand = "fakesecretprogram"\n"""\n'
                                            '[mcp_servers.real]\ncommand = "npx"\n')
        self.assertEqual(sorted(tables), ["", "mcp_servers.real"])
        got = self.collect({".codex/config.toml": 'prompt = """\n[mcp_servers.tomlcanary]\ncommand = "fakesecretprogram"\n"""\n'},
                           only={8})
        self.assertNotIn("tomlcanary", json.dumps(got.items))

    def test_a_linked_skills_directory_is_not_enumerated(self) -> None:
        def prepare(repo, home):
            _write(home, "elsewhere/only-outside-canary/SKILL.md", "---\nname: x\ndescription: x\n---\n")
            (repo / ".claude").mkdir()
            (repo / ".claude" / "skills").symlink_to(home / "elsewhere")

        got = self.collect({"a.txt": "x\n"}, only={8}, prepare=prepare)
        self.assertNotIn("only-outside-canary", json.dumps(got.items))
        self.assertTrue(any("NOT INSPECTED" in row for row in self.rows(got, "skills")))

    def test_state_and_variable_files_are_never_opened_by_any_scanner(self) -> None:
        got = self.collect({".claude/rules/current.tfvars": 'x = "do not read' + chr(0x202E) + '"\n'})
        self.assertNotIn("current.tfvars", json.dumps([i for i in got.items if i["kind"] in ("hidden-unicode", "rule-file")]))

    def test_flag_emoji_tags_are_not_hidden_text(self) -> None:
        scotland = chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in "gbsct") + chr(0xE007F)
        self.assertEqual(self.mod.hidden_columns("flag " + scotland + " ok"), [])
        self.assertEqual([code for _, code in self.mod.hidden_columns("x" + chr(0xE0041) + "y")], [0xE0041])

    def test_git_child_environment_is_fixed(self) -> None:
        seen = []
        real = self.mod.subprocess.run

        def recording(cmd, *args, **kwargs):
            seen.append((cmd[0], dict(kwargs.get("env") or {})))
            return real(cmd, *args, **kwargs)

        self.mod.subprocess.run = recording
        try:
            self.collect({"a.txt": "x\n"}, {"GIT_DIR": "/nonexistent", "GIT_TRACE": "1", "SOME_TOKEN": MARK}, only={5})
        finally:
            self.mod.subprocess.run = real
        self.assertTrue(seen)
        for program, env in seen:
            self.assertEqual(program, "git")
            self.assertEqual(env.get("GIT_NO_LAZY_FETCH"), "1")
            self.assertEqual(env.get("GIT_TRACE"), "0")
            self.assertEqual(env.get("GIT_TRACE2_EVENT"), "0")
            self.assertNotIn("GIT_DIR", env)
            self.assertNotIn("SOME_TOKEN", env)

    def test_rule_head_stops_at_the_first_word_that_is_not_a_command_word(self) -> None:
        head = self.mod.rule_head
        self.assertEqual(head("Bash(git push --force *)"), "Bash(git push --force *)")
        self.assertEqual(head("Bash(rm -rf:*)"), "Bash(rm -rf *)")
        self.assertEqual(head("Bash(curl fake-deny-value)"), "Bash(curl ...)")
        # A word after a flag may be the flag's value; a bare word after an unknown program may be anything.
        self.assertEqual(head("Bash(wget --password orchidcanary https://example.invalid)"), "Bash(wget --password ...)")
        self.assertEqual(head("Bash(curl --pass winterleaf https://example.invalid)"), "Bash(curl --pass ...)")
        self.assertEqual(head("Bash(mysqladmin password winterleaf)"), "Bash(mysqladmin ...)")
        self.assertEqual(head("Bash(gh secret set DEPLOY_KEY --body winterleaf)"), "Bash(gh secret set ...)")
        self.assertEqual(head("Bash(terraform destroy *)"), "Bash(terraform destroy *)")
        self.assertEqual(head("Bash(git push --force winterleaf)"), "Bash(git push --force ...)")
        # Assembled at runtime: written out, it reads as a real header to the repo's secret scanner.
        header = "Authorization" + ": " + "Bearer " + "orchidheader4"
        self.assertEqual(head(f'Bash(curl -H "{header}" https://x)'), "Bash(curl -H ...)")
        self.assertEqual(head("Read(./.env)"), "Read(./.env)")
        self.assertEqual(head("Read(//etc/orchidheader4 secret)"), "Read(...)")
        self.assertEqual(head("mcp__claude_ai_Gmail*__send_message"), "mcp__claude_ai_Gmail*__send_message")

    def test_config_reached_through_a_link_out_of_the_repo_is_not_read(self) -> None:
        def prepare(repo, home):
            _write(home, "shared.json", json.dumps({"apiKeyHelper": "demo fakeoutside.py",
                                                    "permissions": {"deny": ["Bash(curl fakeoutside)"]}}))
            (repo / ".claude").mkdir()
            (repo / ".claude" / "settings.json").symlink_to(home / "shared.json")

        got = self.collect({"a.txt": "x\n"}, prepare=prepare)
        self.assertNotIn("fakeoutside", json.dumps(got.items))
        self.assertTrue(any(".claude/settings.json" in row and "NOT INSPECTED" in row
                            for row in self.rows(got, "config-not-parsed")))

    def test_git_does_not_write_a_trace_file(self) -> None:
        def prepare(repo, home):
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        trace = Path(tmp.name) / "trace.json"
        self.collect({"a.txt": "x\n"}, {"GIT_TRACE2_EVENT": str(trace), "GIT_TRACE": str(trace)}, prepare=prepare)
        self.assertFalse(trace.exists())

    def test_write_is_read_only_inside_a_permissions_mapping(self) -> None:
        got = self.collect({".github/workflows/a.yml":
                            'on: push\npermissions: {"contents": write}\njobs:\n  a:\n    runs-on: x\n'
                            "    env:\n      fakeenvkey: write\n    steps:\n      - run: true\n",
                            ".github/workflows/b.yml":
                            "on: push\njobs:\n  b:\n    permissions:\n      'pull-requests': write\n"
                            "      contents: read\n    env:\n      mode: write\n    steps:\n      - run: true\n"},
                           only={9})
        rows = self.rows(got, "workflow")
        self.assertTrue(any("a.yml" in row and "WRITE PERMISSIONS: contents@2;" in row for row in rows))
        self.assertTrue(any("b.yml" in row and "WRITE PERMISSIONS: pull-requests@5;" in row for row in rows))
        self.assertFalse(any("fakeenvkey" in row or "mode@" in row for row in rows))
        got = self.collect({".github/workflows/c.yml":
                            "on: push\npermissions:\n  contents: read\njobs:\n  c:\n    runs-on: x\n    steps:\n"
                            "      - run: |\n          cat <<EOT\n          permissions:\n            shellcanary: write\n"
                            "          EOT\n"}, only={9})
        self.assertTrue(any("permissions block present, no write found" in row for row in self.rows(got, "workflow")))

    def test_terraform_protection_must_be_in_the_right_place(self) -> None:
        got = self.collect({"main.tf":
                            'terraform {\n  backend "local" {}\n}\n'
                            'resource "aws_db_instance" "tagged" {\n  tags = {\n    prevent_destroy = true\n'
                            '    deletion_protection = true\n  }\n}\n'
                            'resource "aws_db_instance" "guarded" {\n  deletion_protection = true\n}\n'
                            'resource "aws_s3_bucket" "kept" {\n  lifecycle { prevent_destroy = true }\n}\n'},
                           only={4})
        rows = self.rows(got, "unprotected-data-resource")
        self.assertTrue(any("aws_db_instance.tagged" in row for row in rows))
        self.assertFalse(any("guarded" in row or "kept" in row for row in rows))
        got = self.collect({"main.tf": 'resource "aws_s3_bucket" "said" {\n  lifecycle {\n    precondition {\n'
                                       '      condition     = true\n      error_message = "prevent_destroy = true"\n'
                                       "    }\n  }\n}\n"}, only={4})
        self.assertTrue(any("aws_s3_bucket.said" in row for row in self.rows(got, "unprotected-data-resource")))
        self.assertTrue(self.rows(got, "local-terraform-state"))

    def test_relative_kubeconfig_is_flagged_not_skipped(self) -> None:
        got = self.collect({}, {"KUBECONFIG": "kube.yaml"}, only={2})
        self.assertTrue(any("env:KUBECONFIG" in row and "NOT INSPECTED" in row for row in self.rows(got, "credential-file")))

    def test_only_an_exact_github_host_is_github(self) -> None:
        slug = self.mod.github_slug
        self.assertEqual(slug("https://github.com/acme/demo.git"), ("acme", "demo"))
        self.assertEqual(slug("git@github.com:acme/demo.git"), ("acme", "demo"))
        self.assertEqual(slug("ssh://git@github.com/acme/demo"), ("acme", "demo"))
        self.assertEqual(slug("https://user:pw@github.com/acme/demo"), ("acme", "demo"))
        self.assertEqual(slug("ssh://git@github.com:443/acme/demo.git"), ("acme", "demo"))
        for other in ("https://notgithub.com/acme/demo.git", "https://github.com.evil.example/acme/demo",
                      "https://example.com/github.com/acme/demo", "git@notgithub.com:acme/demo.git",
                      "https://github.com:443/demo", "https://github.com/acme/demo/extra"):
            self.assertIsNone(slug(other), other)

    def test_a_newline_in_a_path_cannot_forge_a_second_row(self) -> None:
        got = self.collect({"a.txt": "x\n", "double  space.txt": ""}, {"BASH_ENV": "{home}/rc\n- forged | lead | row"},
                           only={7, 10})
        self.assertTrue(all("\n" not in line for lines in got.coverage.values() for line in lines))
        self.assertTrue(all("\n" not in item["loc"] + item["note"] for item in got.items))
        self.assertTrue(any(item["loc"] == "double  space.txt" for item in got.items))  # spaces are evidence; keep them
        self.assertEqual(self.mod.one_line("a\nb\x1b[0m c"), "a\\x0ab\\x1b[0m c")

    def test_host_list_is_as_remote_as_its_most_remote_member(self) -> None:
        self.assertEqual(self.mod.classify_host("localhost,db.example.com"), "non-local")
        self.assertEqual(self.mod.sanitize_db_url("mongodb://localhost,db.example.com/app"),
                         ("mongodb://localhost,db.example.com/app", "non-local"))
        self.assertEqual(self.mod.sanitize_db_url("mongodb://a.example.com:27017,b.example.com:27017/app")[1], "non-local")
        got = self.collect({".env.example": "DATABASE_URL=mongodb://localhost,db.example.com/app\n"}, only={1})
        self.assertTrue(any("[non-local]" in row for row in self.rows(got, "db-target")))

    def test_terraform_comment_is_not_protection_and_backends_are_per_directory(self) -> None:
        got = self.collect({
            "infra/service/main.tf": 'resource "aws_s3_bucket" "data" {\n  bucket = "example"\n  # prevent_destroy = true\n}\n',
            "infra/other/main.tf": 'terraform {\n  backend "s3" {}\n}\n',
        }, only={4})
        self.assertTrue(any("infra/service/main.tf:1" in row and "aws_s3_bucket.data" in row
                            for row in self.rows(got, "unprotected-data-resource")))
        state = self.rows(got, "local-terraform-state")
        self.assertTrue(any("infra/service" in row for row in state))
        self.assertFalse(any("infra/other/" in row for row in state))

    def test_inline_workflow_permissions_and_pull_request_agents(self) -> None:
        got = self.collect({".github/workflows/qa.yml":
                            "on: pull_request\npermissions: {contents: write}\njobs:\n  qa:\n"
                            "    runs-on: ubuntu-latest\n    steps:\n      - run: codex exec review\n"}, only={9})
        self.assertTrue(any("WRITE PERMISSIONS: contents@2" in row for row in self.rows(got, "workflow")))
        self.assertTrue(any("WRITE PERMISSIONS" in row for row in self.rows(got, "agent-on-pull-request")))

    def test_aws_files_named_by_the_environment_are_inspected(self) -> None:
        def prepare(repo, home):
            _write(home, "alternate-aws", f"[default]\naws_access_key_id = REPLACE_ME\naws_secret_access_key = {MARK}x\n")

        got = self.collect({}, {"AWS_SHARED_CREDENTIALS_FILE": "{home}/alternate-aws",
                                "AWS_CONFIG_FILE": "{home}/absent"}, only={2}, prepare=prepare)
        rows = self.rows(got, "credential-file")
        self.assertTrue(any("alternate-aws" in row and "STATIC LONG-LIVED KEY" in row for row in rows))
        self.assertTrue(any("env:AWS_CONFIG_FILE" in row and "NOT INSPECTED" in row for row in rows))
        self.assertNotIn(MARK, json.dumps(got.items))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs mkfifo")
    def test_fifo_is_not_read_and_not_called_an_empty_file(self) -> None:
        got = self.collect({"a.txt": "x\n"}, prepare=lambda repo, home: os.mkfifo(repo / "queue"))
        self.assertEqual(self.rows(got, "zero-byte-file"), [])
        self.assertTrue(any("special files" in line for line in got.coverage[7]))

    def test_root_lockfile_covers_nested_packages_only_in_a_workspace(self) -> None:
        nested = {"package-lock.json": "{}", "examples/standalone/package.json": '{"name": "standalone"}'}
        got = self.collect(dict(nested, **{"package.json": '{"name": "root"}'}), only={8})
        self.assertTrue(any("examples/standalone/package.json" in row for row in self.rows(got, "no-lockfile")))
        got = self.collect(dict(nested, **{"package.json": '{"name": "root", "workspaces": ["examples/*"]}'}), only={8})
        self.assertFalse(any("examples/standalone" in row for row in self.rows(got, "no-lockfile")))
        got = self.collect(dict(nested, **{"package.json": '{"name": "root", "workspaces": ["packages/*"]}'}), only={8})
        self.assertTrue(any("examples/standalone" in row for row in self.rows(got, "no-lockfile")))
        deep = {"package-lock.json": "{}", "package.json": '{"name": "root", "workspaces": ["packages/*"]}',
                "packages/ui/package.json": '{"name": "ui"}', "packages/ui/examples/standalone/package.json": '{"name": "s"}'}
        rows = self.rows(self.collect(deep, only={8}), "no-lockfile")
        self.assertTrue(any("packages/ui/examples/standalone" in row for row in rows))
        self.assertFalse(any(row.startswith("packages/ui/package.json") for row in rows))

    def test_a_link_in_the_repo_is_not_followed(self) -> None:
        def prepare(repo, home):
            _write(home, "outside.txt", "postgres://u:pw@leak.example.com/app\n")
            (repo / "link.txt").symlink_to(home / "outside.txt")

        got = self.collect({"a.txt": "x\n"}, prepare=prepare)
        self.assertFalse(any("leak.example.com" in json.dumps(item) for item in got.items))

    def test_aliased_payment_call_is_a_lead(self) -> None:
        got = self.collect({"app.py": "from stripe import Transfer as BillingTransfer\nBillingTransfer.create(amount=100)\n"}, only={11})
        self.assertTrue(any(row.startswith("app.py:2") for row in self.rows(got, "moves-money")))

    def test_branch_verdict_keeps_missing_evidence_unknown(self) -> None:
        verdict = self.mod.branch_verdict
        open_to_admins = {"enforce_admins": {"enabled": False}}
        self.assertIn("CAN BYPASS", verdict(open_to_admins, [], ["admin"]))
        self.assertIn("applies to this token", verdict({"enforce_admins": {"enabled": True}}, [], ["admin"]))
        self.assertIn("NO PROTECTION", verdict("HTTP 404", [], ["admin"]))
        self.assertTrue(verdict("HTTP 404", [], ["push"]).startswith("UNKNOWN"))
        self.assertTrue(verdict("HTTP 403", "HTTP 403", ["admin"]).startswith("UNKNOWN"))
        self.assertIn("UNKNOWN", verdict("HTTP 404", [{"type": "pull_request"}], ["push"]))
        mixed = verdict(open_to_admins, [{"type": "pull_request"}], ["admin"])
        self.assertIn("UNKNOWN", mixed)
        self.assertNotIn("is accepted", mixed)
        self.assertIn("UNKNOWN", verdict(open_to_admins, "HTTP 403", ["admin"]))
        self.assertNotIn("NO PROTECTION", verdict("request failed", "request failed", []))

    def test_command_summary_shows_the_program_and_scripts_only(self) -> None:
        summary = self.mod.command_summary
        self.assertEqual(summary("mysql -u root -pwinterblue7 -h db"), "runs mysql (+5 arguments not shown)")
        self.assertEqual(summary("node server.js fakeargv.py"), "runs node server.js (+1 arguments not shown)")
        self.assertEqual(summary("docker run example/image:1 user:fakeimage"), "runs docker (+3 arguments not shown)")
        self.assertEqual(summary("npx -y @scope/server@1.2.3 --key fakeargv"), "runs npx @scope/server@1.2.3 (+3 arguments not shown)")
        self.assertEqual(summary("npx --userconfig npmrc-canary example-package"), "runs npx (+3 arguments not shown)")
        self.assertEqual(summary('bash "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"'),
                         "runs bash $CLAUDE_PROJECT_DIR/.claude/hooks/x.sh")
        self.assertEqual(summary("TOKEN=plumcanary9 ./run.sh --go"), "runs run.sh (+1 arguments not shown)")
        self.assertNotIn("quartz", summary(["node", "quartzcanary8"]))

    def test_safe_name_withholds_anything_that_is_not_a_plain_name(self) -> None:
        safe = self.mod.safe_name
        self.assertEqual(safe("prod-cluster"), "prod-cluster")
        self.assertEqual(safe("@scope/server@1.4.2"), "@scope/server@1.4.2")
        self.assertEqual(safe("ctx;$(maplecanary2)"), "<withheld>")
        self.assertEqual(safe("Zq7pR2mX9vL4kT8wB1nC5hJ3"), "<withheld>")


class StripHiddenUnicodeTests(unittest.TestCase):
    """The bundled fixer changes the hidden characters and nothing else."""

    def run_script(self, *args: str):
        script = Path(_load_collector().__file__).with_name("strip_hidden_unicode.py")
        return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                              env={"PATH": os.environ.get("PATH", "")}, cwd=self.tmp.name)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "rules.md"
        family = chr(0x1F468) + chr(0x200D) + chr(0x1F469)
        scotland = chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in "gbsct") + chr(0xE007F)
        self.content = (chr(0xFEFF) + "first" + chr(0x200B) + " line\r\n" + family + " " + scotland + " kept\r\n"
                        "bidi" + chr(0x202E) + "end\r\n").encode("utf-8")
        self.path.write_bytes(self.content)
        self.path.chmod(0o755)

    def test_listing_changes_nothing(self) -> None:
        done = self.run_script("rules.md")
        self.assertEqual(done.returncode, 0)
        self.assertIn(":1:7 U+200B ZERO WIDTH SPACE", done.stdout)
        self.assertIn(":3:5 U+202E RIGHT-TO-LEFT OVERRIDE", done.stdout)
        self.assertIn("2 hidden characters; nothing changed", done.stdout)
        self.assertEqual(self.path.read_bytes(), self.content)

    def test_apply_removes_only_the_listed_characters(self) -> None:
        inode = self.path.stat().st_ino
        done = self.run_script("rules.md", "--apply")
        self.assertEqual(done.returncode, 0)
        expected = self.content.replace(chr(0x200B).encode(), b"").replace(chr(0x202E).encode(), b"")
        self.assertEqual(self.path.read_bytes(), expected)  # BOM, emoji joiner, flag tags and CRLF all intact
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.path.stat().st_ino, inode)  # rewritten in place: metadata travels with the inode
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["rules.md"])

    def test_links_and_non_utf8_are_refused(self) -> None:
        base = Path(self.tmp.name)
        (base / "link.md").symlink_to(self.path)
        self.assertEqual(self.run_script("link.md", "--apply").returncode, 2)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "rule.md"
        target.write_bytes(self.content)
        (base / "linked-dir").symlink_to(outside.name)
        self.assertEqual(self.run_script("linked-dir/rule.md", "--apply").returncode, 2)
        self.assertEqual(self.run_script(str(target), "--apply").returncode, 2)  # outside the working directory
        self.assertEqual(target.read_bytes(), self.content)
        (base / "latin.txt").write_bytes(b"caf\xe9\n")
        self.assertEqual(self.run_script("latin.txt", "--apply").returncode, 2)
        self.assertEqual(self.path.read_bytes(), self.content)


class PureFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_collector()

    def test_redact_removes_values_and_keeps_references(self) -> None:
        redact = self.mod.redact
        cases = [
            f"export STRIPE_KEY={LIVE_KEY}",
            f'"password": "{MARK}pw"',
            f"Authorization: Bearer {MARK}tok",
            f"psql postgres://admin:{MARK}pw@db.example.com/app",
            f"blob {MARK}aB3dE5fG7hJ9kL1mN3pQ5rS7tU9v",
            f"api_key = {MARK}",
        ]
        for case in cases:
            self.assertNotIn(MARK, redact(case), case)
        self.assertEqual(redact("token: ${{ secrets.GH_TOKEN }}"), "token: ${{ secrets.GH_TOKEN }}")
        self.assertEqual(redact('rm -rf "$BUILD_DIR"/*'), 'rm -rf "$BUILD_DIR"/*')
        self.assertIn("plugins/brightops-ai-skills/skills/safety", redact("see plugins/brightops-ai-skills/skills/safety"))

    def test_classify_host(self) -> None:
        expect = {
            "localhost": "local", "127.0.0.1": "local", "::1": "local", "host.docker.internal": "local",
            "db": "service-name", "10.0.0.5": "private-network", "db.internal": "private-network",
            "prod-db.example.com": "non-local", "8.8.8.8": "non-local", "${DB_HOST}": "from-variable", "": "no-host",
        }
        for host, klass in expect.items():
            self.assertEqual(self.mod.classify_host(host), klass, host)

    def test_sanitize_db_url_never_echoes_credentials(self) -> None:
        sanitize = self.mod.sanitize_db_url
        self.assertEqual(sanitize(f"postgres://u:{MARK}@db.example.com:5432/app?sslmode=require"),
                         ("postgres://db.example.com:5432/app", "non-local"))
        for tricky in (f"postgres://u:{MARK}/x@h.example.com/app", f"mysql://u:12?{MARK}@h.example.com/app",
                       f"redis://u:{MARK}@a@h.example.com/0"):
            shown, _ = sanitize(tricky)
            self.assertNotIn(MARK, shown, tricky)
        self.assertEqual(sanitize("jdbc:postgresql://localhost:5432/dev")[1], "local")

    def test_unpinned_reasons(self) -> None:
        reasons = self.mod.unpinned_reasons
        self.assertTrue(reasons("npx", ["-y", "@scope/server"]))
        self.assertEqual(reasons("npx", ["@scope/server@1.4.2"]), [])
        self.assertTrue(reasons("uvx", ["some-mcp"]))
        self.assertEqual(reasons("uvx", ["some-mcp==0.3.1"]), [])
        self.assertTrue(reasons("docker", ["run", "-i", "ghcr.io/acme/server"]))
        self.assertEqual(reasons("docker", ["run", "-i", "ghcr.io/acme/server:1.2"]), [])
        self.assertEqual(reasons("node", ["server.js"]), [])

    def test_parse_toml_tables(self) -> None:
        tables = self.mod.parse_toml_tables(
            'approval_policy = "never"\n[mcp_servers.docs]\ncommand = "npx"\nargs = [\n  "-y",\n  "x@latest",\n]\n'
            '[mcp_servers.docs.env]\nTOKEN = "v"\n')
        self.assertEqual(tables[""]["approval_policy"], "never")
        self.assertEqual(tables["mcp_servers.docs"]["args"], ["-y", "x@latest"])
        self.assertIn("TOKEN", tables["mcp_servers.docs.env"])

    def test_hidden_codepoint_allows_emoji_joiner(self) -> None:
        hidden = self.mod.hidden_codepoint
        self.assertTrue(hidden(0x200B, ord("a")))
        self.assertTrue(hidden(0xE0041, ord("a")))
        self.assertTrue(hidden(0x202E, ord("a")))
        self.assertFalse(hidden(0x200D, 0x1F468))
        self.assertTrue(hidden(0x200D, ord("a")))

    def test_main_rejects_unknown_check_number(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.mod.main(["--only", "42"])
        self.assertEqual(raised.exception.code, 2)
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.mod.main(["--only", chr(0xB2)])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
