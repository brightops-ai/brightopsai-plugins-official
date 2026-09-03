"""Safety and sign-off: a snapshot that survives, a checkbox that is honoured."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from dream import overview as ov
from dream import snapshot

NOW = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.memory = self.project / "memory"
        self.memory.mkdir()
        (self.memory / "MEMORY.md").write_text("- [A](a.md) — a\n", encoding="utf-8")
        (self.memory / "a.md").write_text("original\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_snapshot_lands_beside_memory_not_inside_it(self):
        taken = snapshot.create(self.memory, now=NOW)
        self.assertEqual(taken.path.parent.parent, self.project)
        self.assertNotIn(self.memory, taken.path.parents)

    def test_snapshot_copies_every_markdown_file(self):
        taken = snapshot.create(self.memory, now=NOW)
        self.assertEqual(taken.file_count, 2)
        self.assertEqual((taken.path / "a.md").read_text(), "original\n")

    def test_restore_puts_back_what_was_captured(self):
        snapshot.create(self.memory, now=NOW)
        (self.memory / "a.md").write_text("clobbered\n", encoding="utf-8")
        restored = snapshot.restore(self.memory)
        self.assertIn("a.md", restored)
        self.assertEqual((self.memory / "a.md").read_text(), "original\n")

    def test_restore_defaults_to_the_newest_snapshot(self):
        snapshot.create(self.memory, now=NOW)
        (self.memory / "a.md").write_text("second state\n", encoding="utf-8")
        snapshot.create(self.memory, now=NOW + dt.timedelta(minutes=1))
        (self.memory / "a.md").write_text("third state\n", encoding="utf-8")
        snapshot.restore(self.memory)
        self.assertEqual((self.memory / "a.md").read_text(), "second state\n")

    def test_restore_leaves_files_created_since_the_snapshot(self):
        snapshot.create(self.memory, now=NOW)
        (self.memory / "later.md").write_text("new\n", encoding="utf-8")
        snapshot.restore(self.memory)
        self.assertTrue((self.memory / "later.md").exists())

    def test_two_snapshots_in_the_same_second_do_not_collide(self):
        first = snapshot.create(self.memory, now=NOW)
        second = snapshot.create(self.memory, now=NOW)
        self.assertNotEqual(first.path, second.path)

    def test_restore_without_any_snapshot_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            snapshot.restore(self.memory)

    def test_snapshot_of_a_missing_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            snapshot.create(self.project / "absent")

    def test_prune_keeps_the_newest(self):
        for minute in range(5):
            snapshot.create(self.memory, now=NOW + dt.timedelta(minutes=minute))
        removed = snapshot.prune(self.memory, keep=2)
        self.assertEqual(len(removed), 3)
        self.assertEqual(len(snapshot.list_snapshots(self.memory)), 2)

    def test_prune_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            snapshot.prune(self.memory, keep=0)


class OverviewRenderTest(unittest.TestCase):
    def test_pending_items_render_as_unticked_checkboxes(self):
        doc = ov.Overview(pending=[ov.Item("Merge duplicates", "two say the same thing")])
        text = ov.render(doc)
        self.assertIn("- [ ] **Merge duplicates**", text)

    def test_applied_section_points_at_the_snapshot(self):
        doc = ov.Overview(applied=["trimmed the index"], snapshot="/snap/20260903")
        text = ov.render(doc)
        self.assertIn("/snap/20260903", text)
        self.assertIn("trimmed the index", text)

    def test_empty_run_still_says_so(self):
        text = ov.render(ov.Overview())
        self.assertIn("Nothing was applied automatically", text)
        self.assertIn("Nothing is waiting on a decision", text)

    def test_round_trip_preserves_items(self):
        doc = ov.Overview(
            applied=["removed a dead link"],
            pending=[ov.Item("Retire a rule", "no longer true")],
        )
        parsed = ov.parse(ov.render(doc))
        self.assertEqual(parsed.applied, ["removed a dead link"])
        self.assertEqual(len(parsed.pending), 1)
        self.assertEqual(parsed.pending[0].title, "Retire a rule")
        self.assertEqual(parsed.pending[0].detail, "no longer true")

    def test_identity_is_stable_across_runs(self):
        first = ov.Item("Retire a rule", "no longer true")
        second = ov.Item("Retire a rule", "no longer true")
        self.assertEqual(first.identifier, second.identifier)

    def test_different_proposals_get_different_identities(self):
        self.assertNotEqual(
            ov.Item("A", "x").identifier, ov.Item("B", "x").identifier
        )


class SignOffTest(unittest.TestCase):
    def setUp(self):
        self.doc = ov.Overview(
            pending=[
                ov.Item("Approved change", "detail one"),
                ov.Item("Ignored change", "detail two"),
            ]
        )
        rendered = ov.render(self.doc)
        self.ticked = rendered.replace(
            "- [ ] **Approved change**", "- [x] **Approved change**"
        )

    def test_only_ticked_items_are_approved(self):
        approved = ov.approved(self.ticked)
        self.assertEqual([i.title for i in approved], ["Approved change"])

    def test_capital_x_also_counts_as_ticked(self):
        approved = ov.approved(self.ticked.replace("- [x]", "- [X]"))
        self.assertEqual(len(approved), 1)

    def test_nothing_ticked_approves_nothing(self):
        self.assertEqual(ov.approved(ov.render(self.doc)), [])

    def test_an_unticked_item_reappearing_ages(self):
        previous = ov.parse(ov.render(self.doc)).pending
        fresh = [ov.Item("Ignored change", "detail two")]
        pending, declined = ov.carry_forward(previous, fresh)
        self.assertEqual(declined, [])
        self.assertEqual(pending[0].seen, 2)

    def test_an_item_ignored_past_the_threshold_is_declined(self):
        item = ov.Item("Ignored change", "detail two", seen=3)
        pending, declined = ov.carry_forward(
            [item], [ov.Item("Ignored change", "detail two")], expire_after_runs=3
        )
        self.assertEqual(pending, [])
        self.assertEqual([i.title for i in declined], ["Ignored change"])

    def test_a_new_proposal_starts_at_one_sighting(self):
        pending, _ = ov.carry_forward([], [ov.Item("Brand new", "detail")])
        self.assertEqual(pending[0].seen, 1)

    def test_an_already_ticked_item_is_not_re_proposed(self):
        previous = [ov.Item("Approved change", "detail one", ticked=True)]
        pending, declined = ov.carry_forward(
            previous, [ov.Item("Approved change", "detail one")]
        )
        self.assertEqual(pending, [])
        self.assertEqual(declined, [])

    def test_declined_items_are_shown_in_the_document(self):
        doc = ov.Overview(declined=[ov.Item("Ignored change", "detail two")])
        self.assertIn("Ignored change", ov.render(doc))


if __name__ == "__main__":
    unittest.main()
