"""Marketplace consistency check — fixture trees, no subprocesses."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "check-marketplace.py"
_SPEC = importlib.util.spec_from_file_location("check_marketplace", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
cm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cm)


PLUGIN = "alpha"
VERSION = "1.2.0"
PLUGIN_JSON = Path("plugins") / PLUGIN / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = Path(".claude-plugin") / "marketplace.json"


def _skill_md(name: str = "demo") -> str:
    return (
        f"---\nname: {name}\ndescription: A {name} skill.\n---\n\n"
        f"# {name}\n\nDo the thing.\n"
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _readme(rows: list[tuple[str, str]]) -> str:
    lines = [
        "# Fixture",
        "",
        "## Plugins",
        "",
        "| Plugin | Version | Description |",
        "|--------|---------|-------------|",
    ]
    for name, version in rows:
        lines.append(
            f"| **[{name}](plugins/{name})** | {version} | A {name} plugin. |"
        )
    lines.append("")
    return "\n".join(lines)


def build_clean_tree(root: Path) -> None:
    """One plugin, a listed nested skill, an unlisted top-level skill."""
    plugin_dir = root / "plugins" / PLUGIN
    (plugin_dir / "skills" / "top").mkdir(parents=True)
    (plugin_dir / "skills" / "cat" / "nested").mkdir(parents=True)
    (plugin_dir / "skills" / "top" / "SKILL.md").write_text(
        _skill_md("top"), encoding="utf-8"
    )
    (plugin_dir / "skills" / "cat" / "nested" / "SKILL.md").write_text(
        _skill_md("nested"), encoding="utf-8"
    )
    _write_json(
        root / PLUGIN_JSON,
        {
            "name": PLUGIN,
            "version": VERSION,
            "description": "The alpha plugin.",
            "skills": ["./skills/cat/nested"],
        },
    )
    _write_json(
        root / MARKETPLACE_JSON,
        {
            "name": "test-marketplace",
            "description": "fixture",
            "owner": {"name": "Test"},
            "plugins": [
                {
                    "name": PLUGIN,
                    "source": f"./plugins/{PLUGIN}",
                    "version": VERSION,
                    "description": "The alpha plugin.",
                }
            ],
        },
    )
    (root / "README.md").write_text(
        _readme([(PLUGIN, VERSION)]), encoding="utf-8"
    )


def load_plugin(root: Path) -> tuple[dict, Path]:
    path = root / PLUGIN_JSON
    return json.loads(path.read_text(encoding="utf-8")), path


def load_marketplace(root: Path) -> tuple[dict, Path]:
    path = root / MARKETPLACE_JSON
    return json.loads(path.read_text(encoding="utf-8")), path


def add_plugin(
    root: Path,
    name: str,
    version: str = "1.0.0",
    *,
    listed_skills: list[str] | None = None,
    skill_dirs: list[str] | None = None,
) -> None:
    plugin_dir = root / "plugins" / name
    if skill_dirs is None:
        skill_dirs = [f"skills/{name}"]
    for rel in skill_dirs:
        d = plugin_dir / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(_skill_md(Path(rel).name), encoding="utf-8")
    payload: dict = {
        "name": name,
        "version": version,
        "description": f"The {name} plugin.",
    }
    if listed_skills is not None:
        payload["skills"] = listed_skills
    _write_json(plugin_dir / ".claude-plugin" / "plugin.json", payload)


class _TreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def findings(self) -> list[str]:
        return cm.collect_findings(self.root)

    def assert_finding(self, items: list[str], file_part: str, *needles: str) -> str:
        named = [f for f in items if file_part in f]
        self.assertTrue(
            named,
            f"no finding names {file_part!r}: {items}",
        )
        for needle in needles:
            hit = [f for f in named if needle in f]
            self.assertTrue(
                hit,
                f"no {file_part!r} finding contains {needle!r}: {named}; all={items}",
            )
            named = hit
        return named[0]


class CleanTreeTest(_TreeTest):
    def test_clean_tree_passes(self) -> None:
        build_clean_tree(self.root)
        self.assertEqual(self.findings(), [])


class VersionMismatchTest(_TreeTest):
    def test_plugin_json_version_differs_from_marketplace(self) -> None:
        build_clean_tree(self.root)
        data, path = load_marketplace(self.root)
        data["plugins"][0]["version"] = "9.9.9"
        _write_json(path, data)

        items = self.findings()
        self.assert_finding(
            items,
            ".claude-plugin/marketplace.json",
            PLUGIN,
            "9.9.9",
            "1.2.0",
        )

    def test_plugin_json_version_differs_from_readme_row(self) -> None:
        build_clean_tree(self.root)
        (self.root / "README.md").write_text(
            _readme([(PLUGIN, "0.0.1")]), encoding="utf-8"
        )

        items = self.findings()
        self.assert_finding(items, "README.md", PLUGIN, "0.0.1", "1.2.0")


class RegistrationTest(_TreeTest):
    def test_plugin_on_disk_not_registered(self) -> None:
        build_clean_tree(self.root)
        add_plugin(self.root, "beta")
        (self.root / "README.md").write_text(
            _readme([(PLUGIN, VERSION), ("beta", "1.0.0")]), encoding="utf-8"
        )

        items = self.findings()
        self.assert_finding(
            items,
            "plugins/beta/.claude-plugin/plugin.json",
            "beta",
            "not registered",
        )

    def test_registered_plugin_source_does_not_exist(self) -> None:
        build_clean_tree(self.root)
        data, path = load_marketplace(self.root)
        data["plugins"].append(
            {
                "name": "ghost",
                "source": "./plugins/ghost",
                "version": "1.0.0",
            }
        )
        _write_json(path, data)

        items = self.findings()
        self.assert_finding(
            items,
            ".claude-plugin/marketplace.json",
            "ghost",
            "./plugins/ghost",
        )
        self.assertTrue(
            any("does not exist" in f or "no .claude-plugin/plugin.json" in f for f in items),
            items,
        )


class SkillListTest(_TreeTest):
    def test_nested_skill_on_disk_missing_from_skills_array(self) -> None:
        build_clean_tree(self.root)
        orphan = self.root / "plugins" / PLUGIN / "skills" / "cat" / "orphan"
        orphan.mkdir(parents=True)
        (orphan / "SKILL.md").write_text(_skill_md("orphan"), encoding="utf-8")

        items = self.findings()
        self.assert_finding(
            items,
            str(PLUGIN_JSON),
            "skills/cat/orphan",
        )

    def test_listed_skill_path_with_no_skill_md(self) -> None:
        build_clean_tree(self.root)
        data, path = load_plugin(self.root)
        data["skills"].append("./skills/cat/missing")
        _write_json(path, data)

        items = self.findings()
        self.assert_finding(
            items,
            str(PLUGIN_JSON),
            "skills/cat/missing",
            "SKILL.md",
        )

    def test_unlisted_top_level_skill_is_not_a_finding(self) -> None:
        build_clean_tree(self.root)
        extra = self.root / "plugins" / PLUGIN / "skills" / "another"
        extra.mkdir()
        (extra / "SKILL.md").write_text(_skill_md("another"), encoding="utf-8")
        self.assertEqual(self.findings(), [])

    def test_skill_md_missing_frontmatter_fields(self) -> None:
        build_clean_tree(self.root)
        skill = self.root / "plugins" / PLUGIN / "skills" / "top" / "SKILL.md"
        skill.write_text("# top\n\nNo frontmatter.\n", encoding="utf-8")

        items = self.findings()
        self.assert_finding(
            items,
            "plugins/alpha/skills/top/SKILL.md",
            "frontmatter",
        )


class MalformedJsonTest(_TreeTest):
    def test_malformed_plugin_json(self) -> None:
        build_clean_tree(self.root)
        (self.root / PLUGIN_JSON).write_text("{not json\n", encoding="utf-8")

        items = self.findings()
        self.assert_finding(items, str(PLUGIN_JSON), "malformed JSON")

    def test_malformed_marketplace_json(self) -> None:
        build_clean_tree(self.root)
        (self.root / MARKETPLACE_JSON).write_text("{not json\n", encoding="utf-8")

        items = self.findings()
        self.assert_finding(
            items, ".claude-plugin/marketplace.json", "malformed JSON"
        )


class ReadmeTableTest(_TreeTest):
    def test_readme_row_for_plugin_that_does_not_exist(self) -> None:
        build_clean_tree(self.root)
        (self.root / "README.md").write_text(
            _readme([(PLUGIN, VERSION), ("ghost", "1.0.0")]),
            encoding="utf-8",
        )

        items = self.findings()
        self.assert_finding(items, "README.md", "ghost")

    def test_plugin_missing_from_readme_table(self) -> None:
        build_clean_tree(self.root)
        (self.root / "README.md").write_text(_readme([]), encoding="utf-8")

        items = self.findings()
        self.assert_finding(items, "README.md", PLUGIN)


class MarketplaceVersionRuleTest(unittest.TestCase):
    """Isolated tests for the function follow-up #37 will invert."""

    def test_mismatch_is_a_finding(self) -> None:
        got = cm.check_marketplace_plugin_version(
            "alpha",
            "1.2.0",
            {"name": "alpha", "version": "9.9.9"},
        )
        self.assertEqual(len(got), 1)
        self.assertIn(".claude-plugin/marketplace.json", got[0])
        self.assertIn("9.9.9", got[0])
        self.assertIn("1.2.0", got[0])

    def test_matching_version_is_not_a_finding(self) -> None:
        self.assertEqual(
            cm.check_marketplace_plugin_version(
                "alpha",
                "1.2.0",
                {"name": "alpha", "version": "1.2.0"},
            ),
            [],
        )

    def test_absent_marketplace_version_is_not_a_finding(self) -> None:
        self.assertEqual(
            cm.check_marketplace_plugin_version(
                "alpha",
                "1.2.0",
                {"name": "alpha", "source": "./plugins/alpha"},
            ),
            [],
        )


class MainCliTest(_TreeTest):
    def test_exit_zero_prints_ok(self) -> None:
        build_clean_tree(self.root)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cm.main(["--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertTrue(buf.getvalue().startswith("OK:"), buf.getvalue())

    def test_exit_one_prints_every_finding(self) -> None:
        build_clean_tree(self.root)
        data, path = load_marketplace(self.root)
        data["plugins"][0]["version"] = "9.9.9"
        _write_json(path, data)
        (self.root / "README.md").write_text(
            _readme([(PLUGIN, "0.0.1")]), encoding="utf-8"
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cm.main(["--root", str(self.root)])
        self.assertEqual(code, 1)
        out = buf.getvalue()
        self.assertIn("9.9.9", out)
        self.assertIn("0.0.1", out)
        self.assertGreaterEqual(out.strip().count("\n") + 1, 2)


if __name__ == "__main__":
    unittest.main()
