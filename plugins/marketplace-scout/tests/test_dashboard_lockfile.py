"""Offline checks on the dashboard's package.json and committed package-lock.json.

They read the two files and nothing else: no network, no node_modules. The
dashboard has no test runner of its own, and `npm audit` needs the registry,
so this is what holds the zod advisory fix (#93) in CI.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = PLUGIN_ROOT / "skills" / "marketplace-scout" / "assets" / "dashboard"

# First release patched for GHSA-mrhx-c7xc-m3w5 (vulnerable range: < 4.6.6).
# The advisory lists no patched 3.x release.
ZOD_FIRST_PATCHED = (4, 6, 6)

REGISTRY = "https://registry.npmjs.org/"
DEPENDENCY_SECTIONS = ("dependencies", "peerDependencies", "optionalDependencies")

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_CARET = re.compile(r"\^(\d+)\.(\d+)\.(\d+)")


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(text)
    if match is None:
        raise ValueError(f"not a plain x.y.z version: {text!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def caret_floors(range_text: str) -> list[tuple[int, int, int]]:
    """Lower bounds of a range written as `^x.y.z`, or several joined by `||`.

    Any other form raises: a range these checks cannot read must fail the
    test, not pass it unexamined.
    """
    floors = []
    for part in range_text.split("||"):
        match = _CARET.fullmatch(part.strip())
        if match is None:
            raise ValueError(f"range form these checks do not read: {range_text!r}")
        floors.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return floors


def caret_accepts(range_text: str, version: tuple[int, int, int]) -> bool:
    # Caret semantics for a major of 1 or more, which is every zod range here.
    return any(
        floor[0] >= 1 and floor[0] == version[0] and floor <= version
        for floor in caret_floors(range_text)
    )


class TestRangeHelpers(unittest.TestCase):
    def test_caret_accepts(self) -> None:
        self.assertTrue(caret_accepts("^4.6.6", (4, 6, 7)))
        self.assertTrue(caret_accepts("^3.25.0 || ^4.0.0", (4, 6, 7)))
        self.assertFalse(caret_accepts("^3.25.0", (4, 6, 7)))
        self.assertFalse(caret_accepts("^4.6.6", (4, 6, 5)))
        self.assertFalse(caret_accepts("^4.6.6", (5, 0, 0)))

    def test_unread_range_form_raises(self) -> None:
        for text in (">=4.6.6", "4.x", "*", "~4.6.6", "^4.6", ""):
            with self.assertRaises(ValueError, msg=text):
                caret_floors(text)


class TestDashboardLockfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
        cls.lock = json.loads((DASHBOARD / "package-lock.json").read_text(encoding="utf-8"))
        cls.packages = cls.lock["packages"]

    def test_lockfile_root_matches_package_json(self) -> None:
        # `npm ci` refuses a lockfile whose root entry disagrees with
        # package.json, so a range edited without regenerating fails here first.
        root = self.packages[""]
        for section in ("dependencies", "devDependencies"):
            self.assertEqual(
                root.get(section, {}),
                self.manifest.get(section, {}),
                f"package-lock.json root {section} differ from package.json; regenerate "
                "with `npm install --package-lock-only --ignore-scripts`",
            )

    def test_locked_zod_is_patched(self) -> None:
        locked = parse_version(self.packages["node_modules/zod"]["version"])
        self.assertGreaterEqual(
            locked,
            ZOD_FIRST_PATCHED,
            "locked zod is inside the vulnerable range of GHSA-mrhx-c7xc-m3w5 (< 4.6.6)",
        )

    def test_zod_range_cannot_resolve_to_a_vulnerable_release(self) -> None:
        # The floor of the declared range is what a regenerated lockfile may
        # fall back to, so it has to be patched as well.
        declared = self.manifest["dependencies"]["zod"]
        for floor in caret_floors(declared):
            self.assertGreaterEqual(
                floor,
                ZOD_FIRST_PATCHED,
                f"package.json zod range {declared!r} admits a release below 4.6.6",
            )

    def test_one_zod_copy_that_every_dependent_accepts(self) -> None:
        copies = [path for path in self.packages if path.split("node_modules/")[-1] == "zod"]
        self.assertEqual(
            copies,
            ["node_modules/zod"],
            "a second zod copy is locked; some dependent does not accept the root one",
        )
        locked = parse_version(self.packages["node_modules/zod"]["version"])

        dependents = []
        for path, meta in self.packages.items():
            for section in DEPENDENCY_SECTIONS:
                declared = meta.get(section, {}).get("zod")
                if declared is None:
                    continue
                dependents.append(path or "<root>")
                self.assertTrue(
                    caret_accepts(declared, locked),
                    f"{path or '<root>'} {section} wants zod {declared!r}; "
                    f"the lockfile has {'.'.join(map(str, locked))}",
                )
        # The dashboard itself, plus at least the lint plugin that brings zod
        # in on its own. Zero dependents would mean the loop matched nothing.
        self.assertIn("<root>", dependents)
        self.assertGreater(len(dependents), 1, dependents)

    def test_every_package_resolves_from_the_public_registry(self) -> None:
        checked = 0
        for path, meta in self.packages.items():
            if not path:
                continue
            checked += 1
            resolved = meta.get("resolved", "")
            self.assertTrue(
                resolved.startswith(REGISTRY),
                f"{path} resolves from {resolved!r}, not {REGISTRY}",
            )
            self.assertTrue(
                meta.get("integrity", "").startswith("sha512-"),
                f"{path} has no sha512 integrity",
            )
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
