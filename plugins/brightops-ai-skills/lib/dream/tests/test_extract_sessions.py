"""The extractor finds structure and never decides meaning.

Fixtures here are synthetic. They contain no real paths, hostnames, usernames
or personal data.
"""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from dream import extract_sessions as ex

NOW = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)


def stamp(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()


class TranscriptBuilder:
    """Writes a synthetic .jsonl transcript one record at a time."""

    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []

    def user(self, text, minutes_ago=1, **extra):
        self.records.append(
            {
                "type": "user",
                "timestamp": stamp(minutes_ago),
                "message": {"content": text},
                **extra,
            }
        )
        return self

    def assistant_tool(self, name, params, minutes_ago=2, **extra):
        self.records.append(
            {
                "type": "assistant",
                "timestamp": stamp(minutes_ago),
                "message": {
                    "content": [{"type": "tool_use", "name": name, "input": params}]
                },
                **extra,
            }
        )
        return self

    def assistant_text(self, text, minutes_ago=2, **extra):
        self.records.append(
            {
                "type": "assistant",
                "timestamp": stamp(minutes_ago),
                "message": {"content": [{"type": "text", "text": text}]},
                **extra,
            }
        )
        return self

    def tool_result(self, text, is_error=False, minutes_ago=1):
        self.records.append(
            {
                "type": "user",
                "timestamp": stamp(minutes_ago),
                "message": {
                    "content": [
                        {"type": "tool_result", "is_error": is_error, "content": text}
                    ]
                },
            }
        )
        return self

    def write(self):
        with self.path.open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record) + "\n")
        return self.path


class ExtractorTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def builder(self, name="session-a"):
        return TranscriptBuilder(self.dir / f"{name}.jsonl")

    def extract(self, **kwargs):
        kwargs.setdefault("now", NOW)
        kwargs.setdefault("since", NOW - dt.timedelta(days=7))
        return ex.extract(self.dir, **kwargs)

    def kinds(self, digest):
        return [e.kind for e in digest.episodes]


