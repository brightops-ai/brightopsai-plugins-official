"""Guards on the adversarial-review upload gate (SKILL.md and upload-gate.md).

The skill uploads a document to a third party. Its gate is prose that an
agent follows, so these tests cannot show that an agent obeys it: that needs
a live run with a browser. What they can do:

- assert each rule is written down, says what it must, and sits before the
  step it has to precede (no read before the scan; dismissal, snapshot,
  destination and fallback rules before the upload);
- assert no line that mentions a dismissed, cancelled or unanswered question
  does anything but stop;
- pin the text of the gate steps, so that any edit to them — including an
  added sentence these rule checks would not recognise — fails until the pin
  is updated on purpose, in a diff a reviewer sees.

What can be executed is tested where it lives: the snapshot and scan scripts,
in `snapshot-document.bats` and `scan-secrets.bats`.

To update the pin after a deliberate change to the gate steps:

    python3 tests/test_skill_upload_gate.py --print-pin
"""

from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN_ROOT / "skills" / "adversarial-review"
SKILL = SKILL_DIR / "SKILL.md"
REFS = SKILL_DIR / "references"

# Quoted trigger phrases the description carried before the gate existed.
# None names Grok or an adversarial review.
GENERAL_CRITIQUE_TRIGGERS = (
    '"stress-test this plan"',
    '"get a second opinion on',
    '"red team this document"',
    '"devil\'s',
    '"challenge this plan"',
    '"poke holes in this"',
    '"critique this',
    '"tear this apart"',
    '"find the flaws"',
    '"what\'s wrong with this plan"',
    '"cross-model review"',
)

SCAN_STEP = "### 3. Snapshot, Scan, Then Read"
UPLOAD_STEP = "### 6. Navigate to Grok Projects and Upload Document"

# The steps that stand between the document and grok.com.
GATE_STEPS = (1, 3, 4, 5, 6, 7, 12)
GATE_PIN = (
    "5b251c890d1df11e4e55dd762f19a9ac"
    "86166f144612ab72e5aaded664db9bae"
)

