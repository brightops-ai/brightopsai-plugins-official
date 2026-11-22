"""Guards on the adversarial-review SKILL.md upload gate.

The skill uploads a document to a third party. These checks keep three
properties from regressing: the description triggers only on requests that
name Grok or an adversarial review, the confirmation step sits between the
secret scan and the first contact with Grok, and the upload tool is not
pre-approved by the skill.
"""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "adversarial-review" / "SKILL.md"

# Quoted trigger phrases the description carried before the gate existed.
# None names the external reviewer or an adversarial review.
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
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    _, frontmatter, body = text.split("---\n", 2)
    return frontmatter, body


class TestUploadGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frontmatter, cls.body = _split_frontmatter(
            SKILL.read_text(encoding="utf-8")
        )

    def _description(self) -> str:
        start = self.frontmatter.index("description:")
        end = self.frontmatter.index("argument-hint:")
        return " ".join(self.frontmatter[start:end].split())

    def test_description_has_no_general_critique_triggers(self) -> None:
        description = self._description()
        for phrase in GENERAL_CRITIQUE_TRIGGERS:
            self.assertNotIn(phrase, description)

    def test_every_quoted_trigger_names_grok_or_adversarial(self) -> None:
        quoted = self._description().split('"')[1::2]
        self.assertTrue(quoted)
        for phrase in quoted:
            lowered = phrase.lower()
            self.assertTrue(
                "grok" in lowered
                or "adversarial" in lowered
                or "cross-model" in lowered,
                f"trigger does not name the reviewer: {phrase!r}",
            )

    def test_description_keeps_model_invocable_convention(self) -> None:
        self.assertIn(
            "This skill should be used when the user asks to", self._description()
        )
        self.assertNotIn("disable-model-invocation", self.frontmatter)

    def test_confirmation_sits_between_scan_and_grok(self) -> None:
        scan = self.body.index("### 3. Scan for Secrets")
        confirm = self.body.index("### 4. Confirm the Upload")
        login = self.body.index("### 5. Verify Grok Login")
        upload = self.body.index("### 6. Navigate to Grok Projects and Upload Document")
        self.assertLess(scan, confirm)
        self.assertLess(confirm, login)
        self.assertLess(login, upload)
        # grok.com is first navigated to in the login step, after the gate.
        self.assertGreater(self.body.index("Navigate to `https://grok.com`"), confirm)

    def test_confirmation_names_file_and_destination_and_stops_headless(self) -> None:
        start = self.body.index("### 4. Confirm the Upload")
        step = self.body[start : self.body.index("### 5. Verify Grok Login")]
        self.assertIn("AskUserQuestion", step)
        self.assertIn("<absolute path of the document>", step)
        self.assertIn('grok.com, project "<project name>"', step)
        self.assertIn("No user to answer", step)
        self.assertIn("stop before opening Grok", step)

    def test_upload_tool_is_not_pre_approved(self) -> None:
        self.assertIn("browser_navigate", self.frontmatter)
        self.assertNotIn("browser_file_upload", self.frontmatter)

    def test_aggressive_flag_description_states_the_backup(self) -> None:
        start = self.body.index("### 2. Parse Flags")
        step = self.body[start : self.body.index("### 3. Scan for Secrets")]
        self.assertIn("Both modes take the backup", step)
        self.assertIn("before the first edit", step)


if __name__ == "__main__":
    unittest.main()
