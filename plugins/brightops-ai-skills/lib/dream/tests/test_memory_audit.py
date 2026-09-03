"""Hygiene checks must catch the silent failures, and stay silent otherwise."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from dream import memory_audit


def checks(findings):
    return {f.check for f in findings}


class MemoryDirBuilder:
    """Builds a throwaway memory directory for one test."""

    def __init__(self, root: Path):
        self.root = root

    def index(self, text: str):
        (self.root / "MEMORY.md").write_text(text, encoding="utf-8")
        return self

    def memory(self, filename: str, body: str = "A fact.", **frontmatter):
        lines = ["---"]
        for key, value in frontmatter.items():
            lines.append(f"{key}: {value}")
        lines += ["---", "", body, ""]
        (self.root / filename).write_text("\n".join(lines), encoding="utf-8")
        return self

    def raw(self, name: str, text: str):
        (self.root / name).write_text(text, encoding="utf-8")
        return self


class AuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "memory"
        self.dir.mkdir()
        self.build = MemoryDirBuilder(self.dir)
        self.now = dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self._tmp.cleanup()

    def audit(self, **kwargs):
        return memory_audit.audit(self.dir, now=self.now, **kwargs)

    def test_healthy_directory_reports_nothing(self):
        self.build.index("- [Role](user_role.md) — who they are\n").memory(
            "user_role.md", type="user", modified="2026-09-01T00:00:00Z"
        )
        self.assertEqual(self.audit(), [])

    def test_missing_directory_is_not_reported_as_clean(self):
        findings = memory_audit.audit(self.dir.parent / "absent", now=self.now)
        self.assertEqual(checks(findings), {"memory-directory-missing"})

    def test_index_over_line_limit_names_what_is_dropped(self):
        body = "\n".join(f"- entry {n}" for n in range(250))
        self.build.index(body)
        findings = [f for f in self.audit() if f.check == "index-over-line-limit"]
        self.assertEqual(len(findings), 1)
        self.assertIn("250 lines", findings[0].detail)
        self.assertIn("line 201", findings[0].detail)
        self.assertTrue(findings[0].auto_fixable)

    def test_index_at_the_line_limit_is_not_flagged(self):
        self.build.index("\n".join(f"- entry {n}" for n in range(200)))
        self.assertNotIn("index-over-line-limit", checks(self.audit()))

    def test_index_over_byte_limit_is_reported(self):
        self.build.index("- " + ("x" * 26000) + "\n")
        self.assertIn("index-over-byte-limit", checks(self.audit()))

    def test_dead_index_entry_is_reported(self):
        self.build.index("- [Gone](vanished.md) — no longer here\n")
        findings = [f for f in self.audit() if f.check == "dead-index-entry"]
        self.assertEqual(len(findings), 1)
        self.assertIn("vanished.md", findings[0].detail)

    def test_unreachable_memory_is_reported(self):
        self.build.index("- [Role](user_role.md) — who they are\n").memory(
            "user_role.md", type="user"
        ).memory("orphan.md", type="project")
        findings = [f for f in self.audit() if f.check == "unreachable-memory"]
        self.assertEqual(len(findings), 1)
        self.assertIn("orphan.md", findings[0].detail)

    def test_wiki_links_count_as_index_references(self):
        self.build.index("- [[user_role]] — who they are\n").memory(
            "user_role.md", type="user"
        )
        self.assertNotIn("unreachable-memory", checks(self.audit()))

    def test_missing_index_reports_every_topic_file_unreachable(self):
        self.build.memory("a.md", type="user")
        found = checks(self.audit())
        self.assertIn("index-missing", found)

    def test_invalid_type_is_reported(self):
        self.build.index("- [X](x.md) — a\n").memory("x.md", type="notes")
        findings = [f for f in self.audit() if f.check == "invalid-type"]
        self.assertEqual(len(findings), 1)
        self.assertIn("notes", findings[0].detail)

    def test_each_documented_type_is_accepted(self):
        entries = []
        for name in memory_audit.VALID_TYPES:
            entries.append(f"- [{name}]({name}.md) — a")
            self.build.memory(f"{name}.md", type=name)
        self.build.index("\n".join(entries) + "\n")
        self.assertEqual(self.audit(), [])

    def test_missing_type_is_reported(self):
        self.build.index("- [X](x.md) — a\n").memory("x.md", name="x")
        self.assertIn("missing-type", checks(self.audit()))

    def test_file_without_frontmatter_is_reported(self):
        self.build.index("- [X](x.md) — a\n").raw("x.md", "just prose\n")
        self.assertIn("missing-frontmatter", checks(self.audit()))

    def test_stale_memory_is_reported_with_its_age(self):
        self.build.index("- [X](x.md) — a\n").memory(
            "x.md", type="user", modified="2025-01-01T00:00:00Z"
        )
        findings = [f for f in self.audit() if f.check == "stale-memory"]
        self.assertEqual(len(findings), 1)
        self.assertIn("days ago", findings[0].detail)

    def test_recent_memory_is_not_stale(self):
        self.build.index("- [X](x.md) — a\n").memory(
            "x.md", type="user", modified="2026-08-30T00:00:00Z"
        )
        self.assertNotIn("stale-memory", checks(self.audit()))

    def test_stale_threshold_is_configurable(self):
        self.build.index("- [X](x.md) — a\n").memory(
            "x.md", type="user", modified="2026-06-01T00:00:00Z"
        )
        self.assertNotIn("stale-memory", checks(self.audit()))
        self.assertIn("stale-memory", checks(self.audit(stale_days=30)))

    def test_unreadable_modified_is_reported(self):
        self.build.index("- [X](x.md) — a\n").memory(
            "x.md", type="user", modified="last tuesday"
        )
        self.assertIn("unreadable-modified", checks(self.audit()))

    def test_duplicate_index_entry_is_reported(self):
        self.build.index(
            "- [X](x.md) — a\n- [X](x.md) — a\n"
        ).memory("x.md", type="user")
        findings = [f for f in self.audit() if f.check == "duplicate-index-entry"]
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].auto_fixable)

    def test_distinct_entries_are_not_duplicates(self):
        self.build.index(
            "- [X](x.md) — a\n- [Y](y.md) — b\n"
        ).memory("x.md", type="user").memory("y.md", type="user")
        self.assertNotIn("duplicate-index-entry", checks(self.audit()))

    def test_audit_writes_nothing(self):
        self.build.index("- [X](x.md) — a\n").memory("x.md", type="user")
        before = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        self.audit()
        after = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        self.assertEqual(before, after)


class FrontmatterTest(unittest.TestCase):
    def test_unterminated_frontmatter_is_not_frontmatter(self):
        fields, ok = memory_audit.parse_frontmatter("---\ntype: user\nno terminator\n")
        self.assertFalse(ok)
        self.assertEqual(fields, {})

    def test_quotes_are_stripped_from_values(self):
        fields, ok = memory_audit.parse_frontmatter('---\ntype: "user"\n---\n')
        self.assertTrue(ok)
        self.assertEqual(fields["type"], "user")

    def test_body_text_is_not_mistaken_for_fields(self):
        fields, _ = memory_audit.parse_frontmatter("---\ntype: user\n---\nkey: value\n")
        self.assertNotIn("key", fields)


if __name__ == "__main__":
    unittest.main()


class NestedFrontmatterTest(unittest.TestCase):
    """Written memory files nest type and modified under a metadata block."""

    NESTED = (
        "---\n"
        "name: a-memory\n"
        "description: something\n"
        "metadata: \n"
        "  node_type: memory\n"
        "  type: user\n"
        "  modified: 2026-08-10T09:37:14.187Z\n"
        "---\n\nBody.\n"
    )

    def test_nested_type_is_found(self):
        fields, ok = memory_audit.parse_frontmatter(self.NESTED)
        self.assertTrue(ok)
        self.assertEqual(fields["type"], "user")
        self.assertEqual(fields["metadata.type"], "user")

    def test_nested_modified_is_found(self):
        fields, _ = memory_audit.parse_frontmatter(self.NESTED)
        self.assertTrue(fields["modified"].startswith("2026-08-10"))

    def test_top_level_key_wins_over_nested(self):
        text = "---\ntype: project\nmetadata:\n  type: user\n---\n"
        fields, _ = memory_audit.parse_frontmatter(text)
        self.assertEqual(fields["type"], "project")

    def test_nested_memory_file_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MEMORY.md").write_text("- [A](a.md) — a\n", encoding="utf-8")
            (root / "a.md").write_text(self.NESTED, encoding="utf-8")
            found = checks(
                memory_audit.audit(
                    root, now=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)
                )
            )
        self.assertNotIn("missing-type", found)
        self.assertNotIn("missing-frontmatter", found)
