"""Tests for skills/restart/scripts/restart.sh.

Every run uses fake osascript, open and t3 executables written into a temporary directory and
wired in through the T3_RESTART_* variables, in an environment built from scratch. The real
app is never touched.
"""
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(PLUGIN_DIR, "skills", "restart", "scripts", "restart.sh")
HAS_PERL = shutil.which("perl", path="/usr/bin:/bin") is not None
APP_ID = "com.example.t3test"

FAKE_OSASCRIPT = """#!/bin/sh
d="$FAKE_DIR"
read -r mode < "$d/mode"
case "$*" in
  *"is running"*)
    [ "$mode" = error ] && exit 1
    read -r state < "$d/running"; echo "$state"; exit 0 ;;
  *"to quit"*)
    echo "quit $*" >> "$d/calls"
    [ "$mode" = error ] && exit 1
    [ "$mode" = stuck ] || echo false > "$d/running"
    exit 0 ;;
esac
exit 1
"""

FAKE_OPEN = """#!/bin/sh
echo "open $*" >> "$FAKE_DIR/calls"
while [ ! -f "$FAKE_DIR/proceed" ]; do sleep 0.02; done
read -r mode < "$FAKE_DIR/mode"
[ "$mode" = noreopen ] || echo true > "$FAKE_DIR/running"
"""

FAKE_T3 = """#!/bin/sh
d="$FAKE_DIR"
echo "t3 $1 $2 $3" >> "$d/calls"
while read -r line; do
  case "$line" in "result: "*) echo "t3-saw-result" >> "$d/calls"; break ;; esac
done < "$FAKE_LOG"
printf '%s' "$4" > "$d/message"
read -r mode < "$d/mode"
[ "$mode" = notifyfail ] && exit 1
exit 0
"""

FAKE_COMMAND = """#!/bin/sh
d="$FAKE_DIR"
read -r state < "$d/running"
echo "command app-running=$state" >> "$d/calls"
: > "$d/command_args"
for a in "$@"; do printf '%s\\n' "$a" >> "$d/command_args"; done
echo command-out
echo command-err >&2
read -r status < "$d/command_status"
exit "$status"
"""

class RestartTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)
        self.fake = os.path.join(self.root, "fake")
        os.makedirs(self.fake)
        self.log = os.path.join(self.root, "restart.log")
        self.paths = {}
        for name, body in (("osascript", FAKE_OSASCRIPT), ("open", FAKE_OPEN),
                           ("t3", FAKE_T3), ("command", FAKE_COMMAND)):
            path = os.path.join(self.fake, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
            self.paths[name] = path
        self.set_mode("normal")
        self.write("proceed", "go")
        self.write("running", "true")
        self.write("command_status", "0")

    def write(self, name, text):
        with open(os.path.join(self.fake, name), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    def set_mode(self, mode):
        self.write("mode", mode)

    def read(self, name):
        try:
            with open(os.path.join(self.fake, name), encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    def calls(self):
        return self.read("calls").splitlines()

    def env(self, **extra):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": self.root,
            "FAKE_DIR": self.fake,
            "FAKE_LOG": self.log,
            "T3_APP_ID": APP_ID,
            "T3_RESTART_OSASCRIPT": self.paths["osascript"],
            "T3_RESTART_OPEN": self.paths["open"],
            "T3_RESTART_T3": self.paths["t3"],
            "T3_RESTART_POLL_SECONDS": "0.05",
            "T3_RESTART_MAX_POLLS": "6",
        }
        env.update(extra)
        return env

    def run_script(self, *args, **env_extra):
        return subprocess.run(
            ["/bin/sh", SCRIPT, *args], capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL, timeout=30, env=self.env(**env_extra),
        )

    def log_text(self):
        try:
            with open(self.log, encoding="utf-8") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    def wait_for_log(self, fragment, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if fragment in self.log_text():
                return self.log_text()
            time.sleep(0.05)
        self.fail(f"{fragment!r} never appeared in the log:\n{self.log_text()}")

    def live(self, *tail, wait_for="result:"):
        """Run for real against the fakes and wait for the detached run to reach wait_for."""
        result = self.run_script("--notify", "thread:1", "--log", self.log, "--delay", "0", *tail)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("detached", result.stdout)
        return self.wait_for_log(wait_for)

    def assert_usage_error(self, result, fragment=None):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(fragment or "usage: restart.sh", result.stderr)

class ArgumentTests(RestartTestCase):
    def test_no_arguments(self):
        self.assert_usage_error(self.run_script())

    def test_unknown_argument(self):
        self.assert_usage_error(self.run_script("--bogus", "--dry-run"), "unknown argument: --bogus")
        self.assertFalse(os.path.exists(self.log))

    def test_old_while_closed_option_is_gone(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--while-closed", "x")
        self.assert_usage_error(result, "unknown argument: --while-closed")

    def test_trailing_option_needs_value(self):
        self.assert_usage_error(self.run_script("--dry-run", "--notify", "t1", "--log"), "--log needs a value")

    def test_option_value_may_not_swallow_dry_run(self):
        cases = (
            ("--notify", "--dry-run", "--log", self.log),
            ("--notify", "t1", "--log", "--dry-run"),
            ("--notify", "t1", "--log", self.log, "--delay", "--dry-run"),
        )
        for args in cases:
            with self.subTest(args=args):
                self.assert_usage_error(self.run_script(*args), "needs a value")
                self.assertFalse(os.path.exists(self.log))

    def test_missing_notify_or_log(self):
        self.assert_usage_error(self.run_script("--log", self.log, "--dry-run"))
        self.assert_usage_error(self.run_script("--notify", "t1", "--dry-run"))

    def test_delay_must_be_a_whole_number(self):
        for bad in ("abc", "-1", "1.5", ""):
            with self.subTest(delay=bad):
                result = self.run_script("--notify", "t1", "--log", self.log, "--delay", bad, "--dry-run")
                self.assert_usage_error(result, "--delay must be a whole number")

    def test_bad_notify_id(self):
        for bad in ("a b", "a;b", "a$b", "a'b"):
            with self.subTest(notify=bad):
                result = self.run_script("--notify", bad, "--log", self.log, "--dry-run")
                self.assert_usage_error(result, "--notify may hold only")

    def test_bad_bundle_id(self):
        for bad in ('a";b', "a b", "a'b", "a$(x)"):
            with self.subTest(app_id=bad):
                result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run", T3_APP_ID=bad)
                self.assert_usage_error(result, "T3_APP_ID may hold only")
                self.assertFalse(os.path.exists(self.log))

class PreflightAndLogTests(RestartTestCase):
    def test_existing_log_path_refused_and_untouched(self):
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write("keep me\n")
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("exists or is a symlink", result.stderr)
        self.assertEqual(self.log_text(), "keep me\n")

    def test_symlink_log_path_refused(self):
        target = os.path.join(self.root, "target.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("target\n")
        os.symlink(target, self.log)
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run")
        self.assertEqual(result.returncode, 2, result.stderr)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "target\n")
        dangling = os.path.join(self.root, "dangling.log")
        os.symlink(os.path.join(self.root, "nowhere"), dangling)
        result = self.run_script("--notify", "t1", "--log", dangling, "--dry-run")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "nowhere")))

    def test_unwritable_log(self):
        bad_log = os.path.join(self.root, "missing-dir", "restart.log")
        result = self.run_script("--notify", "t1", "--log", bad_log, "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot create log", result.stderr)

    def test_missing_perl(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run", PATH=empty)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("perl not found", result.stderr)
        self.assertFalse(os.path.exists(self.log))

    def test_missing_t3_cli(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run",
                                 T3_RESTART_T3=os.path.join(self.root, "no-such-t3"))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("t3 CLI is not an executable file", result.stderr)
        self.assertFalse(os.path.exists(self.log))

    def test_t3_cli_not_found_on_path_or_home(self):
        env_without = self.env()
        del env_without["T3_RESTART_T3"]
        result = subprocess.run(
            ["/bin/sh", SCRIPT, "--notify", "t1", "--log", self.log, "--dry-run"],
            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
            timeout=30, env=env_without,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("t3 CLI is not an executable file", result.stderr)

    def test_t3_cli_must_be_a_regular_file(self):
        for bad in (self.fake, os.path.join(self.fake, "mode")):  # a directory; a file without x
            with self.subTest(t3=bad):
                result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run",
                                         T3_RESTART_T3=bad)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("t3 CLI is not an executable file", result.stderr)
                self.assertFalse(os.path.exists(self.log))

    def test_command_must_be_an_executable_file(self):
        for command in (os.path.join(self.root, "nope"), "no-such-command-anywhere",
                        os.path.join(self.fake, "mode")):
            with self.subTest(command=command):
                result = self.run_script("--notify", "t1", "--log", self.log, "--", command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("not an executable file", result.stderr)
                self.assertFalse(os.path.exists(self.log))

@unittest.skipUnless(HAS_PERL, "needs perl to detach")
class DryRunTests(RestartTestCase):
    def test_dry_run_detaches_and_logs(self):
        result = self.run_script("--notify", "thread-1", "--log", self.log, "--delay", "3",
                                 "--dry-run", "--", self.paths["command"], "echo never-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("detached; dry run, T3 Code would quit in 3s", result.stdout)
        self.assertIn(self.log, result.stdout)
        text = self.wait_for_log("result:")
        self.assertTrue(text.rstrip().endswith("result: dry-run"), text)
        self.assertIn("dry_run=1", text)
        self.assertIn("notify=thread-1", text)
        self.assertIn("delay=3s", text)
        self.assertIn("command=command", text)
        self.assertIn("app state now: true", text)
        self.assertNotIn("quitting", text)
        self.assertNotIn("never-run", text)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.read("command_args"), "")

    def test_dry_run_with_dry_run_after_dashes_is_a_command_word(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run", "--",
                                 self.paths["command"], "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.wait_for_log("result:").rstrip().endswith("result: dry-run"))

    def test_log_is_private(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.wait_for_log("result:")
        self.assertEqual(stat.S_IMODE(os.stat(self.log).st_mode), 0o600)

@unittest.skipUnless(HAS_PERL, "needs perl to detach")
class LivePathTests(RestartTestCase):
    """The full path, against fake osascript, open and t3."""

    def test_full_path_order_and_result_before_notify(self):
        text = self.live("--", self.paths["command"], wait_for="notify:")
        self.assertEqual(self.calls(), [
            f"quit -e tell application id \"{APP_ID}\" to quit",
            "command app-running=false",
            f"open -b {APP_ID}",
            "t3 thread send thread:1",
            "t3-saw-result",
        ])
        lines = text.splitlines()
        self.assertLess(lines.index("result: ok"), lines.index("notify: accepted"))
        self.assertIn("start: app=", lines[0])
        self.assertIn("command-out", text)
        self.assertIn("command-err", text)
        self.assertIn("While-closed command exit: 0", self.read("message"))

    def test_no_command(self):
        text = self.live(wait_for="notify:")
        self.assertIn("result: ok", text)
        self.assertNotIn("command", [c.split()[0] for c in self.calls()])
        self.assertIn("While-closed command exit: none", self.read("message"))

    def test_probe_error_is_never_treated_as_stopped(self):
        self.set_mode("error")
        text = self.live("--", self.paths["command"])
        self.assertIn("result: failed-to-quit", text)
        self.assertIn("state is 'unknown'", text)
        self.assertNotIn("command app-running", self.read("calls"))
        self.assertNotIn("open -b", self.read("calls"))
        self.assertNotIn("t3 thread", self.read("calls"))

    def test_app_that_never_exits(self):
        self.set_mode("stuck")
        text = self.live("--", self.paths["command"])
        self.assertIn("result: failed-to-quit", text)
        self.assertIn("state is 'true'", text)
        self.assertNotIn("command app-running", self.read("calls"))
        self.assertNotIn("open -b", self.read("calls"))

    def test_command_failure(self):
        self.write("command_status", "3")
        text = self.live("--", self.paths["command"], wait_for="notify:")
        self.assertIn("while-closed exit 3", text)
        self.assertIn("result: while-closed-failed", text)
        self.assertNotIn("result: ok", text)
        self.assertIn("While-closed command exit: 3", self.read("message"))

    def test_app_does_not_reopen(self):
        self.set_mode("noreopen")
        text = self.live("--", self.paths["command"])
        self.assertIn("result: failed-to-open", text)
        self.assertNotIn("t3 thread", self.read("calls"))

    def test_notify_failure_leaves_result_unchanged(self):
        self.set_mode("notifyfail")
        text = self.live("--", self.paths["command"], wait_for="notify:")
        lines = text.splitlines()
        self.assertIn("notify: failed", lines)
        self.assertNotIn("notify: accepted", lines)
        self.assertEqual([line for line in lines if line.startswith("result:")], ["result: ok"])
        self.assertLess(lines.index("result: ok"), lines.index("notify: failed"))
        self.assertGreater(self.calls().count("t3-saw-result"), 1)

    def test_arguments_after_dashes_reach_the_command_unchanged(self):
        args = ["plain", "it's a test", "two  spaces", "$HOME", "*", "--dry-run", "a;b", '"quoted"']
        text = self.live("--", self.paths["command"], *args, wait_for="notify:")
        self.assertEqual(self.read("command_args").splitlines(), args)
        self.assertIn("running while closed: command", text)
        for word in ("it's a test", "two  spaces", "a;b"):
            self.assertNotIn(word, text)

    def test_command_found_on_path(self):
        result = self.run_script("--notify", "thread:1", "--log", self.log, "--delay", "0",
                                 "--", "command", "x", PATH=f"{self.fake}:/usr/bin:/bin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.wait_for_log("notify:")
        self.assertEqual(self.read("command_args").splitlines(), ["x"])

FAKE_PERL_NO_SETSID = """#!/bin/sh
# Real perl, except that POSIX::setsid fails.
exec /usr/bin/perl -e 'BEGIN { require POSIX; no warnings "redefine"; *POSIX::setsid = sub { $! = 1; return undef } }' "$@"
"""

FAKE_PERL_DOES_NOTHING = """#!/bin/sh
# A launcher that never starts the run: no start line will ever appear.
exit 0
"""

class ChildTestCase(RestartTestCase):
    """Runs the detached half directly (T3_RESTART_CHILD=1), as the launcher would."""

    def run_child(self, *args, ack=True, ack_seconds="1", **env_extra):
        if ack:
            with open(self.log + ".go", "w", encoding="utf-8"):
                pass
        env = self.env(T3_RESTART_CHILD="1", T3_RESTART_ACK_SECONDS=ack_seconds, **env_extra)
        argv = ["--notify", "thread:1", "--log", self.log, "--delay", "0", *args]
        with open(self.log, "w", encoding="utf-8") as out:
            return subprocess.run(["/bin/sh", SCRIPT, *argv], stdout=out, stderr=out, check=False,
                                  stdin=subprocess.DEVNULL, timeout=30, env=env)

class AcknowledgementTests(ChildTestCase):
    def test_no_acknowledgement_means_nothing_is_touched(self):
        result = self.run_child("--", self.paths["command"], ack=False)
        self.assertEqual(result.returncode, 1)
        text = self.log_text()
        self.assertIn("result: aborted-no-ack", text)
        self.assertIn("start: app=", text)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.read("command_args"), "")
        self.assertNotIn("quitting", text)

    def test_no_acknowledgement_also_stops_a_dry_run(self):
        result = self.run_child("--dry-run", ack=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: aborted-no-ack", self.log_text())
        self.assertNotIn("result: dry-run", self.log_text())

    def test_acknowledgement_file_is_removed_once_seen(self):
        result = self.run_child("--", self.paths["command"])
        self.assertEqual(result.returncode, 0, self.log_text())
        self.assertIn("result: ok", self.log_text())
        self.assertFalse(os.path.exists(self.log + ".go"))

    def test_a_symlinked_acknowledgement_does_not_count(self):
        target = os.path.join(self.root, "elsewhere")
        with open(target, "w", encoding="utf-8"):
            pass
        os.symlink(target, self.log + ".go")
        result = self.run_child("--", self.paths["command"], ack=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: aborted-no-ack", self.log_text())
        self.assertEqual(self.calls(), [])

    def test_an_existing_acknowledgement_path_is_refused_by_the_launcher(self):
        with open(self.log + ".go", "w", encoding="utf-8"):
            pass
        result = self.run_script("--notify", "t1", "--log", self.log, "--dry-run")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("acknowledgement path exists", result.stderr)
        self.assertFalse(os.path.exists(self.log))

@unittest.skipUnless(HAS_PERL, "needs perl to detach")
class LauncherTests(RestartTestCase):
    def fake_perl(self, body):
        directory = os.path.join(self.root, "fakeperl")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "perl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(path, 0o755)
        return directory

    def test_launcher_that_never_starts_the_run_gives_up_and_never_acknowledges(self):
        directory = self.fake_perl(FAKE_PERL_DOES_NOTHING)
        result = self.run_script("--notify", "t1", "--log", self.log, "--delay", "0",
                                 PATH=f"{directory}:/usr/bin:/bin")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("detach failed", result.stderr)
        self.assertNotIn("detached", result.stdout)
        self.assertFalse(os.path.exists(self.log + ".go"))
        self.assertEqual(self.calls(), [])

    def test_failed_setsid_dies_and_nothing_is_acknowledged(self):
        directory = self.fake_perl(FAKE_PERL_NO_SETSID)
        result = self.run_script("--notify", "t1", "--log", self.log, "--delay", "0",
                                 PATH=f"{directory}:/usr/bin:/bin")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("detached", result.stdout)
        self.assertIn("setsid:", self.log_text())
        self.assertNotIn("start: app=", self.log_text())
        self.assertFalse(os.path.exists(self.log + ".go"))
        self.assertEqual(self.calls(), [])

    def test_dry_run_says_would_never_that_it_quits(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--delay", "7", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would quit in 7s", result.stdout)
        self.assertNotIn("T3 Code quits", result.stdout)
        text = self.wait_for_log("result:")
        self.assertIn("would quit", text)
        self.assertNotIn("quitting", text)

    def test_the_log_is_held_open_and_never_reopened_by_path(self):
        result = self.run_script("--notify", "thread:1", "--log", self.log, "--delay", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        moved = self.log + ".moved"
        os.rename(self.log, moved)
        with open(self.log, "w", encoding="utf-8"):
            pass
        deadline = time.time() + 20
        text = ""
        while time.time() < deadline and "notify:" not in text:
            time.sleep(0.05)
            with open(moved, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("result: ok", text)
        self.assertEqual(self.log_text(), "")

    def test_acknowledgement_is_consumed_by_a_live_run(self):
        self.live(wait_for="notify:")
        self.assertFalse(os.path.exists(self.log + ".go"))

class ResultWriteTests(ChildTestCase):
    def test_failed_result_write_exits_one_without_notifying(self):
        # The run's stdout is a pipe. Every write works until the run reaches the fake `open`,
        # which waits; the test then drops the reader, so the next write (the result line) fails.
        os.unlink(os.path.join(self.fake, "proceed"))
        with open(self.log + ".go", "w", encoding="utf-8"):
            pass
        reader, writer = os.pipe()
        env = self.env(T3_RESTART_CHILD="1", T3_RESTART_ACK_SECONDS="5")
        process = subprocess.Popen(
            ["/bin/sh", "-c", 'trap "" PIPE; exec /bin/sh "$0" "$@"', SCRIPT,
             "--notify", "thread:1", "--log", self.log, "--delay", "0", "--", self.paths["command"]],
            stdout=writer, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL, env=env)
        os.close(writer)
        try:
            deadline = time.time() + 20
            while "open -b" not in self.read("calls") and time.time() < deadline:
                time.sleep(0.02)
            self.assertIn("open -b", self.read("calls"))
        finally:
            os.close(reader)
            self.write("proceed", "go")
        _, stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 1, stderr)
        self.assertIn("write error", stderr)
        self.assertNotIn("t3 thread", self.read("calls"))

class CommandNameTests(ChildTestCase):
    def test_preflight_names_only_the_basename(self):
        hidden = os.path.join(self.root, "private-dir-name", "prog")
        result = self.run_script("--notify", "t1", "--log", self.log, "--", hidden, "arg-secret")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("prog", result.stderr)
        self.assertNotIn("private-dir-name", result.stderr)
        self.assertNotIn("arg-secret", result.stderr)

    def test_a_directory_is_not_an_executable_file(self):
        result = self.run_script("--notify", "t1", "--log", self.log, "--", self.fake)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not an executable file", result.stderr)
        self.assertFalse(os.path.exists(self.log))

    def test_a_command_that_vanished_after_preflight_is_logged_by_basename(self):
        hidden = os.path.join(self.root, "private-dir-name", "prog")
        result = self.run_child("--", hidden, "arg-secret")
        self.assertEqual(result.returncode, 1, self.log_text())
        text = self.log_text()
        self.assertIn("command not found: prog", text)
        self.assertIn("result: while-closed-failed", text)
        self.assertNotIn("private-dir-name", text)
        self.assertNotIn("arg-secret", text)

if __name__ == "__main__":
    unittest.main()
