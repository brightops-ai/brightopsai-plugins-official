"""Unit tests for the bundled secret-scan fallback.

Secret-shaped strings are concatenated at runtime so this tracked file does
not itself match gitleaks (or the fallback) when the repo is scanned.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_scanner():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "adversarial-review" / "scripts" / "scan_secrets.py"
    spec = importlib.util.spec_from_file_location("scan_secrets", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _private_key_block() -> str:
    beg = "-----BEGIN"
    mid = "OPENSSH PRIVATE"
    end = "KEY-----"
    return f"{beg} {mid} {end}\nREPLACE_ME_NOT_A_REAL_KEY_BODY\n-----END {mid} {end}\n"


class ScanSecretsFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_scanner()

    def test_clean_prose_has_no_findings(self) -> None:
        text = (
            "Discuss token rotation and the password reset flow in docs.\n"
            "Mention api keys only as a topic, never a value.\n"
        )
        self.assertEqual(self.mod.findings_from_text(text, "plan.md"), [])

    def test_private_key_block_is_named(self) -> None:
        path = "leaky.md"
        hits = self.mod.findings_from_text(_private_key_block(), path)
        self.assertTrue(hits)
        rule, file, line = hits[0]
        self.assertEqual(rule, "private-key")
        self.assertEqual(file, path)
        self.assertEqual(line, 1)

    def test_aws_access_key_id(self) -> None:
        # Amazon's documented example shape, assembled so this file stays clean.
        key = "AKIA" + "IOSFODNN7EXAMPLE"
        hits = self.mod.findings_from_text(f"aws_key={key}\n", "aws.env")
        self.assertTrue(any(h[0] == "aws-access-key-id" for h in hits))

    def test_assignment_of_quoted_secret(self) -> None:
        name = "api_" + "key"
        text = f'{name}="REPLACE_ME_FAKE_VALUE"\n'
        hits = self.mod.findings_from_text(text, "cfg.env")
        self.assertTrue(any(h[0] == "generic-credential" for h in hits))

    def test_scan_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.md"
            path.write_text(_private_key_block(), encoding="utf-8")
            hits = self.mod.scan_file(str(path))
            self.assertEqual(hits[0][0], "private-key")
            self.assertEqual(hits[0][1], str(path))

    def test_github_pat_prefix(self) -> None:
        token = "ghp_" + ("A" * 36)
        hits = self.mod.findings_from_text(token + "\n", "gh.env")
        self.assertTrue(any(h[0] == "github-token" for h in hits))

    def test_stripe_live_prefix(self) -> None:
        token = "sk_live_" + ("a" * 24)
        hits = self.mod.findings_from_text(token + "\n", "stripe.env")
        self.assertTrue(any(h[0] == "stripe-access-token" for h in hits))

    def test_jwt_shape(self) -> None:
        part = "eyJhbGciOiJub25lIn0"
        token = ".".join((part, part, part))
        hits = self.mod.findings_from_text(token + "\n", "auth.md")
        self.assertTrue(any(h[0] == "jwt" for h in hits))


if __name__ == "__main__":
    unittest.main()
