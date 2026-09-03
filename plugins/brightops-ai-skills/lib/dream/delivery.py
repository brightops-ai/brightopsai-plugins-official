"""Deliver a summary to wherever the person actually looks.

The destination is configuration, never inference. Writing a file is the
zero-configuration default; handing the summary to a command is the extension
point that lets one line of local config route results into a chat platform,
an inbox, or anything else, without this plugin knowing what those are.

An unconfigured command destination is an error rather than a quiet fallback to
writing a file. A delivery that silently went somewhere other than where it was
asked to go is worse than one that failed loudly: the run looks delivered and
nobody reads it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "config.json"
DEFAULT_TIMEOUT_SECONDS = 60


def data_dir(env: dict[str, str] | None = None) -> Path:
    """The per-plugin data directory, which survives plugin updates."""
    env = os.environ if env is None else env
    configured = env.get("CLAUDE_PLUGIN_DATA")
    if configured:
        return Path(configured)
    from .claude_env import config_dir

    return config_dir(env) / "plugins" / "data" / "brightops-ai-skills"


def load_config(env: dict[str, str] | None = None) -> dict:
    path = data_dir(env) / CONFIG_NAME
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass
class Delivery:
    destination: str
    detail: str
    ok: bool = True

    def as_dict(self) -> dict:
        return {"destination": self.destination, "detail": self.detail, "ok": self.ok}


class DeliveryError(RuntimeError):
    """Raised when a configured destination cannot be used as configured."""


def deliver(
    summary: str,
    destination: str | None = None,
    config: dict | None = None,
    env: dict[str, str] | None = None,
    out_dir: Path | None = None,
    runner=subprocess.run,
) -> Delivery:
    """Send ``summary`` to the configured destination."""
    config = load_config(env) if config is None else config
    destination = destination or config.get("destination") or "file"

    if destination == "file":
        target = Path(out_dir) if out_dir else data_dir(env) / "results"
        target.mkdir(parents=True, exist_ok=True)
        path = target / "latest-summary.md"
        path.write_text(summary, encoding="utf-8")
        return Delivery("file", str(path))

    if destination == "command":
        command = config.get("command")
        if not command:
            raise DeliveryError(
                "Destination 'command' is selected but no command is configured. "
                "Set \"command\" in the plugin's config.json. Nothing was sent: "
                "an unconfigured destination is not silently replaced with a file."
            )
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        timeout = config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        try:
            result = runner(
                argv,
                input=summary,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # Unattended runs are the point of this skill, so a command that
            # hangs must produce a reportable failure rather than a traceback.
            raise DeliveryError(
                f"Delivery command {argv[0]!r} did not finish within {timeout}s. "
                "Nothing was delivered."
            ) from None
        except (OSError, ValueError) as error:
            raise DeliveryError(
                f"Delivery command {argv[0]!r} could not be run: {error}"
            ) from None
        if result.returncode != 0:
            raise DeliveryError(
                f"Delivery command exited {result.returncode}: "
                f"{(result.stderr or '').strip()[:300]}"
            )
        return Delivery("command", f"{argv[0]} accepted the summary")

    raise DeliveryError(
        f"Unknown destination {destination!r}. Supported: 'file', 'command'."
    )
