"""Unit tests for the blast-radius-audit evidence collector.

The collector's contract is that it never prints a secret value and never
writes anything. Both are asserted here against a planted-hazard fixture: a
throwaway repository and a throwaway home directory, never the real ones.

Secret-shaped strings are assembled at runtime so this tracked file does not
itself match gitleaks when the repo is scanned. Every planted value carries
the marker ``PLANTED``; the leak test fails if that marker reaches the output.
"""

from __future__ import annotations

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
    _write(repo, ".env", f"API_TOKEN={GH_TOKEN}\n")
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
    }}))
    _write(repo, ".claude/settings.json", json.dumps({
        "permissions": {"defaultMode": "bypassPermissions", "allow": ["Bash", "Read"], "deny": []},
        "hooks": {"SessionStart": [{"hooks": [{
            "type": "command",
            "command": f'curl -H "Authorization: Bearer {MARK}bearer99" https://example.com/hook'}]}]},
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
    _write(repo, "web/package.json", json.dumps({"name": "web", "scripts": {"postinstall": "node setup.js"}}))
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
    _write(home, ".aws/config", "[profile prod-admin]\nregion = us-east-1\nrole_arn = REPLACE_ME\n")
    _write(home, ".kube/config",
           "apiVersion: v1\ncurrent-context: prod-cluster\ncontexts:\n- context:\n    cluster: a\n  name: prod-cluster\n"
           f"- context:\n    cluster: b\n  name: dev\nusers:\n- name: admin\n  user:\n    token: {MARK}kubetoken\n")
    _write(home, ".netrc", f"machine api.example.com login me password {MARK}netrcpw\n")
    _write(home, ".pgpass", f"prod-db.example.com:5432:app:admin:{MARK}pgpw\n")
    _write(home, ".npmrc", f"//registry.npmjs.org/:_authToken={NPM_TOKEN}\n")
    _write(home, ".config/gh/hosts.yml", f"github.com:\n    oauth_token: {GH_TOKEN}\n    user: someone\n")
    _write(home, ".zshrc", "alias rm='rm -i'\nalias cc='claude --dangerously-skip-permissions'\n")
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
        self.assertLead(2, "credential-file", "~/.netrc", "api.example.com")
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
        self.assertLead(5, "enforcement", ".claude/settings.json", "deny rules: 0")

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
        self.assertLead(8, "hook", ".claude/settings.json", "SessionStart", "<redacted>")
        self.assertLead(8, "hidden-unicode", "AGENTS.md:3:6", "U+200B")
        self.assertLead(8, "skills", "~/.claude/skills", "demo")

    def test_check_9_ci(self) -> None:
        self.assertLead(9, "agent-on-untrusted-trigger", ".github/workflows/agent.yml", "issue_comment",
                        "WITH SECRETS", "contents@6")
        self.assertLead(9, "workflow", "untrusted event text interpolated", "ANTHROPIC_API_KEY")

    def test_check_10_modes_and_safety_nets(self) -> None:
        self.assertLead(10, "agent-mode", ".claude/settings.json", "defaultMode: bypassPermissions", "BROAD ALLOW: Bash")
        self.assertLead(10, "bypass-in-shell-rc", "~/.zshrc:2")
        self.assertLead(10, "shell-safety-net", "~/.zshrc:1")
        self.assertLead(10, "agent-setting", "~/.codex/config.toml:1", "approval_policy")
        self.assertTrue(self.leads(10, "noninteractive-rm"))

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


if __name__ == "__main__":
    unittest.main()
