"""Tests for skills/1password-secrets/scripts/t3_op_env_sync.py.

Every run points T3CODE_HOME and T3_OP_ENV into a temporary directory, so the real
~/.t3 and ~/.config are never read or written.
"""
import fcntl
import glob
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PLUGIN_DIR, "skills", "1password-secrets", "scripts", "t3_op_env_sync.py")

REF_A = "op://vault/item/field"
REF_B = "op://vault/other/token"


class SyncTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.t3_home = os.path.join(self.root, "t3")
        self.userdata = os.path.join(self.t3_home, "userdata")
        os.makedirs(self.userdata)
        self.settings_path = os.path.join(self.userdata, "settings.json")
        self.op_env = os.path.join(self.root, "op.env")

    def write_settings(self, data):
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh)

    def write_op_env(self, text):
        with open(self.op_env, "w", encoding="utf-8") as fh:
            fh.write(text)

    @staticmethod
    def read_bytes(path):
        with open(path, "rb") as fh:
            return fh.read()

    def read_settings(self):
        with open(self.settings_path, encoding="utf-8") as fh:
            return json.load(fh)

    def backups(self):
        return glob.glob(self.settings_path + ".bak-*")

    def run_sync(self, *args):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": self.root,
            "T3CODE_HOME": self.t3_home,
            "T3_OP_ENV": self.op_env,
        }
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, env=env, check=False,
        )

    def assert_fails(self, result, fragment):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(fragment, result.stderr)


