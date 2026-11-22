"""Tests for skills/1password-secrets/scripts/op_check.sh.

Fake security, launchctl and op executables live in a temporary directory and are wired in
through the T3_OP_CHECK_* variables. A planted token and a planted resolved value must never
appear in any output.
"""
import os
import subprocess
import sys
import tempfile
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PLUGIN_DIR, "skills", "1password-secrets", "scripts", "op_check.sh")

TOKEN = "ops_PLANTED_TOKEN_0123456789"
RESOLVED = "PLANTED_RESOLVED_VALUE_9876543210"

FAKE_SECURITY = """#!/bin/sh
# Prints the planted token for `find-generic-password ... -w`; absent file means "not found".
[ -f "$FAKE_DIR/keychain" ] || exit 44
read -r value < "$FAKE_DIR/keychain"
echo "$value"
"""

FAKE_LAUNCHCTL = """#!/bin/sh
[ "$1" = getenv ] || exit 1
[ -f "$FAKE_DIR/launchd" ] || exit 0
read -r value < "$FAKE_DIR/launchd"
echo "$value"
"""

FAKE_OP = """#!/bin/sh
d="$FAKE_DIR"
case "$1" in
  read)
    read -r keychain < "$d/keychain"
    seen="token-mismatch"
    [ "$OP_SERVICE_ACCOUNT_TOKEN" = "$keychain" ] && seen="token-ok"
    connect="connect-unset"
    [ -n "${OP_CONNECT_HOST}${OP_CONNECT_TOKEN}" ] && connect="connect-set"
    echo "read $2 $seen $connect" >> "$d/calls"
    case "$2" in *missing*) echo "[ERROR] could not read $2" >&2; exit 1 ;; esac
    echo "%(resolved)s"
    echo "%(resolved)s" >&2
    ;;
  whoami)
    [ -f "$d/whoami" ] && cat "$d/whoami" && exit 0
    exit 1
    ;;
esac
""" % {"resolved": RESOLVED}

class OpCheckTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)
        self.fake = os.path.join(self.root, "fake")
        os.makedirs(self.fake)
        self.op_env = os.path.join(self.root, "op.env")
        self.paths = {}
        for name, body in (("security", FAKE_SECURITY), ("launchctl", FAKE_LAUNCHCTL), ("op", FAKE_OP)):
            path = os.path.join(self.fake, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
            self.paths[name] = path
        self.plant("keychain", TOKEN)
        self.plant("launchd", TOKEN)
        self.plant("whoami", "URL: https://example.1password.com\nUser Type: SERVICE_ACCOUNT")
        self.write_op_env("API_KEY=op://vault/item/field\nOTHER = op://vault/two/token\n")

    def plant(self, name, text):
        with open(os.path.join(self.fake, name), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    def unplant(self, name):
        os.unlink(os.path.join(self.fake, name))

    def write_op_env(self, text):
        with open(self.op_env, "w", encoding="utf-8") as fh:
            fh.write(text)

    def calls(self):
        try:
            with open(os.path.join(self.fake, "calls"), encoding="utf-8") as fh:
                return fh.read().splitlines()
        except FileNotFoundError:
            return []

    def run_check(self, *args, **env_extra):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": self.root,
            "USER": "tester",
            "FAKE_DIR": self.fake,
            "T3_OP_ENV": self.op_env,
            "T3_OP_CHECK_PYTHON": sys.executable,
            "T3_OP_CHECK_SECURITY": self.paths["security"],
            "T3_OP_CHECK_LAUNCHCTL": self.paths["launchctl"],
            "T3_OP_CHECK_OP": self.paths["op"],
        }
        env.update(env_extra)
        result = subprocess.run(["/bin/sh", SCRIPT, *args], capture_output=True, text=True,
                                check=False, stdin=subprocess.DEVNULL, timeout=60, env=env)
        for secret in (TOKEN, RESOLVED):
            self.assertNotIn(secret, result.stdout, "secret printed to stdout")
            self.assertNotIn(secret, result.stderr, "secret printed to stderr")
        return result

    def assert_passes(self, result, *lines):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), list(lines))

    def assert_fails(self, result, *lines):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in lines:
            self.assertIn(line, result.stdout.splitlines())

