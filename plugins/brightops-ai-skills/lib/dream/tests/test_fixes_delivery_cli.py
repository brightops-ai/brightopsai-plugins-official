"""Auto-fixes stay mechanical, delivery never guesses, the CLI stays a contract."""

import io
import json
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
from types import SimpleNamespace

from dream import cli, delivery, fixes, memory_audit, snapshot


class FixesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.memory = Path(self._tmp.name) / "memory"
        self.memory.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def index(self, text):
        (self.memory / "MEMORY.md").write_text(text, encoding="utf-8")

    def memo(self, name, description="a fact"):
        (self.memory / name).write_text(
            f"---\nname: {name[:-3]}\ndescription: {description}\n"
            f"metadata:\n  type: project\n---\n\nBody.\n",
            encoding="utf-8",
        )

    def read_index(self):
        return (self.memory / "MEMORY.md").read_text(encoding="utf-8")

    def test_dead_entry_is_removed(self):
        self.index("- [Gone](gone.md) — a\n- [Here](here.md) — b\n")
        self.memo("here.md")
        result = fixes.apply_safe_fixes(self.memory)
        self.assertTrue(any("dead index entry" in line for line in result.applied))
        self.assertNotIn("gone.md", self.read_index())
        self.assertIn("here.md", self.read_index())

    def test_unreachable_memory_is_linked_back_in(self):
        self.index("- [Here](here.md) — b\n")
        self.memo("here.md")
        self.memo("orphan.md", description="the orphan fact")
        result = fixes.apply_safe_fixes(self.memory)
        self.assertTrue(any("orphan.md" in line for line in result.applied))
        self.assertIn("orphan.md", self.read_index())
        self.assertIn("the orphan fact", self.read_index())

    def test_duplicate_entries_are_removed(self):
        self.index("- [Here](here.md) — b\n- [Here](here.md) — b\n")
        self.memo("here.md")
        result = fixes.apply_safe_fixes(self.memory)
        self.assertTrue(any("duplicate" in line for line in result.applied))
        self.assertEqual(self.read_index().count("here.md"), 1)

    def test_healthy_index_is_left_alone(self):
        self.index("- [Here](here.md) — b\n")
        self.memo("here.md")
        before = self.read_index()
        result = fixes.apply_safe_fixes(self.memory)
        self.assertEqual(result.applied, [])
        self.assertEqual(self.read_index(), before)

    def test_dry_run_changes_nothing_on_disk(self):
        self.index("- [Gone](gone.md) — a\n")
        before = self.read_index()
        result = fixes.apply_safe_fixes(self.memory, dry_run=True)
        self.assertTrue(result.applied)
        self.assertEqual(self.read_index(), before)

    def test_an_index_still_too_long_is_proposed_not_trimmed(self):
        entries = []
        for index in range(memory_audit.INDEX_LINE_LIMIT + 20):
            name = f"m{index}.md"
            self.memo(name)
            entries.append(f"- [M{index}]({name}) — a")
        self.index("\n".join(entries) + "\n")
        result = fixes.apply_safe_fixes(self.memory)
        titles = [title for title, _ in result.proposals]
        self.assertIn("Shorten the memory index", titles)
        self.assertGreater(len(self.read_index().splitlines()), memory_audit.INDEX_LINE_LIMIT)

    def test_generated_entry_cannot_contain_link_breaking_characters(self):
        self.index("")
        self.memo("odd.md", description="uses foo(bar) and [baz] heavily")
        fixes.apply_safe_fixes(self.memory)
        entry = [l for l in self.read_index().splitlines() if "odd.md" in l][0]
        self.assertEqual(entry.count("("), 1)
        self.assertEqual(entry.count(")"), 1)
        self.assertEqual(entry.count("["), 1)

    def test_generated_entry_survives_a_re_audit(self):
        self.index("")
        self.memo("odd.md", description="uses foo(bar) and [baz] heavily")
        fixes.apply_safe_fixes(self.memory)
        found = {f.check for f in memory_audit.audit(self.memory)}
        self.assertNotIn("dead-index-entry", found)
        self.assertNotIn("unreachable-memory", found)

    def test_entry_mixing_a_live_and_dead_link_is_proposed_not_dropped(self):
        self.index("- see [Here](here.md) and [Gone](gone.md)\n")
        self.memo("here.md")
        result = fixes.apply_safe_fixes(self.memory)
        self.assertIn("here.md", self.read_index())
        titles = [title for title, _ in result.proposals]
        self.assertIn("Index entry mixes a live and a dead link", titles)

    def test_no_memory_directory_is_proposed_not_crashed(self):
        result = fixes.apply_safe_fixes(self.memory.parent / "absent")
        self.assertEqual(result.applied, [])
        self.assertTrue(result.proposals)


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_destination_is_the_zero_config_default(self):
        result = delivery.deliver("a summary", config={}, out_dir=self.tmp)
        self.assertEqual(result.destination, "file")
        self.assertEqual(Path(result.detail).read_text(), "a summary")

    def test_unconfigured_command_destination_is_an_error(self):
        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.deliver("a summary", config={"destination": "command"})
        self.assertIn("no command is configured", str(caught.exception))

    def test_unconfigured_command_does_not_fall_back_to_a_file(self):
        with self.assertRaises(delivery.DeliveryError):
            delivery.deliver(
                "a summary", config={"destination": "command"}, out_dir=self.tmp
            )
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_configured_command_receives_the_summary_on_stdin(self):
        seen = {}

        def runner(argv, **kwargs):
            seen["argv"] = argv
            seen["input"] = kwargs.get("input")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = delivery.deliver(
            "a summary",
            config={"destination": "command", "command": "notify --to team"},
            runner=runner,
        )
        self.assertEqual(seen["argv"], ["notify", "--to", "team"])
        self.assertEqual(seen["input"], "a summary")
        self.assertTrue(result.ok)

    def test_failing_command_is_reported_not_swallowed(self):
        def runner(argv, **kwargs):
            return SimpleNamespace(returncode=3, stdout="", stderr="no route to host")

        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.deliver(
                "a summary",
                config={"destination": "command", "command": "notify"},
                runner=runner,
            )
        self.assertIn("no route to host", str(caught.exception))

    def test_a_hanging_command_is_reported_not_raised_raw(self):
        def runner(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.deliver(
                "a summary",
                config={"destination": "command", "command": "notify", "timeout_seconds": 1},
                runner=runner,
            )
        self.assertIn("did not finish", str(caught.exception))
        self.assertIn("Nothing was delivered", str(caught.exception))

    def test_a_missing_command_is_reported_not_raised_raw(self):
        def runner(argv, **kwargs):
            raise FileNotFoundError("no such executable")

        with self.assertRaises(delivery.DeliveryError) as caught:
            delivery.deliver(
                "a summary",
                config={"destination": "command", "command": "nonexistent-notifier"},
                runner=runner,
            )
        self.assertIn("could not be run", str(caught.exception))

    def test_unknown_destination_is_an_error(self):
        with self.assertRaises(delivery.DeliveryError):
            delivery.deliver("a summary", config={"destination": "carrier-pigeon"})

    def test_data_dir_prefers_the_plugin_data_variable(self):
        found = delivery.data_dir({"CLAUDE_PLUGIN_DATA": "/data/plugin"})
        self.assertEqual(found, Path("/data/plugin"))

    def test_data_dir_falls_back_without_the_variable(self):
        found = delivery.data_dir({"HOME": "/home/person"})
        self.assertIn("brightops-ai-skills", str(found))


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Sandbox the plugin data directory: a test must never write into the
        # real one, and the default resolves to the user's config directory.
        self._env = unittest.mock.patch.dict(
            os.environ, {"CLAUDE_PLUGIN_DATA": str(self.tmp / "plugin-data")}
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.memory = self.tmp / "memory"
        self.memory.mkdir()
        (self.memory / "MEMORY.md").write_text("- [A](a.md) — a\n", encoding="utf-8")
        (self.memory / "a.md").write_text(
            "---\nname: a\nmetadata:\n  type: user\n---\n\nBody.\n", encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(argv)
        return code, json.loads(buffer.getvalue())

    def test_resolve_reports_every_location(self):
        code, payload = self.run_cli(["resolve"])
        self.assertEqual(code, 0)
        for key in ("memory_dir", "transcripts_dir", "project_root", "memory_source"):
            self.assertIn(key, payload)

    def test_audit_reports_findings_as_json(self):
        code, payload = self.run_cli(["audit", "--memory-dir", str(self.memory)])
        self.assertEqual(code, 0)
        self.assertEqual(payload["finding_count"], 0)

    def test_extract_writes_a_digest_file(self):
        transcripts = self.tmp / "transcripts"
        transcripts.mkdir()
        (transcripts / "s.jsonl").write_text("", encoding="utf-8")
        out = self.tmp / "digest.json"
        code, payload = self.run_cli(
            ["extract", "--transcripts-dir", str(transcripts), "--out", str(out)]
        )
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())
        self.assertEqual(payload["written"], str(out))

    def test_snapshot_then_restore_round_trips(self):
        code, taken = self.run_cli(["snapshot", "--memory-dir", str(self.memory)])
        self.assertEqual(code, 0)
        (self.memory / "a.md").write_text("clobbered\n", encoding="utf-8")
        code, restored = self.run_cli(["restore", "--memory-dir", str(self.memory)])
        self.assertEqual(code, 0)
        self.assertIn("a.md", restored["restored"])
        self.assertIn("Body.", (self.memory / "a.md").read_text())

    def test_fix_takes_a_snapshot_before_writing(self):
        (self.memory / "MEMORY.md").write_text(
            "- [A](a.md) — a\n- [Gone](gone.md) — b\n", encoding="utf-8"
        )
        code, payload = self.run_cli(["fix", "--memory-dir", str(self.memory)])
        self.assertEqual(code, 0)
        self.assertTrue(payload["snapshot"])
        self.assertTrue(snapshot.list_snapshots(self.memory))

    def test_fix_dry_run_takes_no_snapshot(self):
        code, payload = self.run_cli(
            ["fix", "--memory-dir", str(self.memory), "--dry-run"]
        )
        self.assertEqual(payload["snapshot"], "")
        self.assertEqual(snapshot.list_snapshots(self.memory), [])

    def test_approved_reads_only_ticked_items(self):
        doc = self.tmp / "overview.md"
        doc.write_text(
            "## Awaiting sign-off\n\n"
            "- [x] **Yes** — do it <!-- dream:id=aaa1 seen=1 -->\n"
            "- [ ] **No** — skip it <!-- dream:id=bbb2 seen=1 -->\n",
            encoding="utf-8",
        )
        code, payload = self.run_cli(["approved", str(doc)])
        self.assertEqual([i["title"] for i in payload["approved"]], ["Yes"])

    def test_missing_file_exits_non_zero_with_an_error(self):
        code, payload = self.run_cli(["approved", str(self.tmp / "absent.md")])
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])

    def test_deliver_writes_a_file_by_default(self):
        summary = self.tmp / "summary.md"
        summary.write_text("run summary", encoding="utf-8")
        code, payload = self.run_cli(
            ["deliver", "--summary-file", str(summary), "--destination", "file"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