class WriteTests(SyncTestCase):
    def test_references_written_for_each_provider(self):
        self.write_op_env(f"# comment\n\nAPI_KEY={REF_A}\nOTHER = {REF_B}\n")
        self.write_settings({"providerInstances": {"alpha": {}, "beta": {"environment": []}}})
        result = self.run_sync("alpha", "beta")
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = self.read_settings()
        for provider in ("alpha", "beta"):
            env = settings["providerInstances"][provider]["environment"]
            self.assertEqual([v["name"] for v in env], ["API_KEY", "OTHER"])
            self.assertEqual(
                env[0],
                {"name": "API_KEY", "value": "", "sensitive": True,
                 "secret": {"provider": "onepassword", "reference": REF_A}},
            )
            self.assertEqual(env[1]["secret"]["reference"], REF_B)

    def test_unnamed_provider_is_untouched(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}, "beta": {}}})
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        self.assertNotIn("environment", self.read_settings()["providerInstances"]["beta"])

    def test_unmanaged_variables_kept(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        literal = {"name": "PLAIN", "value": "1", "sensitive": False}
        other = {"name": "VIA_OTHER", "value": "", "sensitive": True,
                 "secret": {"provider": "elsewhere", "reference": "x"}}
        self.write_settings({"providerInstances": {"alpha": {"environment": [literal, other]}}})
        result = self.run_sync("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        env = self.read_settings()["providerInstances"]["alpha"]["environment"]
        self.assertEqual(env[:2], [literal, other])
        self.assertEqual(env[2]["name"], "API_KEY")
        self.assertIn("alpha: 1 references, 0 removed, 2 other variables kept", result.stdout)

    def test_managed_variables_replaced_in_place_not_duplicated(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        before = {"name": "BEFORE", "value": "1", "sensitive": False}
        stale = {"name": "API_KEY", "value": "", "sensitive": True,
                 "secret": {"provider": "onepassword", "reference": REF_B}}
        after = {"name": "AFTER", "value": "2", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [before, stale, after]}}})
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        env = self.read_settings()["providerInstances"]["alpha"]["environment"]
        self.assertEqual([v["name"] for v in env], ["BEFORE", "API_KEY", "AFTER"])
        self.assertEqual(env[1]["secret"]["reference"], REF_A)
        # A second run gives the same result.
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        self.assertEqual(self.read_settings()["providerInstances"]["alpha"]["environment"], env)

    def test_existing_secret_provider_left_as_is(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        existing = {"kind": "one_password", "label": "Mine", "config": {"account": "existing.example"}}
        self.write_settings(
            {"secretProviders": {"onepassword": existing}, "providerInstances": {"alpha": {}}}
        )
        self.assertEqual(self.run_sync("--account=new.example", "alpha").returncode, 0)
        self.assertEqual(self.read_settings()["secretProviders"]["onepassword"], existing)

    def test_account_used_for_new_secret_provider(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assertEqual(self.run_sync("--account=team.example", "alpha").returncode, 0)
        provider = self.read_settings()["secretProviders"]["onepassword"]
        self.assertEqual(provider["kind"], "one_password")
        self.assertEqual(provider["config"], {"account": "team.example"})

    def test_default_account(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        provider = self.read_settings()["secretProviders"]["onepassword"]
        self.assertEqual(provider["config"], {"account": "my.1password.com"})

    def test_dry_run_writes_nothing(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        before = self.read_bytes(self.settings_path)
        result = self.run_sync("--dry-run", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry run: nothing written", result.stdout)
        self.assertIn("alpha: 1 references", result.stdout)
        self.assertEqual(self.read_bytes(self.settings_path), before)
        self.assertEqual(self.backups(), [])
        self.assertEqual(sorted(os.listdir(self.userdata)), ["settings.json"])

    def test_backup_created_with_original_content(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        before = self.read_bytes(self.settings_path)
        result = self.run_sync("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.read_bytes(backups[0]), before)
        self.assertIn(backups[0], result.stdout)

    def test_file_mode_preserved(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        os.chmod(self.settings_path, 0o640)
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        self.assertEqual(stat.S_IMODE(os.stat(self.settings_path).st_mode), 0o640)

    def test_no_temp_files_left_behind(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        leftovers = [n for n in os.listdir(self.userdata) if n.startswith(".settings-")]
        self.assertEqual(leftovers, [])

    def test_output_never_prints_references(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        result = self.run_sync("alpha")
        self.assertNotIn(REF_A, result.stdout + result.stderr)


class FailureTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})

    def assert_nothing_written(self):
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.read_settings(), {"providerInstances": {"alpha": {}}})

    def test_missing_references_file(self):
        os.unlink(self.op_env)
        self.assert_fails(self.run_sync("alpha"), "cannot read references file")
        self.assert_nothing_written()

    def test_missing_settings_file(self):
        os.unlink(self.settings_path)
        self.assert_fails(self.run_sync("alpha"), "cannot read")

    def test_bad_json(self):
        self.write_settings("{not json")
        self.assert_fails(self.run_sync("alpha"), "is not valid JSON")

    def test_settings_not_an_object(self):
        self.write_settings("[]")
        self.assert_fails(self.run_sync("alpha"), "does not hold a JSON object")

    def test_no_provider_instances(self):
        self.write_settings({})
        self.assert_fails(self.run_sync("alpha"), "has no providerInstances")

    def test_unknown_provider(self):
        result = self.run_sync("missing")
        self.assert_fails(result, "no provider instance named 'missing'")
        self.assertIn("alpha", result.stderr)
        self.assert_nothing_written()

    def test_literal_value_in_place_of_reference(self):
        self.write_op_env("API_KEY=literal-value\n")
        result = self.run_sync("alpha")
        self.assert_fails(result, "not a reference T3 Code accepts")
        self.assertNotIn("literal-value", result.stderr)
        self.assert_nothing_written()

    def test_duplicate_name(self):
        self.write_op_env(f"API_KEY={REF_A}\nAPI_KEY={REF_B}\n")
        self.assert_fails(self.run_sync("alpha"), "defined twice")

    def test_bad_variable_name(self):
        self.write_op_env(f"1BAD={REF_A}\n")
        self.assert_fails(self.run_sync("alpha"), "the variable name is not valid")

    def test_line_without_equals(self):
        self.write_op_env("API_KEY\n")
        self.assert_fails(self.run_sync("alpha"), "expected NAME=op://vault/item/field")

    def test_empty_references_file(self):
        self.write_op_env("# only a comment\n\n")
        self.assert_fails(self.run_sync("alpha"), "holds no references")

    def test_unknown_option(self):
        self.assert_fails(self.run_sync("--bogus", "alpha"), "unknown option --bogus")

    def test_no_providers_prints_usage(self):
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stderr)

    def test_bad_account(self):
        self.assert_fails(self.run_sync("--account=has space", "alpha"), "--account needs")
        self.assert_fails(self.run_sync("--account=", "alpha"), "--account needs")

    def test_environment_not_a_list(self):
        self.write_settings({"providerInstances": {"alpha": {"environment": {"x": 1}}}})
        self.assert_fails(self.run_sync("alpha"), "environment is not a list")


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)

def onepassword_variable(name, ref):
    return {"name": name, "value": "", "sensitive": True,
            "secret": {"provider": "onepassword", "reference": ref}}

class OwnershipTests(SyncTestCase):
    def env_of(self, provider="alpha"):
        return self.read_settings()["providerInstances"][provider]["environment"]

    def test_other_onepassword_references_not_in_the_file_are_kept(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        other = onepassword_variable("HAND_ADDED", REF_B)
        self.write_settings({"providerInstances": {"alpha": {"environment": [other]}}})
        result = self.run_sync("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([v["name"] for v in self.env_of()], ["HAND_ADDED", "API_KEY"])
        self.assertEqual(self.env_of()[0], other)

    def test_remove_drops_a_managed_variable_only(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        literal = {"name": "PLAIN", "value": "1", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [
            onepassword_variable("GONE", REF_B), onepassword_variable("OLD", REF_B), literal]}}})
        result = self.run_sync("--remove=GONE", "--remove=OLD", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([v["name"] for v in self.env_of()], ["PLAIN", "API_KEY"])
        self.assertIn("2 removed", result.stdout)

    def test_remove_works_with_missing_or_empty_references_file(self):
        for prepare in (lambda: os.unlink(self.op_env), lambda: self.write_op_env("# nothing\n")):
            with self.subTest():
                self.write_op_env("")
                self.write_settings({"providerInstances": {"alpha": {"environment": [
                    onepassword_variable("GONE", REF_B)]}}})
                prepare()
                result = self.run_sync("--remove=GONE", "alpha")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.env_of(), [])
                self.assertNotIn("secretProviders", self.read_settings())

    def test_remove_refuses_a_variable_it_does_not_manage(self):
        self.write_op_env("")
        literal = {"name": "PLAIN", "value": "keep-this-value", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [literal]}}})
        result = self.run_sync("--remove=PLAIN", "alpha")
        self.assert_fails(result, "PLAIN is not a onepassword reference")
        self.assertNotIn("keep-this-value", result.stderr)
        self.assertEqual(self.env_of(), [literal])

    def test_remove_wins_over_a_line_of_the_same_name_in_the_references_file(self):
        self.write_op_env(f"API_KEY={REF_A}\nOTHER={REF_B}\n")
        self.write_settings({"providerInstances": {"alpha": {"environment": [
            onepassword_variable("API_KEY", REF_B)]}}})
        result = self.run_sync("--remove=API_KEY", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_of(), [onepassword_variable("OTHER", REF_B)])
        self.assertIn("1 removed", result.stdout)

    def test_remove_all_removes_every_name_in_the_references_file(self):
        self.write_op_env(f"API_KEY={REF_A}\nOTHER={REF_B}\n")
        literal = {"name": "PLAIN", "value": "1", "sensitive": False}
        hand_added = onepassword_variable("HAND_ADDED", REF_B)
        settings = {"providerInstances": {
            "alpha": {"environment": [onepassword_variable("API_KEY", REF_A), literal,
                                      onepassword_variable("OTHER", REF_B), hand_added]},
            "beta": {"environment": [onepassword_variable("OTHER", REF_B)]},
            "gamma": {}}}
        self.write_settings(settings)
        result = self.run_sync("--remove-all", "alpha", "beta", "gamma")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_of("alpha"), [literal, hand_added])
        self.assertEqual(self.env_of("beta"), [])
        self.assertEqual(self.env_of("gamma"), [])
        self.assertNotIn("secretProviders", self.read_settings())
        self.assertIn("2 removed", result.stdout.splitlines()[0])

    def test_remove_all_with_a_missing_references_file_removes_nothing(self):
        self.write_settings({"providerInstances": {"alpha": {"environment": [
            onepassword_variable("KEEP", REF_A)]}}})
        result = self.run_sync("--remove-all", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_of(), [onepassword_variable("KEEP", REF_A)])

    def test_remove_all_still_validates_the_references_file(self):
        self.write_op_env("API_KEY=MARKER-LITERAL\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        result = self.run_sync("--remove-all", "alpha")
        self.assert_fails(result, "op.env:1:")
        self.assertNotIn("MARKER", result.stderr)

    def test_remove_all_refuses_a_same_named_variable_it_does_not_manage(self):
        self.write_op_env(f"PLAIN={REF_A}\n")
        literal = {"name": "PLAIN", "value": "keep-this-value", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [literal]}}})
        result = self.run_sync("--remove-all", "alpha")
        self.assert_fails(result, "PLAIN is not a onepassword reference")
        self.assertEqual(self.env_of(), [literal])

    def test_remove_needs_a_valid_name(self):
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assert_fails(self.run_sync("--remove=1bad", "alpha"), "--remove needs a valid variable name")

    def test_collision_with_a_literal_value_stops(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        literal = {"name": "API_KEY", "value": "planted-literal", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [literal]}}})
        result = self.run_sync("alpha")
        self.assert_fails(result, "API_KEY already exists as a literal value")
        self.assertNotIn("planted-literal", result.stdout + result.stderr)
        self.assertEqual(self.env_of(), [literal])
        self.assertEqual(self.backups(), [])

    def test_collision_with_another_secret_provider_stops(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        other = {"name": "API_KEY", "value": "", "sensitive": True,
                 "secret": {"provider": "elsewhere", "reference": "planted-reference"}}
        self.write_settings({"providerInstances": {"alpha": {"environment": [other]}}})
        result = self.run_sync("alpha")
        self.assert_fails(result, "API_KEY already exists as a reference through another secret provider")
        self.assertNotIn("planted-reference", result.stdout + result.stderr)
        self.assertEqual(self.env_of(), [other])

    def test_replace_overwrites_a_collision(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        literal = {"name": "API_KEY", "value": "planted-literal", "sensitive": False}
        self.write_settings({"providerInstances": {"alpha": {"environment": [literal]}}})
        result = self.run_sync("--replace", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_of(), [onepassword_variable("API_KEY", REF_A)])

class ShowTargetTests(SyncTestCase):
    def test_reports_the_target_and_writes_nothing(self):
        self.write_settings({"providerInstances": {"beta": {}, "alpha": {}},
                             "secretProviders": {"onepassword": {}}})
        before = sorted(os.listdir(self.userdata))
        result = self.run_sync("--show-target")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"settings: {os.path.realpath(self.settings_path)}", result.stdout)
        self.assertIn("exists: yes", result.stdout)
        self.assertIn("provider instances: alpha, beta", result.stdout)
        self.assertIn("secret provider onepassword: yes", result.stdout)
        self.assertEqual(sorted(os.listdir(self.userdata)), before)

    def test_without_a_secret_provider_and_without_a_file(self):
        self.write_settings({"providerInstances": {"alpha": {}}})
        result = self.run_sync("--show-target")
        self.assertIn("secret provider onepassword: no", result.stdout)
        os.unlink(self.settings_path)
        result = self.run_sync("--show-target")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("exists: no", result.stdout)
        self.assertEqual(os.listdir(self.userdata), [])

    def test_the_provider_counts_only_when_its_entry_is_an_object(self):
        for entry, expected in (({}, "yes"), ({"kind": "one_password"}, "yes"), (None, "no"),
                                ("x", "no"), ([], "no"), (0, "no")):
            with self.subTest(entry=entry):
                self.write_settings({"providerInstances": {"alpha": {}},
                                     "secretProviders": {"onepassword": entry}})
                result = self.run_sync("--show-target")
                self.assertIn(f"secret provider onepassword: {expected}", result.stdout)

    def test_needs_no_references_file_or_providers(self):
        self.write_settings({"providerInstances": {}})
        self.assertFalse(os.path.exists(self.op_env))
        self.assertEqual(self.run_sync("--show-target").returncode, 0)

DRIVER = """
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("sync_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mode, args = sys.argv[2], sys.argv[3:]
if mode == "change-between-read-and-replace":
    real_mkstemp = mod.tempfile.mkstemp
    def mkstemp(*a, **k):
        # Runs after the original bytes were read and before the replace.
        with open(os.path.join(os.environ["T3CODE_HOME"], "userdata", "settings.json"), "a") as fh:
            fh.write(" ")
        return real_mkstemp(*a, **k)
    mod.tempfile.mkstemp = mkstemp
elif mode == "same-second-twice":
    mod.time.strftime = lambda fmt: "20000101-000000"
    mod.os.getpid = lambda: 4242
mod.main(args)
if mode == "same-second-twice":
    mod.main(args)
"""

class BackupAndConcurrencyTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})

    def run_driver(self, mode, *args):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.root,
               "T3CODE_HOME": self.t3_home, "T3_OP_ENV": self.op_env}
        return subprocess.run([sys.executable, "-c", DRIVER, SCRIPT, mode, *args],
                              capture_output=True, text=True, env=env, check=False)

    def test_backup_is_private_even_when_settings_are_not(self):
        os.chmod(self.settings_path, 0o644)
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        (backup,) = self.backups()
        self.assertEqual(stat.S_IMODE(os.stat(backup).st_mode), 0o600)

    def test_two_runs_in_the_same_second_do_not_collide(self):
        before = self.read_bytes(self.settings_path)
        result = self.run_driver("same-second-twice", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = sorted(os.path.basename(b) for b in self.backups())
        self.assertEqual(names, ["settings.json.bak-20000101-000000-4242",
                                 "settings.json.bak-20000101-000000-4242-1"])
        self.assertEqual(self.read_bytes(self.backups()[0].replace("4242-1", "4242")), before)

    def test_backup_is_never_overwritten(self):
        existing = self.settings_path + ".bak-20000101-000000-4242"
        with open(existing, "w", encoding="utf-8") as fh:
            fh.write("precious")
        result = self.run_driver("same-second-twice", "alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_bytes(existing), b"precious")

    def test_a_change_between_read_and_replace_aborts(self):
        before = self.read_bytes(self.settings_path)
        result = self.run_driver("change-between-read-and-replace", "alpha")
        self.assert_fails(result, "changed while this ran")
        self.assertEqual(self.read_bytes(self.settings_path), before + b" ")
        self.assertEqual(self.backups(), [])
        self.assertEqual([n for n in os.listdir(self.userdata) if n.startswith(".settings-")], [])

    def test_the_lock_file_is_kept_after_a_run_and_is_empty(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        for _ in range(2):
            self.assertEqual(self.run_sync("alpha").returncode, 0)
            lock = self.settings_path + ".lock"
            self.assertTrue(os.path.exists(lock))
            self.assertEqual(os.path.getsize(lock), 0)

    def test_a_held_lock_stops_the_run(self):
        fd = os.open(self.settings_path + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        before = self.read_bytes(self.settings_path)
        self.assert_fails(self.run_sync("alpha"), "holds the settings lock")
        self.assertEqual(self.read_bytes(self.settings_path), before)

    def test_symlink_to_outside_its_directory_is_refused(self):
        outside = os.path.join(self.root, "elsewhere.json")
        os.replace(self.settings_path, outside)
        os.symlink(outside, self.settings_path)
        before = self.read_bytes(outside)
        self.assert_fails(self.run_sync("alpha"), "symlink to outside its directory")
        self.assertEqual(self.read_bytes(outside), before)

    def test_symlink_inside_its_directory_is_followed(self):
        real = os.path.join(self.userdata, "real-settings.json")
        os.replace(self.settings_path, real)
        os.symlink("real-settings.json", self.settings_path)
        self.assertEqual(self.run_sync("alpha").returncode, 0)
        self.assertTrue(os.path.islink(self.settings_path))
        with open(real, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["providerInstances"]["alpha"]["environment"][0]["name"], "API_KEY")

class ValidationTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.write_settings({"providerInstances": {"alpha": {}}})

    def test_reference_length_limit(self):
        ok_ref = "op://v/i/" + "a" * (1024 - len("op://v/i/"))
        self.write_op_env(f"API_KEY={ok_ref}\n")
        self.assertEqual(self.run_sync("--dry-run", "alpha").returncode, 0)
        self.write_op_env(f"API_KEY={ok_ref}a\n")
        self.assert_fails(self.run_sync("alpha"), "longer than 1024 characters")

    def test_variable_name_length_limit(self):
        self.write_op_env(f"{'A' * 128}={REF_A}\n")
        self.assertEqual(self.run_sync("--dry-run", "alpha").returncode, 0)
        self.write_op_env(f"{'A' * 129}={REF_A}\n")
        self.assert_fails(self.run_sync("alpha"), "the variable name is not valid")

    def test_account_grammar_and_length(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        for good in ("my.1password.com", "a", "Team_1-x.example", "a" * 253):
            with self.subTest(good=good[:20]):
                self.assertEqual(self.run_sync("--dry-run", f"--account={good}", "alpha").returncode, 0)
        for bad in ("-lead", ".lead", "_lead", "has space", "a/b", "a@b", "a" * 254, ""):
            with self.subTest(bad=bad[:20]):
                self.assert_fails(self.run_sync(f"--account={bad}", "alpha"), "--account needs")

    def test_malformed_existing_entries_name_the_provider_and_index(self):
        cases = {
            "not an object": ["text"],
            "no string name": [{"name": 5}],
            "secret is a string": [{"name": "OK", "secret": "x"}, {"name": "BAD", "secret": "planted"}],
            "secret is a list": [{"name": "A"}, {"name": "B"}, {"name": "C", "secret": ["x"]}],
        }
        self.write_op_env(f"API_KEY={REF_A}\n")
        for label, environment in cases.items():
            with self.subTest(label):
                self.write_settings({"providerInstances": {"alpha": {"environment": environment}}})
                result = self.run_sync("alpha")
                self.assert_fails(result, "provider 'alpha' environment index")
                self.assertNotIn("planted", result.stderr)

    def test_absent_secret_is_a_literal_variable(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {"environment": [
            {"name": "A", "value": "1"}]}}})
        self.assertEqual(self.run_sync("alpha").returncode, 0)

    def test_null_secret_is_an_error(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        before = {"providerInstances": {"alpha": {"environment": [
            {"name": "A", "value": "1"}, {"name": "B", "value": "2", "secret": None}]}}}
        self.write_settings(before)
        self.assert_fails(self.run_sync("alpha"), "provider 'alpha' environment index 1 has a secret that is not an object")
        self.assertEqual(self.read_settings(), before)

    def test_secret_must_be_an_object(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        for bad in (None, 0, "", False, [], "x"):
            with self.subTest(secret=bad):
                self.write_settings({"providerInstances": {"alpha": {"environment": [
                    {"name": "A", "secret": bad}]}}})
                self.assert_fails(self.run_sync("alpha"), "has a secret that is not an object")

    def test_environment_absent_is_empty_and_a_list_is_used(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}, "beta": {"environment": []}}})
        self.assertEqual(self.run_sync("alpha", "beta").returncode, 0)

    def test_environment_of_any_other_type_is_an_error(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        for bad in (None, 0, "", False, {}, "x"):
            with self.subTest(environment=bad):
                self.write_settings({"providerInstances": {"alpha": {"environment": bad}}})
                self.assert_fails(self.run_sync("alpha"), "alpha.environment is not a list")

    def test_errors_never_echo_a_line_or_a_value(self):
        cases = {
            "bad name": "MARKER-NAME-1=op://vault/item/field\n",
            "bad reference": "API_KEY=MARKER-VALUE-2\n",
            "no equals": "MARKER-LINE-3\n",
            "reference too long": "API_KEY=op://v/i/" + "MARKER4" * 200 + "\n",
            "name too long": "MARKER5" * 30 + f"={REF_A}\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.write_op_env(text)
                result = self.run_sync("alpha")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("MARKER", result.stdout + result.stderr)
                self.assertRegex(result.stderr, r"op\.env:1:")

class FullmatchTests(SyncTestCase):
    """A trailing newline must fail every grammar."""

    def test_account_with_a_trailing_newline_fails(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assert_fails(self.run_sync("--account=my.1password.com\n", "alpha"), "--account needs")

    def test_remove_name_with_a_trailing_newline_fails(self):
        self.write_settings({"providerInstances": {"alpha": {}}})
        self.assert_fails(self.run_sync("--remove=NAME\n", "alpha"), "--remove needs a valid variable name")

    def test_patterns_reject_a_trailing_newline(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIsNotNone(mod.REFERENCE.fullmatch(REF_A))
        self.assertIsNone(mod.REFERENCE.fullmatch(REF_A + "\n"))
        self.assertIsNone(mod.VARIABLE_NAME.fullmatch("NAME\n"))
        self.assertIsNone(mod.ACCOUNT.fullmatch("my.1password.com\n"))
        self.assertFalse(mod.valid_name("NAME\n"))

class ListReferencesTests(SyncTestCase):
    def test_prints_name_tab_reference_and_writes_nothing(self):
        self.write_op_env(f"# comment\n\nAPI_KEY={REF_A}\n  OTHER =  {REF_B}\n")
        result = self.run_sync("--list-references")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f"API_KEY\t{REF_A}", f"OTHER\t{REF_B}"])
        self.assertEqual(os.listdir(self.userdata), [])
        self.assertEqual(os.listdir(self.root).count("t3"), 1)

    def test_needs_no_settings_file_or_providers(self):
        self.write_op_env(f"API_KEY={REF_A}\n")
        self.assertFalse(os.path.exists(self.settings_path))
        self.assertEqual(self.run_sync("--list-references").returncode, 0)

    def test_rejects_what_a_sync_rejects_with_a_line_number_and_no_content(self):
        cases = {
            "literal value": "OK=op://vault/item/field\nAPI_KEY=MARKER-LITERAL-1\n",
            "no equals": "MARKER-LINE-2\n",
            "bad name": "MARKER-NAME-3=op://vault/item/field\n",
            "duplicate": "A=op://vault/item/field\nA=op://vault/item/field\n",
            "reference too long": "API_KEY=op://v/i/" + "MARKER4" * 200 + "\n",
            "empty": "# nothing\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.write_op_env(text)
                result = self.run_sync("--list-references")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "", "nothing may be printed for an invalid file")
                self.assertNotIn("MARKER", result.stdout + result.stderr)
                if label != "empty":
                    self.assertRegex(result.stderr, r"op\.env:\d+:")

    def test_missing_file_fails(self):
        self.assert_fails(self.run_sync("--list-references"), "cannot read references file")

    def test_unknown_option_still_fails(self):
        self.assert_fails(self.run_sync("--list-references", "--bogus"), "unknown option")

if __name__ == "__main__":
    unittest.main()
