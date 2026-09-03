"""Directory resolution must not guess, and must not fail quietly."""

import json
import tempfile
import unittest
from pathlib import Path

from dream import claude_env


class SlugifyTest(unittest.TestCase):
    def test_path_separators_become_dashes(self):
        self.assertEqual(
            claude_env.slugify("/home/person/work/projects/thing"),
            "-home-person-work-projects-thing",
        )

    def test_dots_become_dashes(self):
        self.assertEqual(
            claude_env.slugify("/home/person/.hidden/workspace"),
            "-home-person--hidden-workspace",
        )

    def test_underscores_become_dashes(self):
        self.assertEqual(claude_env.slugify("/a/b_c"), "-a-b-c")

    def test_existing_dashes_survive(self):
        self.assertEqual(claude_env.slugify("/a/my-repo"), "-a-my-repo")


class ConfigDirTest(unittest.TestCase):
    def test_defaults_under_home(self):
        env = {"HOME": "/home/person"}
        self.assertEqual(claude_env.config_dir(env), Path("/home/person/.claude"))

    def test_honours_explicit_override(self):
        env = {"HOME": "/home/person", "CLAUDE_CONFIG_DIR": "/elsewhere/cfg"}
        self.assertEqual(claude_env.config_dir(env), Path("/elsewhere/cfg"))


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.cfg = self.home / ".claude"
        self.repo = self.tmp / "repo"
        (self.repo / ".claude").mkdir(parents=True)
        self.cfg.mkdir(parents=True)
        self.env = {"HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.cfg)}

    def tearDown(self):
        self._tmp.cleanup()

    def _write_settings(self, path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_default_layout_used_when_nothing_configured(self):
        found = claude_env.resolve(self.repo, self.env)
        expected = self.cfg / "projects" / claude_env.slugify(found.project_root) / "memory"
        self.assertEqual(found.memory_dir, expected)
        self.assertEqual(found.memory_source, "default layout")

    def test_auto_memory_directory_setting_wins_over_default(self):
        custom = self.tmp / "custom-memory"
        custom.mkdir()
        self._write_settings(
            self.cfg / "settings.json", {"autoMemoryDirectory": str(custom)}
        )
        found = claude_env.resolve(self.repo, self.env)
        self.assertEqual(found.memory_dir, custom)
        self.assertIn("autoMemoryDirectory", found.memory_source)
        self.assertTrue(found.memory_exists)

    def test_local_scope_beats_user_scope(self):
        self._write_settings(
            self.cfg / "settings.json", {"autoMemoryDirectory": str(self.tmp / "from-user")}
        )
        self._write_settings(
            self.repo / ".claude" / "settings.local.json",
            {"autoMemoryDirectory": str(self.tmp / "from-local")},
        )
        found = claude_env.resolve(self.repo, self.env)
        self.assertEqual(found.memory_dir, self.tmp / "from-local")
        self.assertIn("local", found.memory_source)

    def test_project_scope_beats_user_scope(self):
        self._write_settings(
            self.cfg / "settings.json", {"autoMemoryDirectory": str(self.tmp / "from-user")}
        )
        self._write_settings(
            self.repo / ".claude" / "settings.json",
            {"autoMemoryDirectory": str(self.tmp / "from-project")},
        )
        found = claude_env.resolve(self.repo, self.env)
        self.assertEqual(found.memory_dir, self.tmp / "from-project")

    def test_tilde_in_setting_expands_to_home(self):
        self._write_settings(
            self.cfg / "settings.json", {"autoMemoryDirectory": "~/somewhere/mem"}
        )
        found = claude_env.resolve(self.repo, self.env)
        self.assertEqual(found.memory_dir, self.home / "somewhere/mem")

    def test_malformed_settings_file_does_not_crash_resolution(self):
        (self.cfg / "settings.json").write_text("{not json", encoding="utf-8")
        found = claude_env.resolve(self.repo, self.env)
        self.assertEqual(found.memory_source, "default layout")

    def test_project_dir_name_override_is_honoured(self):
        env = dict(self.env, CLAUDE_CODE_PROJECT_DIR_NAME="shared-project")
        found = claude_env.resolve(self.repo, env)
        self.assertEqual(found.project_dir, self.cfg / "projects" / "shared-project")

    def test_missing_memory_directory_is_reported_not_assumed_empty(self):
        found = claude_env.resolve(self.repo, self.env)
        self.assertFalse(found.memory_exists)


if __name__ == "__main__":
    unittest.main()
