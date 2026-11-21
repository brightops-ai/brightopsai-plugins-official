"""Tests for skills/1password-secrets/scripts/op_token.sh.

A fake security executable (wired in through T3_OP_TOKEN_SECURITY) records its argv and keeps the
keychain in a temporary file. Shims around the other commands the script runs record their argv
too. A planted token must never appear in any argv or in stdout or stderr.
"""
import os
import stat
import subprocess
import tempfile
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PLUGIN_DIR, "skills", "1password-secrets", "scripts", "op_token.sh")

TOKEN = "ops_PLANTED_TOKEN_0123456789"
OTHER_TOKEN = "ops_PREVIOUS_TOKEN_9876543210"
ACCOUNT = "tester"

FAKE_SECURITY = """#!/bin/sh
d="$FAKE_DIR"
echo "security $*" >> "$d/argv"
case "$1" in
  -i)
    if [ -f "$d/fail_write" ]; then cat > /dev/null; exit 1; fi
    read -r line
    tok="${line##*-w \\"}"; tok="${tok%\\"}"
    [ -f "$d/corrupt" ] && tok="${tok}-corrupted"
    printf '%s\\n' "$tok" > "$d/keychain"
    ;;
  find-generic-password)
    [ -f "$d/keychain" ] || exit 44
    read -r value < "$d/keychain"
    echo "$value"
    ;;
esac
"""

SHIM = """#!/bin/sh
echo "%(name)s $*" >> "$FAKE_DIR/shim_argv"
exec %(real)s "$@"
"""

class OpTokenTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)
        self.fake = os.path.join(self.root, "fake")
        self.shims = os.path.join(self.root, "shims")
        self.home = os.path.join(self.root, "t3home")
        for directory in (self.fake, self.shims, self.home):
            os.makedirs(directory)
        self.security = os.path.join(self.fake, "security")
        self.write_exec(self.security, FAKE_SECURITY)
        for name in ("mktemp", "mv", "chmod", "cat", "wc", "tr", "rm", "id", "head"):
            real = next(p for p in (f"/usr/bin/{name}", f"/bin/{name}") if os.path.exists(p))
            self.write_exec(os.path.join(self.shims, name), SHIM % {"name": name, "real": real})
        self.token_file = os.path.join(self.root, "token")
        self.write_token(TOKEN + "\n")
        self.service_env = os.path.join(self.home, "service.env")

    @staticmethod
    def write_exec(path, body):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(path, 0o755)

    def write_token(self, text, path=None):
        with open(path or self.token_file, "w", encoding="utf-8") as fh:
            fh.write(text)

    def fake_file(self, name):
        try:
            with open(os.path.join(self.fake, name), encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    def touch_fake(self, name):
        with open(os.path.join(self.fake, name), "w", encoding="utf-8"):
            pass

    def run_token(self, *args):
        env = {
            "PATH": self.shims,
            "HOME": self.root,
            "USER": ACCOUNT,
            "FAKE_DIR": self.fake,
            "T3_OP_TOKEN_SECURITY": self.security,
        }
        result = subprocess.run(["/bin/sh", SCRIPT, *args], capture_output=True, text=True,
                                check=False, stdin=subprocess.DEVNULL, timeout=60, env=env)
        for secret in (TOKEN, OTHER_TOKEN):
            self.assertNotIn(secret, result.stdout, "token printed to stdout")
            self.assertNotIn(secret, result.stderr, "token printed to stderr")
        for name in ("argv", "shim_argv"):
            self.assertNotIn(TOKEN, self.fake_file(name), f"token in the argv recorded in {name}")
        return result

    def assert_ok(self, result, line):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), [line])

    def assert_fail(self, result, fragment):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        self.assertTrue(result.stdout.startswith("FAIL: "), result.stdout)
        self.assertIn(fragment, result.stdout)

    def read_service_env(self):
        with open(self.service_env, encoding="utf-8") as fh:
            return fh.read()

    def mode(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

class UsageTests(OpTokenTestCase):
    def test_bad_usage(self):
        for args in ((), ("bogus",), ("keychain",), ("keychain", "a", "b"), ("service-env", "a"),
                     ("remove-service-env",), ("remove-service-env", "a", "b")):
            with self.subTest(args=args):
                result = self.run_token(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage: op_token.sh", result.stderr)

class TokenFileValidationTests(OpTokenTestCase):
    """The same validation guards both subcommands; a failure changes nothing."""

    def bad_files(self):
        missing = os.path.join(self.root, "missing")
        directory = os.path.join(self.root, "a-directory")
        os.makedirs(directory)
        link = os.path.join(self.root, "link")
        os.symlink(self.token_file, link)
        cases = {
            "token file is not a regular file": [missing, directory, link],
            "token file is empty": [],
            "holds more than one line": [],
            "does not start with ops_": [],
            "holds a character": [],
        }
        empty = os.path.join(self.root, "empty")
        self.write_token("", empty)
        cases["token file is empty"].append(empty)
        two = os.path.join(self.root, "two")
        self.write_token(TOKEN + "\n" + TOKEN + "\n", two)
        cases["holds more than one line"].append(two)
        wrong = os.path.join(self.root, "wrong")
        self.write_token("not-a-service-account-token\n", wrong)
        cases["does not start with ops_"].append(wrong)
        for label, text in (("space", TOKEN + " x\n"), ("quote", TOKEN + '"\n'),
                            ("semicolon", TOKEN + ";x\n"), ("crlf", TOKEN + "\r\n"),
                            ("two lines no final newline", TOKEN + "\n" + TOKEN)):
            path = os.path.join(self.root, "bad-" + label.replace(" ", "-"))
            self.write_token(text, path)
            cases["holds a character" if label != "two lines no final newline" else "holds a character"].append(path)
        return cases

    def test_keychain_changes_nothing(self):
        for fragment, paths in self.bad_files().items():
            for path in paths:
                with self.subTest(path=os.path.basename(path)):
                    self.assert_fail(self.run_token("keychain", path), fragment)
                    self.assertEqual(self.fake_file("argv"), "", "security must not be called")
                    self.assertEqual(self.fake_file("keychain"), "")

    def test_service_env_changes_nothing(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write(f"KEEP=1\nOP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\n")
        before = sorted(os.listdir(self.home))
        for fragment, paths in self.bad_files().items():
            for path in paths:
                with self.subTest(path=os.path.basename(path)):
                    self.assert_fail(self.run_token("service-env", path, self.home), fragment)
                    self.assertEqual(self.read_service_env(), f"KEEP=1\nOP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\n")
                    self.assertEqual(sorted(os.listdir(self.home)), before)

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_unreadable_token_file_changes_nothing(self):
        os.chmod(self.token_file, 0)
        self.addCleanup(os.chmod, self.token_file, 0o600)
        self.assert_fail(self.run_token("keychain", self.token_file), "not readable")
        self.assert_fail(self.run_token("service-env", self.token_file, self.home), "not readable")
        self.assertEqual(self.fake_file("argv"), "")
        self.assertEqual(os.listdir(self.home), [])

class KeychainTests(OpTokenTestCase):
    def test_writes_through_stdin_and_reads_back(self):
        result = self.run_token("keychain", self.token_file)
        self.assert_ok(result, "ok: keychain item op_service_account written and read back")
        self.assertEqual(self.fake_file("keychain"), TOKEN + "\n")
        self.assertEqual(self.fake_file("argv").splitlines(), [
            "security -i",
            f"security find-generic-password -a {ACCOUNT} -s op_service_account -w",
        ])

    def test_a_file_without_a_final_newline_works(self):
        self.write_token(TOKEN)
        self.assert_ok(self.run_token("keychain", self.token_file),
                       "ok: keychain item op_service_account written and read back")
        self.assertEqual(self.fake_file("keychain"), TOKEN + "\n")

    def test_a_refused_write_fails(self):
        self.touch_fake("fail_write")
        self.assert_fail(self.run_token("keychain", self.token_file), "did not accept the keychain write")
        self.assertEqual(self.fake_file("keychain"), "")

    def test_a_value_that_does_not_read_back_fails(self):
        self.touch_fake("corrupt")
        self.assert_fail(self.run_token("keychain", self.token_file), "does not read back")

    def test_an_account_name_that_would_break_the_command_is_refused(self):
        env = {"PATH": self.shims, "HOME": self.root, "USER": 'a"b', "FAKE_DIR": self.fake,
               "T3_OP_TOKEN_SECURITY": self.security}
        result = subprocess.run(["/bin/sh", SCRIPT, "keychain", self.token_file], capture_output=True,
                                text=True, check=False, stdin=subprocess.DEVNULL, timeout=60, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("FAIL: "))
        self.assertEqual(self.fake_file("argv"), "")

class ServiceEnvTests(OpTokenTestCase):
    def test_creates_the_file_with_mode_0600(self):
        result = self.run_token("service-env", self.token_file, self.home)
        self.assert_ok(result, "ok: service.env holds one OP_SERVICE_ACCOUNT_TOKEN line, mode 0600")
        self.assertEqual(self.read_service_env(), f"OP_SERVICE_ACCOUNT_TOKEN={TOKEN}\n")
        self.assertEqual(self.mode(self.service_env), 0o600)
        self.assertEqual(os.listdir(self.home), ["service.env"])

    def test_keeps_other_lines_and_replaces_the_old_token_line(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write(f"FIRST=1\nOP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\n# comment with spaces\n"
                     f"OP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\nLAST='quoted $value'\n")
        os.chmod(self.service_env, 0o644)
        self.assert_ok(self.run_token("service-env", self.token_file, self.home),
                       "ok: service.env holds one OP_SERVICE_ACCOUNT_TOKEN line, mode 0600")
        self.assertEqual(self.read_service_env(),
                         f"FIRST=1\n# comment with spaces\nLAST='quoted $value'\nOP_SERVICE_ACCOUNT_TOKEN={TOKEN}\n")
        self.assertEqual(self.mode(self.service_env), 0o600)
        self.assertEqual(os.listdir(self.home), ["service.env"])

    def test_a_missing_trailing_newline_is_handled(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write("FIRST=1\nLAST=2")
        self.assert_ok(self.run_token("service-env", self.token_file, self.home),
                       "ok: service.env holds one OP_SERVICE_ACCOUNT_TOKEN line, mode 0600")
        self.assertEqual(self.read_service_env(), f"FIRST=1\nLAST=2\nOP_SERVICE_ACCOUNT_TOKEN={TOKEN}\n")

    def test_a_longer_name_is_not_mistaken_for_the_token_line(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write("OP_SERVICE_ACCOUNT_TOKEN_OLD=keep\nXOP_SERVICE_ACCOUNT_TOKEN=keep\n")
        self.assert_ok(self.run_token("service-env", self.token_file, self.home),
                       "ok: service.env holds one OP_SERVICE_ACCOUNT_TOKEN line, mode 0600")
        self.assertEqual(self.read_service_env(),
                         f"OP_SERVICE_ACCOUNT_TOKEN_OLD=keep\nXOP_SERVICE_ACCOUNT_TOKEN=keep\nOP_SERVICE_ACCOUNT_TOKEN={TOKEN}\n")

    def test_the_token_is_in_no_argv_of_the_commands_it_runs(self):
        self.run_token("service-env", self.token_file, self.home)
        recorded = self.fake_file("shim_argv")
        self.assertIn("mktemp", recorded)
        self.assertIn("mv", recorded)
        self.assertNotIn("ops_", recorded)

    def test_the_new_file_is_renamed_into_place_from_the_same_directory(self):
        self.run_token("service-env", self.token_file, self.home)
        moves = [line for line in self.fake_file("shim_argv").splitlines() if line.startswith("mv ")]
        self.assertEqual(len(moves), 1, moves)
        source, target = moves[0].split()[-2:]
        self.assertEqual(os.path.dirname(source), self.home)
        self.assertEqual(target, self.service_env)
        self.assertTrue(os.path.basename(source).startswith(".service.env."))

    def test_a_missing_home_or_a_symlinked_service_env_changes_nothing(self):
        self.assert_fail(self.run_token("service-env", self.token_file, os.path.join(self.root, "nope")),
                         "not a directory")
        target = os.path.join(self.root, "elsewhere")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("untouched\n")
        os.symlink(target, self.service_env)
        self.assert_fail(self.run_token("service-env", self.token_file, self.home), "symlink")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "untouched\n")

    @unittest.skipIf(os.geteuid() == 0, "root writes everywhere")
    def test_a_directory_that_cannot_be_written_changes_nothing(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write("KEEP=1\n")
        os.chmod(self.home, 0o500)
        self.addCleanup(os.chmod, self.home, 0o700)
        self.assert_fail(self.run_token("service-env", self.token_file, self.home), "temporary file")
        self.assertEqual(self.read_service_env(), "KEEP=1\n")

    def test_never_touches_the_keychain(self):
        self.run_token("service-env", self.token_file, self.home)
        self.assertEqual(self.fake_file("argv"), "")

class RemoveServiceEnvTests(OpTokenTestCase):
    def test_removes_only_the_token_line(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write(f"FIRST=1\nOP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\nLAST=2\n")
        os.chmod(self.service_env, 0o644)
        self.assert_ok(self.run_token("remove-service-env", self.home),
                       "ok: service.env holds no OP_SERVICE_ACCOUNT_TOKEN line")
        self.assertEqual(self.read_service_env(), "FIRST=1\nLAST=2\n")
        self.assertEqual(self.mode(self.service_env), 0o600)
        self.assertEqual(os.listdir(self.home), ["service.env"])

    def test_handles_a_missing_trailing_newline_and_a_token_only_file(self):
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write(f"FIRST=1\nOP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}")
        self.assert_ok(self.run_token("remove-service-env", self.home),
                       "ok: service.env holds no OP_SERVICE_ACCOUNT_TOKEN line")
        self.assertEqual(self.read_service_env(), "FIRST=1\n")
        with open(self.service_env, "w", encoding="utf-8") as fh:
            fh.write(f"OP_SERVICE_ACCOUNT_TOKEN={OTHER_TOKEN}\n")
        self.run_token("remove-service-env", self.home)
        self.assertEqual(self.read_service_env(), "")

    def test_no_file_is_not_an_error(self):
        self.assert_ok(self.run_token("remove-service-env", self.home),
                       "ok: service.env does not exist; nothing to remove")
        self.assertEqual(os.listdir(self.home), [])

    def test_a_missing_home_fails(self):
        self.assert_fail(self.run_token("remove-service-env", os.path.join(self.root, "nope")), "not a directory")

if __name__ == "__main__":
    unittest.main()