class UsageTests(OpCheckTestCase):
    def test_unknown_or_missing_subcommand(self):
        for args in ((), ("bogus",)):
            with self.subTest(args=args):
                result = self.run_check(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage: op_check.sh", result.stderr)

class KeychainTests(OpCheckTestCase):
    def test_pass(self):
        self.assert_passes(self.run_check("keychain"),
                           "ok: keychain item op_service_account exists and starts with ops_")

    def test_missing_item(self):
        self.unplant("keychain")
        self.assert_fails(self.run_check("keychain"), "FAIL: keychain item op_service_account not found")

    def test_wrong_prefix(self):
        self.plant("keychain", "not-a-service-account-token")
        result = self.run_check("keychain")
        self.assert_fails(result, "FAIL: keychain item op_service_account does not start with ops_")
        self.assertNotIn("not-a-service-account-token", result.stdout + result.stderr)

class LaunchdTests(OpCheckTestCase):
    def test_match(self):
        self.assert_passes(self.run_check("launchd"), "ok: launchd value matches the keychain value")

    def test_mismatch(self):
        self.plant("launchd", "ops_ANOTHER_PLANTED_TOKEN")
        result = self.run_check("launchd")
        self.assert_fails(result, "FAIL: launchd value differs from the keychain value")
        self.assertNotIn("ANOTHER_PLANTED", result.stdout + result.stderr)

    def test_launchd_empty(self):
        self.unplant("launchd")
        self.assert_fails(self.run_check("launchd"), "FAIL: launchd has no OP_SERVICE_ACCOUNT_TOKEN")

    def test_keychain_missing(self):
        self.unplant("keychain")
        self.assert_fails(self.run_check("launchd"), "FAIL: keychain item op_service_account not found")

class RefsTests(OpCheckTestCase):
    def test_every_reference_resolves(self):
        self.assert_passes(self.run_check("refs"), "ok: API_KEY resolves", "ok: OTHER resolves")
        self.assertEqual(self.calls(), [
            "read op://vault/item/field token-ok connect-unset",
            "read op://vault/two/token token-ok connect-unset",
        ])

    def test_connect_variables_are_unset_for_op(self):
        result = self.run_check("refs", OP_CONNECT_HOST="https://connect.example", OP_CONNECT_TOKEN="x")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(all(call.endswith("connect-unset") for call in self.calls()), self.calls())

    def test_one_failing_reference_fails_the_run_and_is_named(self):
        self.write_op_env("API_KEY=op://vault/item/field\nGONE=op://vault/missing/field\n")
        result = self.run_check("refs")
        self.assert_fails(result, "ok: API_KEY resolves", "FAIL: GONE does not resolve")
        self.assertNotIn("op://vault/missing", result.stdout)

    def test_keychain_missing(self):
        self.unplant("keychain")
        self.assert_fails(self.run_check("refs"), "FAIL: keychain item op_service_account not found")
        self.assertEqual(self.calls(), [])

    def test_references_file_missing_or_empty(self):
        os.unlink(self.op_env)
        result = self.run_check("refs")
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r"FAIL: references file: .*cannot read references file")
        self.write_op_env("# only a comment\n\n")
        result = self.run_check("refs")
        self.assertRegex(result.stdout, r"FAIL: references file: .*holds no references")
        self.assertEqual(self.calls(), [])

    def test_line_without_equals(self):
        self.write_op_env("API_KEY=op://vault/item/field\nMARKER-LINE\n")
        result = self.run_check("refs")
        self.assertRegex(result.stdout, r"FAIL: references file: .*op\.env:2: expected NAME=")
        self.assertNotIn("MARKER", result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_literal_value_never_reaches_op_or_any_output(self):
        for command in ("refs", "session"):
            with self.subTest(command=command):
                self.write_op_env("OK=op://vault/item/field\nAPI_KEY=MARKER-LITERAL-VALUE-123\n")
                env = {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "OK": "v", "API_KEY": "v"}
                result = self.run_check(command, **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stdout, r"FAIL: references file: .*op\.env:2:")
                self.assertNotIn("MARKER", result.stdout + result.stderr)
                self.assertEqual(self.calls(), [], "the fake op must never be invoked")
        # `refs` is the one that would call `op read`; for it, not even whoami may have run.
        self.assertFalse(os.path.exists(os.path.join(self.fake, "calls")))

    def test_a_reference_with_a_stray_literal_part_is_rejected_before_op(self):
        self.write_op_env("API_KEY=op://vault/item/field;extra-MARKER\n")
        result = self.run_check("refs")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("MARKER", result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

class SessionTests(OpCheckTestCase):
    def good_env(self):
        return {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "API_KEY": "v1", "OTHER": "v2"}

    def test_pass(self):
        self.assert_passes(
            self.run_check("session", **self.good_env()),
            "ok: OP_SERVICE_ACCOUNT_TOKEN is set",
            "ok: op whoami reports a service account",
            "ok: API_KEY is set",
            "ok: OTHER is set",
            "ok: no OP_CONNECT_* variable is set",
        )

    def test_token_not_set(self):
        env = self.good_env()
        del env["OP_SERVICE_ACCOUNT_TOKEN"]
        self.assert_fails(self.run_check("session", **env), "FAIL: OP_SERVICE_ACCOUNT_TOKEN is not set")

    def test_whoami_not_a_service_account(self):
        self.plant("whoami", "User Type: MEMBER")
        self.assert_fails(self.run_check("session", **self.good_env()),
                          "FAIL: op whoami does not report a service account")

    def test_whoami_fails(self):
        self.unplant("whoami")
        self.assert_fails(self.run_check("session", **self.good_env()),
                          "FAIL: op whoami does not report a service account")

    def test_missing_or_empty_variable(self):
        env = self.good_env()
        del env["OTHER"]
        env["API_KEY"] = ""
        self.assert_fails(self.run_check("session", **env),
                          "FAIL: API_KEY is not set", "FAIL: OTHER is not set")

    def test_connect_variable_set(self):
        for name in ("OP_CONNECT_HOST", "OP_CONNECT_TOKEN"):
            with self.subTest(name=name):
                env = self.good_env()
                env[name] = "x"
                self.assert_fails(self.run_check("session", **env), "FAIL: an OP_CONNECT_* variable is set")

    def test_references_file_missing(self):
        os.unlink(self.op_env)
        result = self.run_check("session", **self.good_env())
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r"FAIL: references file: .*cannot read references file")

    def test_explicit_names_need_no_references_file(self):
        os.unlink(self.op_env)
        env = {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "ONE": "1", "TWO": "2"}
        self.assert_passes(
            self.run_check("session", "ONE", "TWO", **env),
            "ok: OP_SERVICE_ACCOUNT_TOKEN is set",
            "ok: op whoami reports a service account",
            "ok: ONE is set",
            "ok: TWO is set",
            "ok: no OP_CONNECT_* variable is set",
        )

    def test_explicit_names_replace_the_references_file(self):
        # The file names API_KEY and OTHER; the arguments name only ONE.
        env = {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "ONE": "1"}
        result = self.run_check("session", "ONE", **env)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("ok: ONE is set", result.stdout)
        self.assertNotIn("API_KEY", result.stdout)

    def test_explicit_name_that_is_unset_or_invalid(self):
        env = {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "ONE": "1"}
        result = self.run_check("session", "ONE", "MISSING", "bad-name", "1BAD", **env)
        self.assert_fails(result, "ok: ONE is set", "FAIL: MISSING is not set",
                          "FAIL: bad-name: not a variable name", "FAIL: 1BAD: not a variable name")

    def test_a_bad_references_file_is_ignored_when_names_are_given(self):
        self.write_op_env("API_KEY=MARKER-LITERAL\n")
        env = {"OP_SERVICE_ACCOUNT_TOKEN": TOKEN, "ONE": "1"}
        result = self.run_check("session", "ONE", **env)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("MARKER", result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