class SignalDetectionTest(ExtractorTestCase):
    def test_interruption_is_captured_with_what_was_running(self):
        self.builder().assistant_tool(
            "Bash", {"command": "npm run build"}, minutes_ago=5
        ).assistant_text("[Request interrupted by user]", minutes_ago=4).write()
        digest = self.extract()
        self.assertEqual(self.kinds(digest), ["interrupted"])
        self.assertIn("npm run build", digest.episodes[0].preceding_action)

    def test_permission_denial_is_captured(self):
        self.builder().assistant_tool(
            "Bash", {"command": "rm -rf build"}, minutes_ago=5
        ).tool_result(
            "The user doesn't want to proceed with this tool use.", minutes_ago=4
        ).write()
        self.assertEqual(self.kinds(self.extract()), ["permission-denied"])

    def test_repeated_identical_failures_become_one_clustered_episode(self):
        builder = self.builder()
        for minute in range(6):
            builder.assistant_tool("Bash", {"command": "make test"}, minutes_ago=20 - minute)
            builder.tool_result("Exit code 2: missing target", is_error=True, minutes_ago=19 - minute)
        builder.write()
        digest = self.extract()
        self.assertEqual(self.kinds(digest), ["tool-failure"])
        self.assertEqual(digest.episodes[0].occurrences, 6)

    def test_failures_differing_only_by_number_cluster_together(self):
        builder = self.builder()
        for index, minute in enumerate((10, 8)):
            builder.assistant_tool("Bash", {"command": "pytest"}, minutes_ago=minute + 1)
            builder.tool_result(f"Exit code 1: {index} tests failed", is_error=True, minutes_ago=minute)
        builder.write()
        digest = self.extract()
        self.assertEqual(len(digest.episodes), 1)
        self.assertEqual(digest.episodes[0].occurrences, 2)

    def test_distinct_failures_stay_separate(self):
        builder = self.builder()
        builder.assistant_tool("Bash", {"command": "a"}, minutes_ago=10)
        builder.tool_result("permission denied opening socket", is_error=True, minutes_ago=9)
        builder.assistant_tool("Bash", {"command": "b"}, minutes_ago=8)
        builder.tool_result("no such file or directory", is_error=True, minutes_ago=7)
        builder.write()
        self.assertEqual(len(self.extract().episodes), 2)

    def test_short_turn_after_an_edit_is_captured(self):
        self.builder().assistant_tool(
            "Edit", {"file_path": "/synthetic/project/app.ts"}, minutes_ago=5
        ).user("no, keep the original naming", minutes_ago=4).write()
        digest = self.extract()
        self.assertEqual(self.kinds(digest), ["quick-turn-after-edit"])
        self.assertEqual(digest.episodes[0].target, "app.ts")

    def test_long_turn_after_an_edit_is_not_captured(self):
        self.builder().assistant_tool(
            "Edit", {"file_path": "/synthetic/project/app.ts"}, minutes_ago=5
        ).user("x" * 400, minutes_ago=4).write()
        self.assertEqual(self.extract().episodes, [])

    def test_short_turn_after_a_read_is_not_captured(self):
        self.builder().assistant_tool(
            "Read", {"file_path": "/synthetic/project/app.ts"}, minutes_ago=5
        ).user("thanks", minutes_ago=4).write()
        self.assertEqual(self.extract().episodes, [])

    def test_ordinary_conversation_produces_nothing(self):
        self.builder().user("please add a health check endpoint", minutes_ago=5).write()
        self.assertEqual(self.extract().episodes, [])

    def test_sidechain_records_are_ignored(self):
        self.builder().assistant_text(
            "[Request interrupted by user]", minutes_ago=4, isSidechain=True
        ).write()
        self.assertEqual(self.extract().episodes, [])

    def test_no_episode_is_labelled_a_correction(self):
        self.builder().assistant_tool(
            "Edit", {"file_path": "/synthetic/a.ts"}, minutes_ago=5
        ).user("no, use the other one", minutes_ago=4).write()
        for episode in self.extract().episodes:
            self.assertNotIn("correction", episode.kind)


class WindowTest(ExtractorTestCase):
    def test_records_older_than_the_window_are_skipped(self):
        self.builder().assistant_text(
            "[Request interrupted by user]", minutes_ago=60 * 24 * 30
        ).write()
        self.assertEqual(self.extract().episodes, [])

    def test_records_inside_the_window_are_kept(self):
        self.builder().assistant_text("[Request interrupted by user]", minutes_ago=30).write()
        self.assertEqual(len(self.extract().episodes), 1)

    def test_missing_transcript_directory_is_reported_not_silent(self):
        digest = ex.extract(self.dir / "absent", now=NOW)
        self.assertEqual(digest.episodes, [])
        self.assertIn("No transcript directory", digest.retention_gap)

    def test_empty_transcript_directory_is_reported(self):
        digest = self.extract()
        self.assertIn("No session transcripts", digest.retention_gap)

    def test_window_reaching_past_retention_is_reported(self):
        self.builder().user("hello", minutes_ago=5).write()
        digest = self.extract(since=NOW - dt.timedelta(days=400))
        self.assertIn("retention", digest.retention_gap)

    def test_malformed_lines_do_not_stop_the_scan(self):
        path = self.dir / "broken.jsonl"
        good = json.dumps(
            {
                "type": "assistant",
                "timestamp": stamp(5),
                "message": {"content": [{"type": "text", "text": ex.INTERRUPT_MARKER + "]"}]},
            }
        )
        path.write_text("{not json\n" + good + "\n", encoding="utf-8")
        self.assertEqual(len(self.extract().episodes), 1)


