"""scripts/evict-plugin-cache.sh — guarded eviction of one cached plugin version.

Every test points CLAUDE_CONFIG_DIR and HOME at a temp directory, so neither
the real plugin cache nor the real home directory is ever a target.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "evict-plugin-cache.sh"
MARKETPLACE = "brightopsai-plugins-official"

# alpha/1.0.0 as seeded: plugin.json, skills/, skills/demo/, skills/demo/SKILL.md.
ALPHA_1_0_0 = "4 entries beneath it, 2 of them regular files"


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


class TestEvictPluginCache(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Resolved, because the script prints symlink-free paths and the system
        # temp directory is itself behind a symlink on macOS.
        self.base = Path(os.path.realpath(tmp.name))
        self.home = self.base / "home"
        self.config = self.base / "config"
        self.outside = self.base / "outside"
        self.cache = self.config / "plugins" / "cache" / MARKETPLACE
        self._seed(self.cache)
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("keep\n", encoding="utf-8")
        self.home.mkdir()
        self.before = _files(self.base)

    @staticmethod
    def _seed(cache: Path) -> None:
        for rel in (
            "alpha/1.0.0/plugin.json",
            "alpha/1.0.0/skills/demo/SKILL.md",
            "alpha/1.1.0/plugin.json",
            "beta/1.0.0/plugin.json",
        ):
            path = cache / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")

    def _run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        full_env = os.environ.copy()
        full_env.pop("DRY_RUN", None)
        full_env["HOME"] = str(self.home)
        full_env["CLAUDE_CONFIG_DIR"] = str(self.config)
        # The realpath fallback runs python3; keep its bytecode cache out of
        # the sandbox so the before/after file lists stay comparable.
        full_env["PYTHONDONTWRITEBYTECODE"] = "1"
        full_env.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=full_env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _assert_refused(
        self, result: subprocess.CompletedProcess[str], status: int = 1
    ) -> None:
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertEqual(_files(self.base), self.before, "a refused run deleted files")

    def test_refuses_missing_and_empty_arguments(self) -> None:
        for args in ((), ("alpha",), ("", "1.0.0"), ("alpha", ""), ("", ""), ("alpha", "1.0.0", "extra")):
            for dry in ((), ("--dry-run",)):
                with self.subTest(args=args, dry=dry):
                    self._assert_refused(self._run(*dry, *args), status=2)

    def test_refuses_traversal_and_malformed_arguments(self) -> None:
        cases = (
            ("../..", "1.0.0"),
            ("alpha", "../.."),
            ("..", ".."),
            ("alpha/../beta", "1.0.0"),
            ("alpha", "1.0.0/../../beta"),
            (str(self.outside), "1.0.0"),
            ("Alpha", "1.0.0"),
            ("alpha", "1.0"),
            # Not SemVer 2.0.0: leading zeros, empty identifiers.
            ("alpha", "01.0.0"),
            ("alpha", "1.02.0"),
            ("alpha", "1.0.003"),
            ("alpha", "1.0.0-01"),
            ("alpha", "1.0.0-"),
            ("alpha", "1.0.0+"),
            ("alpha", "1.0.0-rc..1"),
            ("alpha", "v1.0.0"),
            ("alpha", "latest"),
            ("alpha", "*"),
            ("*", "1.0.0"),
            ("-rf", "1.0.0"),
            ("alpha", "1.0.0\n"),
        )
        for args in cases:
            with self.subTest(args=args):
                result = self._run(*args)
                self._assert_refused(result, status=2)
                self.assertIn("Refusing", result.stderr)

    def test_dry_run_prints_target_and_count_and_deletes_nothing(self) -> None:
        target = self.cache / "alpha" / "1.0.0"
        for args, env in (
            (("--dry-run", "alpha", "1.0.0"), {}),
            (("alpha", "1.0.0"), {"DRY_RUN": "1"}),
            (("alpha", "1.0.0"), {"DRY_RUN": "true"}),
        ):
            with self.subTest(args=args, env=env):
                result = self._run(*args, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"would delete {target} ({ALPHA_1_0_0})", result.stdout)
                self.assertEqual(_files(self.base), self.before)

    def test_eviction_removes_only_the_target(self) -> None:
        target = self.cache / "alpha" / "1.0.0"
        result = self._run("alpha", "1.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(
            _files(self.base),
            [f for f in self.before if "alpha/1.0.0/" not in f],
        )
        # The warning names the target and the consequence.
        self.assertIn("WARNING", result.stderr)
        self.assertIn(f"DELETES {target} ({ALPHA_1_0_0})", result.stderr)

    def test_warning_comes_before_the_delete(self) -> None:
        # A stub rm announces itself on stderr and then deletes for real, so
        # the captured stream shows which came first.
        real_rm = shutil.which("rm")
        self.assertIsNotNone(real_rm)
        stubs = self.base / "stubs"
        stubs.mkdir()
        (stubs / "rm").write_text(
            f'#!/bin/sh\necho "STUB-RM $*" >&2\nexec "{real_rm}" "$@"\n', encoding="utf-8"
        )
        (stubs / "rm").chmod(0o755)
        path = str(stubs) + os.pathsep + os.environ["PATH"]
        target = self.cache / "alpha" / "1.0.0"

        for args in (("--dry-run", "alpha", "1.0.0"), ("../..", "1.0.0"), ("alpha", "9.9.9")):
            with self.subTest(args=args):
                self.assertNotIn("STUB-RM", self._run(*args, PATH=path).stderr)

        result = self._run("alpha", "1.0.0", PATH=path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        lines = result.stderr.splitlines()
        warned = [i for i, line in enumerate(lines) if line.startswith("WARNING:") and f"DELETES {target}" in line]
        deleted = [i for i, line in enumerate(lines) if line == f"STUB-RM -rf -- {target}"]
        self.assertEqual(len(warned), 1, result.stderr)
        self.assertEqual(len(deleted), 1, result.stderr)
        self.assertLess(warned[0], deleted[0], "the warning was printed after the delete")

    def test_count_is_exact_and_covers_everything_removed(self) -> None:
        # A newline in a file name must not count twice, and symlinks and
        # directories are removed too, so they are counted and labelled.
        target = self.cache / "alpha" / "1.0.0"
        (target / "odd\nname.txt").write_text("x\n", encoding="utf-8")
        os.symlink("plugin.json", target / "link")
        (target / "empty-dir").mkdir()
        result = self._run("--dry-run", "alpha", "1.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(7 entries beneath it, 3 of them regular files)", result.stdout)

    def test_semver_prerelease_and_build_versions_are_accepted(self) -> None:
        for version in ("2.0.0-rc.1", "1.0.0-rc--test", "1.0.0+build.01", "1.0.0-0a.x-y+b-1", "0.0.0"):
            with self.subTest(version=version):
                path = self.cache / "alpha" / version / "plugin.json"
                path.parent.mkdir(parents=True)
                path.write_text("x\n", encoding="utf-8")
                result = self._run("alpha", version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(path.parent.exists())
                self.assertEqual(_files(self.base), self.before)

    def test_absent_version_is_a_no_op(self) -> None:
        result = self._run("alpha", "9.9.9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to evict", result.stdout)
        self.assertEqual(_files(self.base), self.before)

    def test_missing_cache_root_is_a_no_op(self) -> None:
        empty = self.base / "empty-config"
        empty.mkdir()
        result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(empty))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to evict", result.stdout)
        self.assertEqual(_files(self.base), self.before)

    def test_refuses_a_symlinked_version_directory(self) -> None:
        os.symlink(self.outside, self.cache / "alpha" / "3.0.0")
        result = self._run("alpha", "3.0.0")
        self._assert_refused(result)
        self.assertIn("WARNING", result.stderr)
        self.assertIn("Unsupported", result.stderr)
        self.assertIn("nothing was deleted", result.stderr)
        self.assertNotIn("points at", result.stderr)

    def test_refuses_a_cache_root_that_leads_out_of_the_config_directory(self) -> None:
        # Each case replaces one directory on the way to the cache root with a
        # symlink to a look-alike tree outside the config directory.
        for depth, label in ((0, "marketplace"), (1, "cache"), (2, "plugins")):
            config = self.base / f"config-{label}"
            real = self.cache.parents[depth - 1] if depth else self.cache
            link = config / real.relative_to(self.config)
            decoy = self.outside / label
            # The decoy mirrors what the link replaces, down to alpha/1.0.0.
            victim = decoy / self.cache.relative_to(real) / "alpha" / "1.0.0"
            victim.mkdir(parents=True)
            (victim / "precious.txt").write_text("keep\n", encoding="utf-8")
            link.parent.mkdir(parents=True)
            os.symlink(decoy, link)
            self.before = _files(self.base)
            for dry in ((), ("--dry-run",)):
                with self.subTest(symlinked=label, dry=dry):
                    result = self._run(*dry, "alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(config))
                    self._assert_refused(result)
                    self.assertIn("WARNING: cache root", result.stderr)
                    self.assertIn("DELETES", result.stderr)
                    self.assertIn("Refusing", result.stderr)
                    self.assertNotIn("would delete", result.stdout)
                    self.assertTrue((victim / "precious.txt").is_file())

    def test_config_directory_itself_may_be_a_symlink(self) -> None:
        # ~/.claude kept in a dotfiles checkout is legitimate. The anchor is
        # the resolved config directory, so this still evicts.
        link = self.base / "config-link"
        os.symlink(self.config, link)
        result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(link))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cache / "alpha" / "1.0.0").exists())
        self.assertTrue((self.cache / "alpha" / "1.1.0" / "plugin.json").is_file())

    def test_refuses_a_plugin_directory_that_resolves_outside_the_cache(self) -> None:
        elsewhere = self.outside / "gamma" / "1.0.0"
        elsewhere.mkdir(parents=True)
        (elsewhere / "precious.txt").write_text("keep\n", encoding="utf-8")
        os.symlink(self.outside / "gamma", self.cache / "gamma")
        self.before = _files(self.base)
        result = self._run("gamma", "1.0.0")
        self._assert_refused(result)
        self.assertIn("WARNING", result.stderr)
        self.assertIn("DELETES", result.stderr)
        self.assertIn("Refusing", result.stderr)

    def test_refuses_a_plugin_directory_aliased_to_another_plugin(self) -> None:
        os.symlink(self.cache / "beta", self.cache / "delta")
        result = self._run("delta", "1.0.0")
        self._assert_refused(result)

    # -- capitalization, and links checked directly -------------------------

    def _case_insensitive(self) -> bool:
        probe = self.base / "CaseProbe"
        probe.mkdir()
        try:
            return (self.base / "caseprobe").is_dir()
        finally:
            probe.rmdir()

    def _resolver(self, body: str) -> str:
        """A PATH whose `realpath` is a stand-in running `body` on its argument.

        `body` is Python that sees the argument as `arg` and the truly
        resolved path as `p`, and leaves the answer in `p`.
        """
        stubs = self.base / "resolver"
        stubs.mkdir()
        self.addCleanup(shutil.rmtree, stubs, ignore_errors=True)
        program = f"import os, sys\narg = sys.argv[1]\np = os.path.realpath(arg)\n{body}\nprint(p)\n"
        self.assertNotIn("'", program)
        (stubs / "realpath").write_text(
            f'#!/bin/sh\n[ "$1" = "--" ] && shift\nexec "{sys.executable}" -c \'{program}\' "$1"\n',
            encoding="utf-8",
        )
        (stubs / "realpath").chmod(0o755)
        self.before = _files(self.base)
        return str(stubs) + os.pathsep + os.environ["PATH"]

    def test_cache_directories_capitalised_on_disk(self) -> None:
        # A case-insensitive filesystem finds Plugins/Cache when asked for
        # plugins/cache, and a resolver reports the capitalization on disk.
        # That is the managed cache, not a directory outside it.
        config = self.base / "config-caps"
        cache = config / "Plugins" / "Cache" / MARKETPLACE
        self._seed(cache)
        self.before = _files(self.base)
        target = cache / "alpha" / "1.0.0"

        if not self._case_insensitive():
            # Here plugins/cache does not exist at all, so there is nothing to
            # find and nothing may be deleted.
            result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(config))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing to evict", result.stdout)
            self.assertEqual(_files(self.base), self.before)
            return

        dry = self._run("--dry-run", "alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("would delete", dry.stdout)
        self.assertIn(f"({ALPHA_1_0_0})", dry.stdout)
        self.assertEqual(_files(self.base), self.before)

        result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(
            _files(self.base),
            [f for f in self.before if "config-caps/Plugins/Cache" not in f or "alpha/1.0.0/" not in f],
        )

    def test_resolver_capitalisation_alone_is_not_a_refusal(self) -> None:
        # The same comparison on any filesystem: the resolver answers with
        # Plugins/Cache for the plugins/cache it was asked about.
        path = self._resolver('p = p.replace("/plugins/cache/", "/Plugins/Cache/")')
        target = self.cache / "alpha" / "1.0.0"

        dry = self._run("--dry-run", "alpha", "1.0.0", PATH=path)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(f"would delete {target} ({ALPHA_1_0_0})", dry.stdout)
        self.assertEqual(_files(self.base), self.before)

        result = self._run("alpha", "1.0.0", PATH=path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(_files(self.base), [f for f in self.before if "alpha/1.0.0/" not in f])

    def test_resolver_naming_another_directory_is_still_refused(self) -> None:
        # Only capitalization is forgiven, and only below the config
        # directory: another name, or another config directory, is not it.
        for label, body in (
            ("another cache name", 'p = p.replace("/plugins/cache/", "/plugins/cache2/")'),
            ("another plugin", 'p = p.replace("/alpha/", "/beta/")'),
            ("another version", 'p = p.replace("/1.0.0", "/1.1.0")'),
            ("a longer path", 'p = p + "/extra" if "/plugins/cache/" in p else p'),
            ("config directory in other capitals", 'p = p.replace("/config/", "/CONFIG/")'),
        ):
            for dry in ((), ("--dry-run",)):
                with self.subTest(resolver=label, dry=dry):
                    path = self._resolver(body)
                    result = self._run(*dry, "alpha", "1.0.0", PATH=path)
                    self._assert_refused(result)
                    self.assertIn("WARNING", result.stderr)
                    self.assertIn("DELETES", result.stderr)
                    self.assertIn("Refusing", result.stderr)
                    self.assertNotIn("would delete", result.stdout)
                    shutil.rmtree(self.base / "resolver")

    def test_symlinked_components_are_refused_whatever_the_resolver_says(self) -> None:
        # The links are looked at directly. A resolver that resolves nothing
        # (it echoes its argument) must not turn a symlinked managed directory
        # into a delete outside the cache.
        path = self._resolver("p = arg")
        cases = []
        for depth, label in ((0, "marketplace"), (1, "cache"), (2, "plugins")):
            config = self.base / f"config-{label}"
            real = self.cache.parents[depth - 1] if depth else self.cache
            link = config / real.relative_to(self.config)
            decoy = self.outside / label
            victim = decoy / self.cache.relative_to(real) / "alpha" / "1.0.0"
            victim.mkdir(parents=True)
            link.parent.mkdir(parents=True)
            os.symlink(decoy, link)
            cases.append((label, config, "alpha", victim))
        # The plugin directory, inside an otherwise real cache.
        victim = self.outside / "gamma" / "1.0.0"
        victim.mkdir(parents=True)
        os.symlink(self.outside / "gamma", self.cache / "gamma")
        cases.append(("plugin", self.config, "gamma", victim))
        for _, _, _, victim in cases:
            (victim / "precious.txt").write_text("keep\n", encoding="utf-8")
        self.before = _files(self.base)

        for label, config, plugin, victim in cases:
            for dry in ((), ("--dry-run",)):
                with self.subTest(symlinked=label, dry=dry):
                    result = self._run(*dry, plugin, "1.0.0", CLAUDE_CONFIG_DIR=str(config), PATH=path)
                    self._assert_refused(result)
                    self.assertIn("WARNING", result.stderr)
                    self.assertIn("symlink", result.stderr)
                    self.assertIn("DELETES", result.stderr)
                    self.assertIn("Refusing", result.stderr)
                    self.assertNotIn("would delete", result.stdout)
                    self.assertTrue((victim / "precious.txt").is_file())

    def test_symlink_to_a_differently_capitalised_directory_is_refused(self) -> None:
        # plugins -> Plugins resolves to a path that differs from the expected
        # one in capitalization only. It is still a link out of the managed
        # chain, into a directory this script was not pointed at.
        if self._case_insensitive():
            self.skipTest(
                "plugins and Plugins are one name on this filesystem, so the link cannot be made; "
                "test_symlinked_components_are_refused_whatever_the_resolver_says covers the link check"
            )
        config = self.base / "config-variant"
        victim = config / "Plugins" / "cache" / MARKETPLACE / "alpha" / "1.0.0"
        victim.mkdir(parents=True)
        (victim / "precious.txt").write_text("keep\n", encoding="utf-8")
        os.symlink("Plugins", config / "plugins")
        self.before = _files(self.base)
        for dry in ((), ("--dry-run",)):
            with self.subTest(dry=dry):
                result = self._run(*dry, "alpha", "1.0.0", CLAUDE_CONFIG_DIR=str(config))
                self._assert_refused(result)
                self.assertIn("WARNING: cache root", result.stderr)
                self.assertIn("Refusing", result.stderr)
                self.assertTrue((victim / "precious.txt").is_file())

    def test_default_config_dir_is_under_home(self) -> None:
        cache = self.home / ".claude" / "plugins" / "cache" / MARKETPLACE
        self._seed(cache)
        before = _files(self.base)
        result = self._run("alpha", "1.0.0", CLAUDE_CONFIG_DIR="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((cache / "alpha" / "1.0.0").exists())
        self.assertEqual(
            _files(self.base),
            [f for f in before if "home/.claude/" not in f or "alpha/1.0.0/" not in f],
        )

    def test_works_without_a_realpath_binary(self) -> None:
        # PATH holds only what the script needs, minus realpath, so the
        # python3 fallback is the code path under test.
        bindir = self.base / "bin"
        bindir.mkdir()
        for tool in ("bash", "find", "wc", "tr", "rm"):
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"{tool} is required")
            os.symlink(str(found), bindir / tool)
        wrapper = bindir / "python3"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        elsewhere = self.outside / "gamma" / "1.0.0"
        elsewhere.mkdir(parents=True)
        (elsewhere / "precious.txt").write_text("keep\n", encoding="utf-8")
        os.symlink(self.outside / "gamma", self.cache / "gamma")
        self.before = _files(self.base)

        refused = self._run("gamma", "1.0.0", PATH=str(bindir))
        self._assert_refused(refused)
        self.assertIn("Refusing", refused.stderr)

        result = self._run("alpha", "1.0.0", PATH=str(bindir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.cache / "alpha" / "1.0.0").exists())
        self.assertTrue((self.cache / "alpha" / "1.1.0" / "plugin.json").is_file())


if __name__ == "__main__":
    unittest.main()
