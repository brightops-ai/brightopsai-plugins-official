"""Disclosure checks for marketplace-scout SKILL.md vs references/."""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "marketplace-scout" / "SKILL.md"
REFS = SKILL.parent / "references"

# Fingerprint of the 41-column header dump that must not live in SKILL.md.
CSV_HEADER_FINGERPRINT = (
    "id,search_term,title,price,market_price_low,market_price_high,"
    "market_price_median,price_vs_market,grade,grade_breakdown"
)

TIMING_PHRASES = (
    "2-5s between listings",
    "30-60s between searches",
    "5-15s every 5 listings",
    "random 1-3s pauses",
    "wait 30-60 seconds",
    "wait 2-5s between listings",
    "5-15s pause every 5 listings",
)

OLD_DASHBOARD_CP = (
    'cp -r "${CLAUDE_PLUGIN_ROOT}/skills/marketplace-scout/assets/dashboard/" ./dashboard/'
)


class TestSkillDisclosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")

    def test_csv_schema_reference_exists(self) -> None:
        path = REFS / "csv-schema.md"
        self.assertTrue(path.is_file(), f"missing {path}")

    def test_anti_detection_reference_exists(self) -> None:
        path = REFS / "anti-detection.md"
        self.assertTrue(path.is_file(), f"missing {path}")

    def test_skill_points_at_csv_schema_before_write(self) -> None:
        self.assertIn(
            "read `references/csv-schema.md` before writing the csv",
            self.skill.lower(),
        )

    def test_skill_loads_anti_detection_before_browser_loop(self) -> None:
        self.assertIn("read `references/anti-detection.md`", self.skill.lower())

    def test_references_list_names_new_files(self) -> None:
        self.assertIn("`references/csv-schema.md`", self.skill)
        self.assertIn("`references/anti-detection.md`", self.skill)

    def test_skill_does_not_inline_csv_header(self) -> None:
        self.assertNotIn(CSV_HEADER_FINGERPRINT, self.skill)

    def test_skill_does_not_inline_searches_json_shape(self) -> None:
        self.assertNotIn('"gradeDistribution"', self.skill)
        self.assertNotIn('"csvFile":', self.skill)

    def test_skill_does_not_restate_anti_detection_timings(self) -> None:
        lower = self.skill.lower()
        for phrase in TIMING_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase.lower(), lower)

    def test_word_count_well_under_2000(self) -> None:
        words = len(self.skill.split())
        self.assertLess(
            words,
            1600,
            f"SKILL.md is {words} words; after disclosure it should stay well under 2000",
        )

    def test_csv_schema_holds_columns_and_searches_shape(self) -> None:
        text = (REFS / "csv-schema.md").read_text(encoding="utf-8")
        self.assertIn(CSV_HEADER_FINGERPRINT, text)
        self.assertIn("searches.json", text)
        self.assertIn("grade_breakdown", text)
        self.assertIn("GradeLetter", text)

    def test_anti_detection_holds_timings_and_scroll_policy(self) -> None:
        text = (REFS / "anti-detection.md").read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("2-5s", lower)
        self.assertIn("30-60s", lower)
        self.assertIn("5-15s", lower)
        self.assertRegex(lower, r"scroll")

    def test_dashboard_scaffolding_uses_plugin_data(self) -> None:
        self.assertIn("ensure-dashboard.sh", self.skill)
        self.assertIn("${CLAUDE_PLUGIN_DATA}", self.skill)
        self.assertIn("${CLAUDE_PLUGIN_DATA}/data/", self.skill)
        self.assertIn("${CLAUDE_PLUGIN_DATA}/dashboard/public/data/", self.skill)
        self.assertNotIn(OLD_DASHBOARD_CP, self.skill)
        self.assertIn("port 5173", self.skill)


if __name__ == "__main__":
    unittest.main()