# A line that mentions one of these must tell the agent to stop.
NO_ANSWER_WORDS = re.compile(
    r"dismiss|cancel|unclear|unanswered|no answer|not answer|declin|denied|"
    r"times? out|timeout|no user",
    re.I,
)
STOPS = re.compile(r"\bstop\b|send nothing|leave the old source", re.I)
# Lines that only name the options or list the ways out, and decide nothing.
NO_ANSWER_EXEMPT = (
    'Offer "Upload" and "Cancel".',
    'Options "Upload" and "Cancel".',
    'Options "Paste" and "Cancel".',
    "**Cleanup.**",
    "run, not only at the end:",
    "On timeout (120 seconds total)",
)
PROCEEDS_WITHOUT_CONSENT = re.compile(
    r"\b(proceed|continue|upload|paste|send|go ahead)\w*\s+(anyway|regardless|"
    r"without (asking|an answer|confirmation|approval))|"
    r"\b(treat|take|count)\w*\s+\w*\s*(it|that|this|silence|no answer|"
    r"dismissal)\s+as\s+(approval|consent|a? ?yes|confirmation)|"
    r"\bassum\w+\s+(approval|consent|yes)\b|"
    r"\bimplicit(ly)?\s+(approval|consent|approved)",
    re.I,
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    _, frontmatter, body = text.split("---\n", 2)
    return frontmatter, body


def _flat(text: str) -> str:
    """Collapse whitespace so a phrase matches across line wraps."""
    return " ".join(text.split())


def _blocks(text: str) -> list[str]:
    """Paragraphs and list items, each flattened to one line."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        for item in re.split(r"\n(?=\s*(?:[-*>]|\d+\.)\s)", para):
            flat = _flat(item)
            if flat:
                out.append(flat)
    return out


def _step_text(body: str, number: int) -> str:
    match = re.search(rf"^### {number}\. .*$", body, re.M)
    if match is None:
        raise AssertionError(f"no step {number}")
    following = re.search(r"^##+ ", body[match.end():], re.M)
    end = match.end() + following.start() if following else len(body)
    return body[match.start():end]


def gate_pin(body: str) -> str:
    text = "\n".join(_flat(_step_text(body, n)) for n in GATE_STEPS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SkillTextCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SKILL.read_text(encoding="utf-8")
        cls.frontmatter, cls.body = _split_frontmatter(cls.text)
        cls.gate_ref = (REFS / "upload-gate.md").read_text(encoding="utf-8")
        cls.scan_at = cls.body.index(SCAN_STEP)
        cls.upload_at = cls.body.index(UPLOAD_STEP)

    def step(self, number: int) -> str:
        return _step_text(self.body, number)

    def assert_before_upload(self, phrase: str) -> None:
        """`phrase` is in the skill and first appears before the upload step."""
        self.assertIn(phrase, self.body)
        self.assertLess(
            self.body.index(phrase),
            self.upload_at,
            f"rule appears only after the upload step: {phrase!r}",
        )


class TestDescription(SkillTextCase):
    def _description(self) -> str:
        start = self.frontmatter.index("description:")
        end = self.frontmatter.index("argument-hint:")
        return _flat(self.frontmatter[start:end])

    def test_description_has_no_general_critique_triggers(self) -> None:
        description = self._description()
        for phrase in GENERAL_CRITIQUE_TRIGGERS:
            self.assertNotIn(phrase, description)

    def test_every_quoted_trigger_names_grok_or_an_adversarial_review(self) -> None:
        quoted = self._description().split('"')[1::2]
        self.assertTrue(quoted)
        for phrase in quoted:
            lowered = phrase.lower()
            self.assertTrue(
                "grok" in lowered or "adversarial" in lowered,
                f"trigger names neither Grok nor an adversarial review: {phrase!r}",
            )

    def test_description_excludes_other_reviewers(self) -> None:
        description = self._description()
        self.assertIn("names another reviewer or model", description)
        self.assertIn("local or delegated reviewer", description)

    def test_description_keeps_model_invocable_convention(self) -> None:
        self.assertIn(
            "This skill should be used when the user asks to", self._description()
        )
        self.assertNotIn("disable-model-invocation", self.frontmatter)

    def test_skill_stays_within_the_word_guidance(self) -> None:
        # CLAUDE.md: keep SKILL.md under about 2,000 words, frontmatter included.
        self.assertLessEqual(len(self.text.split()), 2000)


class TestNothingReadsBeforeTheScan(SkillTextCase):
    """B3: a secret in the document must not reach the transcript first."""

    READS = re.compile(
        r"\bRead tool\b|\bread the (file|document|content)|"
        r"\bRead the file content\b|\bopen the document\b|\bcat\b|\bhead\b|"
        r"\bgrep\b",
        re.I,
    )

    def test_steps_before_the_scan_forbid_reading(self) -> None:
        step = _flat(self.step(1))
        self.assertIn("**Do not open the document yet.**", step)
        self.assertIn(
            "before the scan in step 3 exits 0", step
        )
        self.assertIn("Until then use metadata only", step)

    def test_no_instruction_to_read_before_the_scan_command(self) -> None:
        scan_command = self.body.index('scan-secrets.sh" "<snapshot>" "<document>"')
        before = self.body[:scan_command]
        for block in _blocks(before):
            if not self.READS.search(block):
                continue
            # The only mentions allowed are prohibitions.
            self.assertRegex(
                block,
                r"Do not open the document yet|No Read,|Never send from the "
                r"source path|only thing scanned, read, approved",
                f"an instruction before the scan reads the document: {block!r}",
            )

    def test_reading_happens_after_a_clean_scan_and_from_the_snapshot(self) -> None:
        step = self.step(3)
        flat = _flat(step)
        scan = step.index('scan-secrets.sh" "<snapshot>" "<document>"')
        read = step.index("Only now read the document, from the snapshot path")
        self.assertLess(scan, read)
        self.assertIn(
            "- **0** — no pattern matched. Only now read the document, from "
            "the snapshot path",
            flat,
        )
        self.assertIn(
            "Do not open the document to inspect or fix the hit", flat
        )

    def test_source_is_checked_before_it_is_opened_for_edits(self) -> None:
        flat = _flat(self.step(11))
        check = flat.index("Before opening or editing it, run the step 6 `check`")
        edit = flat.index("Create a backup of the original document")
        self.assertLess(check, edit)
        self.assertIn("On `CHANGED`, stop", flat)


class TestStepOrder(SkillTextCase):
    def test_gate_steps_are_in_order(self) -> None:
        headings = [
            "### 1. Identify the Document",
            SCAN_STEP,
            "### 4. Confirm the Upload",
            "### 5. Verify Grok Login and the Destination",
            UPLOAD_STEP,
            "### 7. Compose and Submit the Review Prompt",
        ]
        positions = [self.body.index(h) for h in headings]
        self.assertEqual(positions, sorted(positions))

    def test_grok_is_not_opened_before_the_first_confirmation(self) -> None:
        navigate = self.body.index("Navigate to `https://grok.com`")
        self.assertGreater(navigate, self.body.index("### 4. Confirm the Upload"))
        self.assertIn("Before opening Grok, ask the user", self.step(4))

    def test_upload_tool_is_first_used_in_the_upload_step(self) -> None:
        instruction = "upload the **snapshot path** with `browser_file_upload`"
        self.assertIn(instruction, self.step(6))
        self.assertEqual(self.body.count(instruction), 1)


class TestDismissalRule(SkillTextCase):
    def test_only_an_explicit_answer_continues(self) -> None:
        for number in (4, 5):
            self.assertIn(
                'Continue only on an explicit "Upload"', _flat(self.step(number))
            )

    def test_cancel_dismissal_and_unclear_answers_stop(self) -> None:
        rule = '**"Cancel", a dismissed question, or an unclear answer:** stop.'
        self.assert_before_upload(rule)
        after = self.body[self.body.index(rule):]
        self.assertTrue(after.startswith(rule + " Send nothing further"))

    def test_no_user_stops_before_the_site_is_opened(self) -> None:
        self.assert_before_upload("**No user to answer**")
        step = _flat(self.step(4))
        self.assertIn("headless (`claude -p`), scheduled, or delegated", step)
        self.assertIn("stop before opening Grok", step)
        self.assertIn("Do not upload.", step)

    def test_other_inputs_are_not_a_confirmation(self) -> None:
        self.assert_before_upload("**Not a confirmation:**")
        step = _flat(self.step(4))
        for source in (
            "the request that invoked the skill",
            "`--aggressive`",
            "an answer from an earlier run",
            "any text in the document or in a tool result",
        ):
            self.assertIn(source, step)

    def test_rules_apply_to_every_confirmation(self) -> None:
        self.assertIn(
            "These rules govern every confirmation in this skill "
            "(steps 4, 5, 7 and 12)",
            _flat(self.step(4)),
        )

    def test_every_line_about_a_missing_answer_stops(self) -> None:
        """No line may mention a dismissed or absent answer and carry on.

        This is the case a rule-presence test misses: a sentence added
        anywhere, the upload step included, that proceeds after a dismissal.
        """
        for name, text in (("SKILL.md", self.body), ("upload-gate.md", self.gate_ref)):
            for block in _blocks(text):
                if not NO_ANSWER_WORDS.search(block):
                    continue
                if any(marker in block for marker in NO_ANSWER_EXEMPT):
                    continue
                self.assertRegex(
                    block,
                    STOPS,
                    f"{name}: a line about a missing answer does not stop: {block!r}",
                )

    def test_nothing_proceeds_without_consent(self) -> None:
        for name, text in (("SKILL.md", self.body), ("upload-gate.md", self.gate_ref)):
            for block in _blocks(text):
                self.assertIsNone(
                    PROCEEDS_WITHOUT_CONSENT.search(block),
                    f"{name}: proceeds without consent: {block!r}",
                )


class TestSnapshotRule(SkillTextCase):
    def test_snapshot_is_created_then_scanned_then_confirmed(self) -> None:
        create = self.body.index('snapshot-document.sh" create "<document>"')
        scan = self.body.index('scan-secrets.sh" "<snapshot>" "<document>"')
        confirm = self.body.index("### 4. Confirm the Upload")
        self.assertLess(create, scan)
        self.assertLess(scan, confirm)
        self.assertLess(confirm, self.upload_at)

    def test_the_source_path_is_never_scanned_or_sent(self) -> None:
        self.assertNotIn('scan-secrets.sh" "<document>"', self.body)
        self.assert_before_upload(
            "the snapshot is the only thing scanned, read, approved, "
            "uploaded or pasted"
        )
        self.assert_before_upload("Never send from the source path.")

    def test_confirmation_names_the_bytes(self) -> None:
        step = _flat(self.step(4))
        self.assertIn("the document's absolute path", step)
        self.assertIn("the snapshot's sha256 (first 12 digits) and size in bytes", step)
        self.assertIn("grok.com and the project name", step)
        self.assert_before_upload("**One approval, one sha256, one destination.**")
        wording = _flat(self.gate_ref)
        self.assertIn("<absolute path of the document>", wording)
        self.assertIn("sha256 `<first 12 digits>`", wording)

    def test_check_is_the_last_command_before_the_upload(self) -> None:
        step = self.step(6)
        setup = step.index("go as far as the open file chooser")
        check = step.index(
            'snapshot-document.sh" check "<snapshot>" "<sha256>" "<document>"'
        )
        send = step.index("upload the **snapshot path** with `browser_file_upload`")
        self.assertLess(setup, check)
        self.assertLess(check, send)
        flat = _flat(step)
        self.assertIn(
            "As the last command before the upload, with nothing after it but "
            "the upload itself",
            flat,
        )
        self.assertIn("in the very next tool call", flat)
        self.assertIn(
            "**`CHANGED` (exit 1), or any other exit status:** send nothing.", flat
        )
        self.assertIn("Return to step 3", flat)
        self.assertIn("ask the step 4 question again for the new sha256", flat)

    def test_edited_document_is_rescanned_and_confirmed_again(self) -> None:
        step = self.step(12)
        flat = _flat(step)
        self.assertIn("The edited document is new content", flat)
        rescan = step.index("Repeat step 3 on the edited document")
        ask = step.index("ask the step 4 question for the new sha256")
        send = step.index("replace the old project source with the new snapshot")
        self.assertLess(rescan, ask)
        self.assertLess(ask, send)
        self.assertIn("`check` as the last command before the upload", flat)
        self.assertIn("On any other answer, leave the old source in Grok", flat)

    def test_snapshots_are_removed_on_every_way_out(self) -> None:
        self.assert_before_upload("**Cleanup.** Whenever the run stops from here on")
        flat = _flat(self.step(3))
        for way_out in ('a hit', '"Cancel"', "a denied upload", "a timeout", "an error"):
            self.assertIn(way_out, flat)
        self.assertIn('snapshot-document.sh remove "<snapshot>"', flat)
        self.assertIn("Remove every snapshot made in this run", self.step(13))
        self.assertIn("on every way out of the run", _flat(self.gate_ref))

    def test_references_send_the_snapshot_not_the_source(self) -> None:
        nav = (REFS / "grok-ui-navigation.md").read_text(encoding="utf-8")
        self.assertNotIn("`browser_file_upload` with the document path", nav)
        self.assertIn(
            "`browser_file_upload` with the approved snapshot path", nav
        )
        self.assertIn("as the last command before the upload", nav)


class TestDestinationRule(SkillTextCase):
    def test_account_and_project_are_resolved_before_anything_is_sent(self) -> None:
        self.assert_before_upload(
            "The step 4 answer was given before the account was known"
        )
        step = _flat(self.step(5))
        self.assertIn(
            "Before creating a project or sending anything, resolve the actual "
            "destination from the page",
            step,
        )
        self.assertIn("the signed-in account", step)
        self.assertIn("Do not create it yet.", step)

    def test_project_is_named_by_identifier_not_by_name_alone(self) -> None:
        step = _flat(self.step(5))
        self.assertIn(
            "an existing one by its name **and** the identifier in its link "
            "(`/project/{uuid}`)",
            step,
        )
        self.assertIn(
            "the page URL must carry the confirmed identifier; if it does "
            "not, stop",
            _flat(self.step(6)),
        )
        self.assertIn("id `<uuid from its link>`", _flat(self.gate_ref))

    def test_destination_question_is_never_skipped(self) -> None:
        step = _flat(self.step(5))
        self.assertIn(
            "This question is never skipped: the step 6 upload requires its "
            "answer.",
            step,
        )
        self.assertNotRegex(self.body, r"(?i)skip this question")
        self.assertIn("Never guess it.", step)
        self.assertIn(
            'the user answered "Upload" in steps 4 and 5', _flat(self.step(6))
        )


class TestFallbackRule(SkillTextCase):
    def test_upload_tool_is_not_pre_approved(self) -> None:
        self.assertIn("browser_navigate", self.frontmatter)
        self.assertNotIn("browser_file_upload", self.frontmatter)

    def test_no_pre_approved_tool_may_send_document_content(self) -> None:
        self.assert_before_upload(
            "**Only `browser_file_upload` sends document content.**"
        )
        step = _flat(self.step(4))
        self.assertIn(
            "No pre-approved tool (`browser_evaluate`, `browser_run_code`, "
            "`browser_type`) may send document content.",
            step,
        )
        self.assertIn(
            "The single exception is the inline fallback in step 7, and only "
            "after its own confirmation.",
            step,
        )

    def test_inline_fallback_confirms_the_exact_payload(self) -> None:
        step = self.step(7)
        flat = _flat(step)
        fallback = step.index("**Inline fallback.**")
        build = step.index("build the exact payload first", fallback)
        ask = step.index("ask with AskUserQuestion", fallback)
        check = step.index("run `check` as the last command before the paste", fallback)
        paste = step.index('Paste only on an explicit "Paste"', fallback)
        self.assertEqual([build, ask, check, paste], sorted([build, ask, check, paste]))
        self.assertIn("full or truncated, its size and sha256", flat)
        self.assertIn("and only that payload", flat)
        self.assertIn(
            "On any other answer, or if `check` does not report `UNCHANGED`, stop.",
            flat,
        )

    def test_reference_gives_a_truncated_payload_its_own_snapshot(self) -> None:
        ref = _flat(self.gate_ref)
        self.assertIn("**Build the payload first.**", ref)
        self.assertIn("never from the source file", ref)
        self.assertIn("the payload is new bytes. Give it its own snapshot", ref)
        self.assertIn('scan-secrets.sh "<payload-snapshot>" "<document>"', ref)
        self.assertIn("a truncated version: <which sections are summarised", ref)
        self.assertIn("as the last command before the paste", ref)

    def test_templates_reference_points_at_the_fallback_confirmation(self) -> None:
        templates = (REFS / "adversarial-prompt-templates.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "only after the inline-fallback confirmation in SKILL.md step 7",
            _flat(templates),
        )
        self.assertIn("build it from the approved snapshot", _flat(templates))


class TestAggressiveFlag(SkillTextCase):
    def test_flag_description_states_the_backup_and_keeps_the_gate(self) -> None:
        step = _flat(self.step(2))
        self.assertIn("Both modes take the backup", step)
        self.assertIn("before the first edit", step)
        self.assertIn(
            "neither skips the scan in step 3 or any confirmation in steps "
            "4, 5, 7 and 12",
            step,
        )


class TestGatePin(SkillTextCase):
    def test_gate_steps_are_unchanged_since_the_last_deliberate_edit(self) -> None:
        self.assertEqual(
            gate_pin(self.body),
            GATE_PIN,
            "The text of a gate step changed. If that is intended, review the "
            "change against every rule above, then update GATE_PIN: "
            "python3 tests/test_skill_upload_gate.py --print-pin",
        )


if __name__ == "__main__":
    if "--print-pin" in sys.argv:
        print(gate_pin(_split_frontmatter(SKILL.read_text(encoding="utf-8"))[1]))
    else:
        unittest.main()