class BudgetTest(ExtractorTestCase):
    """Distinct failure text per episode: identical text would cluster to one."""

    WORDS = [
        "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
        "hotel", "india", "juliett", "kilo", "lima", "mike", "november",
        "oscar", "papa", "quebec", "romeo", "sierra", "tango",
    ]

    def _many(self, count):
        builder = self.builder()
        for index in range(count):
            word = self.WORDS[index % len(self.WORDS)] + "-" + self.WORDS[index // len(self.WORDS)]
            builder.assistant_tool("Bash", {"command": word}, minutes_ago=(count - index) * 2)
            builder.tool_result(f"failure of kind {word}", is_error=True,
                                minutes_ago=(count - index) * 2 - 1)
        builder.write()

    def test_budget_truncates_and_says_so(self):
        self._many(40)
        digest = self.extract(token_budget=100)
        self.assertTrue(digest.truncated)
        self.assertTrue(digest.dropped)
        self.assertLess(len(digest.episodes), 40)

    def test_generous_budget_keeps_everything(self):
        self._many(5)
        digest = self.extract(token_budget=ex.DEFAULT_TOKEN_BUDGET)
        self.assertFalse(digest.truncated)
        self.assertEqual(len(digest.episodes), 5)

    def test_newest_episodes_survive_truncation(self):
        builder = self.builder()
        builder.assistant_tool("Bash", {"command": "old"}, minutes_ago=100)
        builder.tool_result("ancient breakage in the linker", is_error=True, minutes_ago=99)
        builder.assistant_tool("Bash", {"command": "new"}, minutes_ago=3)
        builder.tool_result("recent breakage in the parser", is_error=True, minutes_ago=2)
        builder.write()

        full = self.extract(token_budget=ex.DEFAULT_TOKEN_BUDGET)
        self.assertEqual(len(full.episodes), 2)
        room_for_one = full.episodes[0].cost()

        digest = self.extract(token_budget=room_for_one)
        self.assertTrue(digest.truncated)
        self.assertEqual(len(digest.episodes), 1)
        self.assertIn("recent", digest.episodes[0].detail)


class RedactionTest(unittest.TestCase):
    def test_api_keys_are_removed(self):
        self.assertNotIn("sk-", ex.redact("key sk-abcdefghijklmnopqrstuvwx"))

    def test_github_tokens_are_removed(self):
        self.assertNotIn("ghp_", ex.redact("ghp_0123456789abcdefghij"))

    def test_aws_access_keys_are_removed(self):
        self.assertNotIn("AKIA", ex.redact("AKIAIOSFODNN7EXAMPLE"))

    def test_bearer_tokens_are_removed(self):
        out = ex.redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz")
        self.assertIn("[redacted]", out)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", out)

    def test_assigned_secrets_are_removed(self):
        self.assertNotIn("hunter2hunter2", ex.redact("password=hunter2hunter2"))

    def test_connection_string_credentials_are_removed(self):
        out = ex.redact("postgres://someuser:somepass@db.internal/app")
        self.assertNotIn("somepass", out)

    def test_private_keys_are_removed(self):
        out = ex.redact(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nsecretbytes\n-----END OPENSSH PRIVATE KEY-----"
        )
        self.assertNotIn("secretbytes", out)

    def test_jwts_are_removed(self):
        out = ex.redact("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NX0.dBjftJeZ4CVPmB92K")
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", out)

    def test_ordinary_prose_is_untouched(self):
        text = "run the build and check the output directory"
        self.assertEqual(ex.redact(text), text)


class RedactionReachesStoredEpisodesTest(ExtractorTestCase):
    def test_secrets_never_reach_the_digest(self):
        self.builder().assistant_tool(
            "Bash", {"command": "deploy"}, minutes_ago=5
        ).tool_result(
            "failed with token ghp_0123456789abcdefghij", is_error=True, minutes_ago=4
        ).write()
        serialised = json.dumps(self.extract().as_dict())
        self.assertNotIn("ghp_0123456789abcdefghij", serialised)


if __name__ == "__main__":
    unittest.main()
