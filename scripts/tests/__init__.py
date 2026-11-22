"""Importing this package installs the test sandbox guard, before any test module loads.

The guard is scripts/test-support/sandbox_guard.py at the repository root. It
points HOME and the Claude config and data overrides at a fresh temp directory
and refuses to run a test when one of them resolves anywhere else. Do not
remove it: without it, a test that forgets one override writes into the real
Claude config or plugin data.
"""

import importlib.util
from pathlib import Path

_GUARD = Path(__file__).resolve().parents[2] / "scripts" / "test-support" / "sandbox_guard.py"
if not _GUARD.is_file():
    raise RuntimeError(
        f"WARNING: the test sandbox guard is missing at {_GUARD}; this suite would run "
        "with no sandbox and WRITE into the real Claude config and plugin data. Refusing."
    )
_spec = importlib.util.spec_from_file_location("sandbox_guard", _GUARD)
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
_guard.install()
