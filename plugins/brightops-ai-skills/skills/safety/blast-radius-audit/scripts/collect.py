#!/usr/bin/env python3
"""Read-only evidence collector for the blast-radius-audit skill.

Prints leads for the eleven checks. What it guarantees, and how:

* Output is built from names and fixed text, never from file content. A lead
  is a location (`file:line`, `env:NAME`, `~/path`), a lead type, and a note
  assembled from things the collector can vouch for: environment variable
  names, file paths, profile, context and host names that pass a strict
  character test, counts, and fixed phrases. Matching lines, hook bodies and
  config values are not printed; the auditor reads them at the cited
  location. Three kinds of value-derived text are shown, each by design:
  the value of a fixed list of context selectors (`AWS_PROFILE`, `NODE_ENV`,
  ...) when it is a plain name or path; the host, port and database name of a
  database URL; and the leading command words of a permission rule. For a
  command line, the program is named and its arguments are counted.
* It never writes, deletes or modifies a file.
* The only programs it starts are `git` (read-only subcommands, in a fixed
  environment with tracing, filesystem-monitor helpers and on-demand fetching
  off) and, with `--github`, `gh`. It starts no shell, so no shell startup
  file runs.
* Anything read through the repository must resolve to a file inside it.
* It opens no network connection unless `--github` is given. That flag adds
  GET requests to github.com through `gh` and nothing else, and the collector
  never fetches the token. `gh` authenticates those requests as it sees fit,
  which can include refreshing an expiring login; omit `--github` if that
  matters.
* A check that could not be examined says so. Missing evidence is reported
  as UNKNOWN or NOT INSPECTED, never as a clean result.

Limits worth knowing: leads are pattern matches (tests, docs and fixtures
included), configuration is read as text rather than parsed as YAML or HCL,
and file and variable NAMES are shown as they are.

Standard library only; runs on Python 3.9+.

    collect.py --repo <path> [--github] [--only 1,3] [--json]
    collect.py --keys <file>        key names of one config file, no values
"""

from __future__ import annotations

import argparse
import configparser
import fnmatch
import ipaddress
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

# gh answers in a second or two and git in milliseconds; a longer wait means a
# hung credential helper or a dead network, and the audit should move on.
SUBPROCESS_TIMEOUT = 15
# Hand-written config and scripts are far below this; larger files are
# generated, minified or binary and only add noise.
MAX_FILE_BYTES = 1_000_000
# Agent config files (~/.claude.json) grow well past MAX_FILE_BYTES.
MAX_CONFIG_BYTES = 30_000_000
# Per lead type. Keeps the report inside an agent's context; the overflow is
# counted in the output, never dropped silently.
MAX_PER_KIND = 40
# Per lead type within one file. One noisy file (a fixture, a doc full of
# examples) must not crowd every other file out of the per-type cap.
MAX_PER_FILE = 5

CHECKS = {
    1: "Test/dev/preview config pointing at a non-local database",
    2: "Credentials this shell can read",
    3: "Recursive deletes with a computed target",
    4: "Infrastructure one command can destroy",
    5: "Rules that exist only as prose",
    6: "GitHub: branch protection and token reach",
    7: "Cloud-synced folder and placeholder files",
    8: "MCP servers, hooks, skills, install scripts and hidden Unicode",
    9: "CI that runs an agent on untrusted input",
    10: "Agent permission modes and safety nets that do not load",
    11: "Tools that send money or messages",
}

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".venv", "venv",
    "__pycache__", ".next", ".nuxt", "target", ".terraform", "coverage",
    ".tox", ".mypy_cache", ".pytest_cache", ".gradle", "Pods", ".cache",
}
DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".adoc")

# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

TOKEN_SHAPES = re.compile(
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----"
    r"|\b[srp]k_(?:live|test)_[0-9A-Za-z]{8,}"
    r"|\bgh[pousr]_[0-9A-Za-z]{20,}"
    r"|\bgithub_pat_[0-9A-Za-z_]{20,}"
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{12,}"
    r"|\bxox[abeprs]-[0-9A-Za-z-]{10,}"
    r"|\beyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}(?:\.[0-9A-Za-z_-]*)?"
    r"|\bsk-[0-9A-Za-z_-]{20,}"
    r"|\bAIza[0-9A-Za-z_-]{30,}"
    r"|\bglpat-[0-9A-Za-z_-]{16,}"
    r"|\bnpm_[0-9A-Za-z]{30,}"
)
SHAPE_LABELS = (
    ("-----BEGIN", "private key header"),
    ("sk_live_", "live payment secret key"),
    ("rk_live_", "live payment restricted key"),
    ("pk_live_", "live payment publishable key"),
    ("sk_test_", "test payment key"),
    ("rk_test_", "test payment key"),
    ("pk_test_", "test payment key"),
    ("github_pat_", "GitHub fine-grained token"),
    ("ghp_", "GitHub classic token"),
    ("gho_", "GitHub OAuth token"),
    ("ghs_", "GitHub app token"),
    ("ghu_", "GitHub user-to-server token"),
    ("ghr_", "GitHub refresh token"),
    ("AKIA", "AWS long-lived access key id"),
    ("ASIA", "AWS temporary access key id"),
    ("xox", "Slack token"),
    ("eyJ", "JWT"),
    ("sk-", "API key (sk- prefix)"),
    ("AIza", "Google API key"),
    ("glpat-", "GitLab token"),
    ("npm_", "npm token"),
)
URL_USERINFO = re.compile(r"(?<=://)[^/\s@'\"]+@")
SECRET_WORD = (
    r"(?:secret|token|passw(?:or)?d|passwd|pwd|api[_-]?key|apikey|access[_-]?key"
    r"|private[_-]?key|credential|authorization|bearer|auth[_-]?(?:token|key)|dsn)"
)
ASSIGN = re.compile(
    r"(?i)([A-Za-z0-9_.\-\"']*" + SECRET_WORD + r"[A-Za-z0-9_.\-\"']*\s*[:=]\s*)"
    r"((?:Bearer|Basic|Token)\s+\S+|\"[^\"]*\"|'[^']*'|[^\s,;)]+)"
)
# A value that names where the secret comes from rather than being one.
REFERENCE = re.compile(
    r"^[\"']?(?:\$|\{\{|<|%|os\.|process\.|ENV\b|env\.|secrets\.|vars?\.|getenv"
    r"|None\b|null\b|true\b|false\b|[\"']?$)"
)
BLOB = re.compile(r"[A-Za-z0-9+/=_-]{24,}")
SECRET_FLAG = re.compile(r"(?i)^--?[\w-]*" + SECRET_WORD + r"[\w-]*$")
PLACEHOLDER = re.compile(
    r"(?i)^(?:|replace[_-]?me.*|change[_-]?me.*|x{3,}|your[-_ ].*|<.*>|todo|example.*"
    r"|dummy.*|test|password|secret|none|null|\*+|.*REPLACE_ME.*)$"
)
PROD_LIKE = re.compile(r"(?i)(?<![a-z])(?:prod(?:uction)?|prd|live)(?![a-z])")


def looks_random(text: str) -> bool:
    """True for a string that reads as key material rather than a word or path."""
    if len(text) < 24:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{32,}", text):
        return True
    separators = sum(text.count(ch) for ch in "/-_")
    mixed = (
        any(c.isupper() for c in text)
        and any(c.islower() for c in text)
        and any(c.isdigit() for c in text)
    )
    # Paths and identifiers are separator-heavy; base64 and tokens are not.
    return mixed and separators / len(text) < 0.15


def redact(text: str) -> str:
    """Remove anything value-shaped from a line that is about to be printed.

    Over-redaction is the intended failure mode: a snippet that loses a path
    still has its file:line beside it, a snippet that keeps a key does harm.
    """
    text = TOKEN_SHAPES.sub("<redacted>", text)
    text = URL_USERINFO.sub("<redacted>@", text)

    def _assign(match: re.Match) -> str:
        if REFERENCE.match(match.group(2)):
            return match.group(0)
        return match.group(1) + "<redacted>"

    text = ASSIGN.sub(_assign, text)
    return BLOB.sub(lambda m: "<redacted>" if looks_random(m.group(0)) else m.group(0), text)


NAME_SAFE = re.compile(r"^[A-Za-z0-9_.@:/~+*\- ]{1,120}$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,80}$")
SELECTOR_VALUE = re.compile(r"^[A-Za-z0-9_.:/~@-]{1,100}$")
PROGRAM = re.compile(r"^[\w.+-]{1,40}$")
SCRIPT_ARG = re.compile(r"^(?:\$\{?[A-Z_]{1,40}\}?/?)?[\w./-]{1,160}\.(?:sh|bash|zsh|py|js|mjs|cjs|ts|rb|ps1)$")
PACKAGE_ARG = re.compile(r"^(?:@[a-z0-9._-]{1,60}/)?[A-Za-z0-9._-]{1,80}(?:(?:@|==)[\w.\-^~*]{1,40})?$")
STATE_OR_VARS = re.compile(r"\.tfstate(?:\.|$)|\.tfvars(?:\.json)?$")
HOST_SAFE = re.compile(r"^(?:[A-Za-z0-9._\-${}]{1,253}|[0-9A-Fa-f:.]{2,45})$")
SETTING_WORDS = {
    "true", "false", "never", "always", "on-request", "on-failure", "untrusted", "danger-full-access",
    "workspace-write", "read-only", "yolo", "auto", "default", "manual", "plan", "acceptedits",
    "bypasspermissions", "dontask", "disable", "enabled", "disabled", "trusted",
}
PERMISSION_MODES = {"default", "manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}


def safe_name(value: object) -> str:
    """Pass a NAME through (profile, context, host, package, key); withhold anything else.

    The collector's output is built from names it can vouch for. A string
    with characters a name does not need, or one that reads as key material,
    is not shown, because nothing can prove it is not a value.
    """
    text = str(value)
    if not NAME_SAFE.match(text) or TOKEN_SHAPES.search(text) or looks_random(text):
        return "<withheld>"
    return text


def safe_names(values, limit: int = 20) -> str:
    values = list(values)
    shown = ", ".join(safe_name(v) for v in values[:limit])
    return shown + (f" (+{len(values) - limit} more)" if len(values) > limit else "")


INTERPRETERS = {"bash", "sh", "zsh", "dash", "python", "python3", "node", "ruby", "deno", "bun", "pwsh",
                "powershell", "tsx", "ts-node", "perl", "php"}
COMMAND_WORD = re.compile(r"^(?:[a-z]{2,12}|--[a-z][a-z-]{1,24}|-[A-Za-z]{1,4}|\*)$")
PATH_GLOB = re.compile(r"^[\w./*~-]{1,80}$")
MULTILINE = "\0multi-line value"


def _tokens(command: object) -> list[str]:
    if isinstance(command, (list, tuple)):
        return [str(t) for t in command]
    try:
        return shlex.split(str(command))
    except ValueError:
        return str(command).split()


def command_summary(command: object) -> str:
    """Name the program a command line runs, and its script when an interpreter is given one.

    Nothing else is shown. Arguments are where inline secrets live
    (`-pPASSWORD`, a token as a bare positional). A pattern can check how an
    argument is spelled but not what it means, so only a position whose
    meaning is fixed (the script after an interpreter) is ever shown, and the
    rest are counted.
    """
    tokens = _tokens(command)
    while tokens and re.match(r"^[A-Za-z_]\w*=", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return "runs nothing recognisable"
    return launch_summary(tokens[0].strip("\"'"), [t.strip("\"'") for t in tokens[1:]])


def launch_summary(command: str, args: list[str]) -> str:
    """Program, plus the one argument whose position fixes its meaning: an
    interpreter's script, or the package an npx-style launcher fetches."""
    base = os.path.basename(command or "")
    shown = base if PROGRAM.match(base) and not looks_random(base) else "<program withheld>"
    named = ""
    if base in INTERPRETERS and args and SCRIPT_ARG.match(args[0]):
        named = args[0]
    elif base in ("npx", "bunx", "pnpx", "uvx"):
        candidate = next((a for a in args if not a.startswith("-")), "")
        if PACKAGE_ARG.match(candidate) and not looks_random(candidate):
            named = candidate
    rest = len(args) - (1 if named else 0)
    out = "runs " + " ".join(filter(None, [shown, named]))
    return out + (f" (+{rest} arguments not shown)" if rest > 0 else "")


def rule_head(rule: object) -> str:
    """A permission rule up to its leading command words: `Bash(git push --force *)`.

    Rule bodies can hold whole commands (an "always allow" rule records the
    command as typed, tokens included), so a body is shown only as far as it
    reads as a program followed by subcommands and flags.
    """
    found = re.match(r"^([A-Za-z_][\w*-]{0,100})(?:\((.*)\))?$", str(rule), re.S)
    if not found:
        return "<rule not shown>"
    tool, body = found.group(1), found.group(2)
    if body is None:
        return tool
    if tool != "Bash":
        return f"{tool}({body})" if PATH_GLOB.match(body) and not looks_random(body) else f"{tool}(...)"
    words = body.replace(":*", " *").split()
    shown = []
    for index, word in enumerate(words):
        if index == 0:
            accepted = bool(PROGRAM.match(word)) and not looks_random(word)
        else:
            accepted = bool(COMMAND_WORD.match(word))
        if not accepted:
            break
        shown.append(word)
    if not shown:
        return "Bash(...)"
    return f"Bash({' '.join(shown)}{'' if len(shown) == len(words) else ' ...'})"


def netrc_machines(text: str) -> list[str] | None:
    """Machine names from netrc text, read by token position. None if it cannot be tokenised.

    A quoted password may contain the word `machine`; only a token that
    follows the keyword in keyword position is a machine name.
    """
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    machines, index = [], 0
    while index < len(tokens):
        token = tokens[index]
        if token == "macdef":
            break  # a macro body is free text; nothing after it is trusted
        if token == "machine" and index + 1 < len(tokens):
            machines.append(tokens[index + 1])
            index += 2
        elif token in ("login", "password", "account"):
            index += 2
        else:
            index += 1
    return machines


def env_assignments(text: str) -> list[tuple[int, str, str]]:
    """(line, key, value) for each assignment in dotenv text.

    A quoted value can span lines (a PEM key). Its continuation lines are
    skipped rather than mistaken for assignments, and the value comes back as
    the MULTILINE marker.
    """
    def closes(rest: str, quote: str) -> bool:
        return re.search(r"(?<!\\)" + re.escape(quote), rest) is not None

    found, quote = [], ""
    for lineno, line in enumerate(text.splitlines(), 1):
        if quote:
            if closes(line, quote):
                quote = ""
            continue
        match = ENV_LINE.match(line)
        if not match or line.lstrip().startswith("#"):
            continue
        key, value = match.group(1)[:80], match.group(2).strip()
        if value[:1] in ("'", '"', "`") and not closes(value[1:], value[0]):
            quote = value[0]
            found.append((lineno, key, MULTILINE))
        else:
            found.append((lineno, key, value.strip("\"'")))
    return found


def key_listing(path: Path) -> list[str]:
    """Key names of one config file, never its values: for `--keys`."""
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFIG_BYTES:
            return ["not a regular file, or too large: not read"]
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ["cannot be read"]
    name = path.name.lower()
    if name.endswith((".json", ".jsonc")) or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return ["not valid JSON: key names unavailable"]
        rows: list[str] = []

        def walk(node: object, trail: str) -> None:
            if len(rows) >= 2000:
                return
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{trail}.{safe_name(key)}" if trail else safe_name(key))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{trail}[{index}]")
            else:
                rows.append(f"{trail} ({type(node).__name__})")

        walk(data, "")
        return rows
    if name.endswith(".toml"):
        return [f"[{safe_name(table) or 'top level'}] {safe_names(sorted(values), 60)}"
                for table, values in parse_toml_tables(text).items() if values]
    return [f"{lineno}: {key}" + (" (multi-line value)" if value == MULTILINE else "")
            for lineno, key, value in env_assignments(text)]


def github_slug(url: str) -> tuple[str, str] | None:
    """(owner, repo) when the remote's HOST is exactly github.com, else None."""
    found = re.match(r"^(?:https?://(?:[^@/\s]+@)?|ssh://(?:[^@/\s]+@)?|[\w.-]+@)github\.com[:/]"
                     r"([\w.-]{1,100})/([\w.-]{1,100}?)(?:\.git)?/?$", url.strip())
    return (found.group(1), found.group(2)) if found else None


def branch_verdict(protection: object, rules: object, held: list) -> str:
    """One line on the default branch. Missing evidence stays unknown; it is never read as 'unprotected'."""
    types = sorted({str(r.get("type")) for r in rules if isinstance(r, dict)}) if isinstance(rules, list) else []
    if isinstance(protection, dict):
        bound = bool((protection.get("enforce_admins") or {}).get("enabled"))
        if "admin" in held and not bound:
            if types:
                return ("the classic rules do not bind this admin token; rulesets also exist and who may bypass "
                        "them was not checked, so the effective protection is UNKNOWN")
            if not isinstance(rules, list):
                return ("the classic rules do not bind this admin token; rulesets could not be read, so the "
                        "effective protection is UNKNOWN")
            return ("THIS TOKEN CAN BYPASS THE PROTECTION: it has admin on the repo, the classic rules are "
                    "not enforced for admins, and no ruleset applies, so a direct push to the default branch "
                    "is accepted")
        return "classic protection applies to this token as far as the API shows"
    if types:
        return ("rulesets are present; who may bypass them was not checked, so whether this token is bound "
                "is UNKNOWN")
    if protection == "HTTP 404" and "admin" in held and isinstance(rules, list):
        return "NO PROTECTION: an admin token read both the classic rules and the rulesets and found none"
    return ("UNKNOWN: the protection settings could not be read with this token "
            f"(classic: {protection if isinstance(protection, str) else 'n/a'}; "
            f"rulesets: {rules if isinstance(rules, str) else 'none listed'}). Check in the repository settings")


def shape_label(text: str) -> str:
    match = TOKEN_SHAPES.search(text)
    if not match:
        return ""
    found = match.group(0)
    for prefix, label in SHAPE_LABELS:
        if found.startswith(prefix):
            return label
    return "token-shaped string"


# --------------------------------------------------------------------------
# Hosts and database URLs
# --------------------------------------------------------------------------

DB_URL = re.compile(
    r"\b((?:jdbc:)?(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|mssql"
    r"|sqlserver|cockroachdb|amqps?|clickhouse|libsql|oracle)(?:\+[a-z0-9]+)?"
    r"://[^\s'\"<>`)]+)",
    re.I,
)
LOCAL_NAMES = {"localhost", "host.docker.internal", "0.0.0.0", "::1", "ip6-localhost"}


HOST_RANK = ("local", "service-name", "no-host", "from-variable", "unknown", "private-network", "non-local")


def _classify_one(host: str) -> str:
    name = (host or "").strip().strip("[]").lower()
    if not name:
        return "no-host"
    if "$" in name or "{" in name or "%" in name:
        return "from-variable"
    if name in LOCAL_NAMES or name.endswith(".localhost"):
        return "local"
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        if address.is_loopback or address.is_unspecified:
            return "local"
        return "private-network" if address.is_private else "non-local"
    if "." not in name:
        # A bare word is a compose service or container alias in practice.
        return "service-name"
    if name.endswith((".local", ".internal", ".lan", ".svc", ".home", ".test")):
        return "private-network"
    return "non-local"


def classify_host(host: str) -> str:
    """local | service-name | private-network | non-local | from-variable | no-host

    A host list (MongoDB, libpq) is as remote as its most remote member.
    """
    parts = [part for part in (host or "").split(",") if part.strip()] or [""]
    return max((_classify_one(part) for part in parts), key=HOST_RANK.index)


def sanitize_db_url(url: str) -> tuple[str, str]:
    """Return (scheme://host:port/db, class) with credentials and query removed.

    Anything that does not parse into plain host names is reported as
    unparseable rather than echoed.
    """
    raw = url[5:] if url.lower().startswith("jdbc:") else url
    scheme = raw.split("://", 1)[0].lower()
    if not re.fullmatch(r"[a-z][a-z0-9+.-]{1,30}", scheme):
        return "<unparseable>", "unknown"
    unknown = (f"{scheme}://<unparseable>", "unknown")
    try:
        parts = urlsplit(raw)
    except ValueError:
        return unknown
    # An unescaped '/', '?' or '#' in a password moves part of the password
    # into the path. Refuse to echo anything from such a URL.
    if "@" in parts.path + parts.query + parts.fragment or raw.count("@") > 1:
        return unknown
    hosts, port = [], ""
    for item in parts.netloc.rpartition("@")[2].split(","):
        if item.startswith("["):
            host, _, rest = item[1:].partition("]")
            item_port = rest.lstrip(":")
        else:
            host, _, item_port = item.partition(":")
        if host and (not HOST_SAFE.match(host) or looks_random(host)):
            return unknown
        if item_port and not re.fullmatch(r"\d{1,5}|\$\{?\w{1,40}\}?", item_port):
            return unknown
        hosts.append(host)
        port = port or item_port
    shown = f"{scheme}://{','.join(h or '<no host>' for h in hosts)}"
    if port.isdigit() and len(hosts) == 1:
        shown += f":{port}"
    database = parts.path.strip("/").split("/")[0]
    if re.fullmatch(r"[\w.${}-]{1,64}", database or "") and not looks_random(database):
        shown += f"/{database}"
    return shown, classify_host(",".join(hosts))


def value_hints(value: str) -> list[str]:
    """Describe a value without quoting it."""
    if value == "":
        return ["empty"]
    hints = []
    label = shape_label(value)
    if label:
        hints.append(label)
    match = DB_URL.search(value)
    if match:
        shown, klass = sanitize_db_url(match.group(1))
        hints.append(f"-> {shown} [{klass}]")
    elif re.match(r"^[a-z][a-z0-9+.-]*://[^/\s@]+@", value, re.I):
        try:
            host = urlsplit(value).hostname or ""
        except ValueError:
            host = ""
        host = host if HOST_SAFE.match(host) and not looks_random(host) else "<withheld>"
        hints.append(f"URL with embedded credentials -> host {host}")
    return hints


# --------------------------------------------------------------------------
# Line patterns for tracked files
# --------------------------------------------------------------------------

RM_RECURSIVE = re.compile(
    r"\brm\s+(?:-{1,2}[\w-]+\s+)*?(?:-[A-Za-z]*[rR][A-Za-z]*|--recursive)\b(.*)"
)
BYPASS = re.compile(
    r"--dangerously-skip-permissions|--allow-dangerously-skip-permissions"
    r"|--dangerously-bypass-approvals-and-sandbox|--yolo\b|--full-auto\b"
    r"|bypassPermissions|--permission-mode[= ]\S*bypass|--trust-all-tools"
    r"|--approval-mode[= ]yolo|approval_policy\s*=\s*[\"']never|danger-full-access"
    r"|--no-sandbox\b|IS_SANDBOX=1|--auto-approve-all"
    r"|(?i:auto[_-]?approve[\"']?\s*[:=]\s*(?:true|\[))|alwaysAllow[\"']?\s*:"
)
AGENT_SETTING = re.compile(
    r"(?i)yolo|auto[_-]?approve|autoaccept|auto[_-]?run|skip[_-]?permissions|bypass"
    r"|approval[_-]?(?:policy|mode)|sandbox[_-]?mode|trust[_-]?level|danger"
)
AGENT_MARKER = re.compile(
    r"(?i)claude-code-(?:base-)?action|\bclaude\s+(?:-p\b|--print\b)|@anthropic-ai/claude-code"
    r"|openai/codex-action|\bcodex\s+exec\b|@openai/codex|run-gemini-cli"
    r"|\bgemini\s+(?:-p\b|--prompt\b|--yolo\b)|cursor-agent|\baider\b|\bopencode\s+run\b"
    r"|copilot-swe-agent|\bgoose\s+run\b|anthropic[_-]api[_-]key|openai[_-]api[_-]key"
    r"|gemini[_-]api[_-]key"
)

# (check, kind, regex, scan_docs)
LINE_PATTERNS = [
    (1, "destructive-db-op", re.compile(
        r"(?i:\bdrop\s+(?:table|database|schema)\b|\btruncate\s+table\b|migrate:(?:fresh|reset|refresh)"
        r"|\bdb:(?:reset|drop|purge|wipe)\b|\bmigrate\s+reset\b|--force-reset\b|\bflush(?:db|all)\b"
        r"|\bdrop_all\s*\(|dropDatabase\s*\(|sync\(\s*\{\s*force\s*:\s*true"
        r"|deleteMany\(\s*(?:\{\s*\})?\s*\)|\bdb\s+reset\b|--accept-data-loss)"
        r"|\bTRUNCATE\s+[\"`\w]"), False),
    (1, "db-migrate-command", re.compile(
        r"(?i)\b(?:prisma\s+migrate\s+(?:deploy|dev)|prisma\s+db\s+push|alembic\s+upgrade"
        r"|knex\s+migrate|ra(?:ke|ils)\s+db:(?:migrate|setup|schema:load)|manage\.py\s+(?:migrate|flush)"
        r"|sequelize(?:-cli)?\s+db:migrate|drizzle-kit\s+(?:push|migrate)|typeorm\s+migration:run"
        r"|flyway\s+(?:migrate|clean)|supabase\s+db\s+push|goose\s+up|atlas\s+schema\s+apply)"), False),
    (3, "recursive-delete-call", re.compile(
        r"shutil\.rmtree\s*\(|\brimraf\b|\.rm(?:Sync)?\s*\([^)]*recursive|rmdirSync\s*\([^)]*recursive"
        r"|\bfse?\.(?:remove|emptyDir)(?:Sync)?\s*\(|Remove-Item\b.*-Recurse|\bfind\b.*\s-delete\b"
        r"|\bfind\b.*-exec\s+rm\b|\bgit\s+clean\s+-[A-Za-z]*[fdxX]|FileUtils\.rm_r?f?\b"
        r"|os\.RemoveAll\s*\(|remove_dir_all\s*\(|\brmdir\s+/s\b|\bdel\s+/[sqf]\b"
        r"|deleteRecursively\s*\(|\bxargs\s+(?:-\S+\s+)*rm\b|\brsync\b.*--delete|\brobocopy\b.*/MIR"), True),
    (3, "changes-home", re.compile(
        r"(?:^|[\s;&|])(?:export\s+)?(?:HOME|USERPROFILE|XDG_(?:CONFIG|DATA|CACHE)_HOME)="
        r"|environ\[[\"'](?:HOME|USERPROFILE)[\"']\]\s*=|setenv\(\s*[\"'](?:HOME|USERPROFILE)[\"']"
        r"|process\.env\.(?:HOME|USERPROFILE)\s*=|set_var\(\s*\"HOME\"|Setenv\(\s*\"HOME\""), False),
    (4, "auto-approve-flag", re.compile(
        r"-auto-approve\b|auto_approve\s*[:=]\s*true|\bpulumi\s+(?:up|destroy|refresh)\b.*(?:\s-y\b|--yes\b|--skip-preview)"
        r"|\bcdk\s+(?:deploy|destroy)\b.*(?:--require-approval[= ]never|--force\b)"
        r"|--yes-i-really-mean-it|--no-confirm\b|--skip-confirmation\b|--assume-yes\b"), True),
    (4, "destroy-command", re.compile(
        r"\b(?:terraform|tofu|terragrunt)\s+(?:[\w=./-]+\s+)*destroy\b|\bpulumi\s+destroy\b|\bcdk\s+destroy\b"
        r"|\bkubectl\s+delete\b|\bhelm\s+(?:uninstall|delete)\b|\baws\s+\S+\s+delete-\S+"
        r"|\baws\s+s3\s+(?:rb|rm)\b.*(?:--force|--recursive)|\bgcloud\s+.*\bdelete\b|\baz\s+.*\bdelete\b"
        r"|\bdropdb\b|\bdoctl\s+.*\bdelete\b|\bfly(?:ctl)?\s+(?:apps\s+)?destroy\b"
        r"|\bheroku\s+(?:apps:destroy|pg:reset)|\bsupabase\s+projects\s+delete|\bdocker\s+(?:system|volume)\s+prune"
        r"|\bdocker\s+compose\s+down\b.*(?:\s-v\b|--volumes)|\bgh\s+repo\s+delete\b|\bvercel\s+(?:rm|remove)\b"), True),
    (4, "force-flag", re.compile(
        r"\bgit\s+push\b.*(?:--force\b|--force-with-lease|\s-f\b)|\bgit\s+reset\s+--hard\b"
        r"|\bgit\s+branch\s+-D\b|\b(?:npm|pnpm|yarn)\s+publish\b"), True),
    (4, "protection-off", re.compile(
        r"(?i)deletion_?protection(?:_enabled)?[\"']?\s*[:=]\s*[\"']?false|force_destroy\s*=\s*true"
        r"|skip_final_snapshot\s*=\s*true|DeletionPolicy[\"']?\s*:\s*[\"']?Delete\b"
        r"|prevent_destroy\s*=\s*false|backup_retention_period\s*=\s*0\b"
        r"|termination_?protection[\"']?\s*[:=]\s*[\"']?false"), False),
    (2, "instruction-prints-secret", re.compile(
        r"\bprintenv\s+[A-Za-z_]|--no-masking\b|\bcat\s+\S*\.env\b|\bgh\s+auth\s+token\b"
        r"|\becho\s+[\"']?\$\{?\w*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY)\w*"
        r"|\bset\s+-x\b.*(?:secret|token|password)|--reveal\b|--show-secrets?\b"), True),
    (5, "skips-a-control", re.compile(
        r"\bgit\s+(?:commit|push|merge)\b.*--no-verify\b|\bHUSKY=0\b|\bSKIP=\S+\s+git\b"
        r"|--no-gpg-sign\b|\[skip ci\]|\[ci skip\]|--admin\b.*\bmerge\b|\bmerge\b.*--admin\b"), True),
    (8, "bypass-flag", BYPASS, True),
    (8, "package-install-in-script", re.compile(
        r"\b(?:npm|pnpm|yarn|bun)\s+(?:install|add|i)\b(?!\s+--frozen-lockfile)|\bpip3?\s+install\b"
        r"|\bplugin\s+install\b|\b(?:gem|cargo|go|brew)\s+install\b"), False),
    (8, "unpinned-or-remote-install", re.compile(
        r"\bnpx\s+(?:-y|--yes)\b|\S@latest\b|\bcurl\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b"
        r"|\bwget\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b|\bpipx\s+run\b|\biex\s*\("), True),
    (11, "moves-money", re.compile(
        r"(?i)\bstripe\.(?:paymentIntents|transfers|payouts|charges|refunds|invoices)\."
        r"|\b(?:create_?(?:payout|transfer|charge|refund|payment)|send_?(?:money|payment|funds)"
        r"|wire_?transfer|payouts?\.create|transfers?\.create|sendTransaction|eth_sendTransaction"
        r"|signAndSend|braintree|paypal|plaid|adyen|dwolla)\b"
        r"|\b\w*(?:Transfer|Payout|Charge|Refund|PaymentIntent)\.create\s*\("), False),
    (11, "sends-messages", re.compile(
        r"(?i)\b(?:twilio|sendgrid|sgMail|mailgun|postmark|nodemailer|smtplib|sendmail|resend\.emails"
        r"|ses\.send\w*|sns\.publish|chat\.postMessage|chat_postMessage|send_?message|send_?email"
        r"|send_?sms|messages\.create|messages\.send|webhook\.send)\b"), False),
]

DB_HOST_KEY = re.compile(
    r"(?i)\b((?:db|database|pg|postgres|mysql|mongo|redis|sql)[a-z_]*host)[\"']?\s*[:=]\s*[\"']?"
    r"([A-Za-z0-9_.\-${}:]+)"
)

RULE_FILE_NAMES = {
    "AGENTS.md", "AGENTS.override.md", "AGENT.md", "CLAUDE.md", "CLAUDE.local.md",
    "GEMINI.md", ".cursorrules", ".windsurfrules", ".clinerules", ".goosehints",
    "CONVENTIONS.md", "copilot-instructions.md", ".rules",
}
RULE_DIR_MARKERS = (
    ".cursor/rules/", ".claude/rules/", ".claude/commands/", ".claude/agents/",
    ".windsurf/rules/", ".github/instructions/", ".github/prompts/", ".clinerules/",
    ".roo/rules/", ".kiro/steering/",
)
RULE_LINE = re.compile(
    r"(?i)\b(?:never|must not|mustn't|do not|don't|always|ask (?:me |the user |first|before)"
    r"|before (?:you )?(?:push|merg|deploy|delet|commit|releas)\w*|code freeze|frozen|forbidden"
    r"|prohibited|off[- ]limits|read[- ]only|without (?:asking|approval|permission|confirmation)"
    r"|requires? (?:approval|confirmation|review)|only (?:with|after) (?:approval|permission)"
    r"|confirm (?:first|before))\b"
)

UNTRUSTED_TRIGGERS = (
    "pull_request_target", "issue_comment", "issues", "pull_request_review_comment",
    "pull_request_review", "discussion_comment", "discussion", "workflow_run",
)
ALL_TRIGGERS = UNTRUSTED_TRIGGERS + ("pull_request", "push", "schedule", "workflow_dispatch")
UNTRUSTED_EXPR = re.compile(
    r"\$\{\{[^}]*github\.(?:head_ref|event\.(?:issue|comment|pull_request|review|discussion|head_commit)"
    r"\.[\w.]*(?:body|title|message|ref|label|name|email))"
)

TF_RESOURCE = re.compile(r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')
TF_DATA_TYPES = re.compile(
    r"db_instance|rds_cluster|dynamodb_table|s3_bucket$|sql_database_instance|storage_bucket$"
    r"|spanner_(?:instance|database)|bigtable_instance|bigquery_dataset|sql_server|sql_database"
    r"|(?:postgresql|mysql|mariadb)_(?:flexible_)?server|cosmosdb_account|storage_account$"
    r"|docdb_cluster|elasticache_(?:cluster|replication_group)|redshift_cluster|efs_file_system"
    r"|opensearch_domain|kms_key$|firestore_database|neptune_cluster|memorydb_cluster|key_vault$"
    r"|ebs_volume|managed_disk|database_cluster|backup_vault"
)

DB_CONFIG_FILE = re.compile(
    r"(?i)(?:^|/)(?:(?:docker-)?compose[^/]*\.ya?ml|schema\.prisma|database\.ya?ml|alembic\.ini"
    r"|knexfile\.[cm]?[jt]s|ormconfig\.\w+|drizzle\.config\.\w+|settings\.py)$|(?:^|/)migrations?/"
)
IAC_FILE = re.compile(
    r"(?i)(?:^|/)(?:Pulumi\.ya?ml|cdk\.json|Chart\.ya?ml|serverless\.ya?ml|kustomization\.ya?ml"
    r"|Dockerfile[^/]*|(?:docker-)?compose[^/]*\.ya?ml|template\.ya?ml)$|\.tf$|\.bicep$"
)
LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock")
IGNORE_PROBES = (".env", ".env.local", "key.pem", "id_rsa", "terraform.tfstate")

SENSITIVE_TRACKED = re.compile(
    r"(?i)(?:^|/)(?:id_(?:rsa|dsa|ecdsa|ed25519)|[^/]*\.(?:pem|p12|pfx|jks|keystore|ppk|key|ovpn)"
    r"|\.env(?:\.[\w.-]+)?|[^/]*\.env|\.envrc|credentials(?:\.json)?|service[-_]?account[^/]*\.json"
    r"|\.netrc|\.pgpass|\.npmrc|\.pypirc|[^/]*kubeconfig[^/]*|secrets?\.(?:ya?ml|json|toml)"
    r"|[^/]*\.tfvars(?:\.json)?|\.htpasswd|\.git-credentials)$"
)
EXAMPLE_NAME = re.compile(r"(?i)example|sample|template|\.dist$|\.pub$|fixture")
ENV_FILE = re.compile(r"(?i)^(?:\.env(?:\..+)?|.+\.env|\.envrc|\.dev\.vars|\.flaskenv)$")
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(.*)$")
SECRET_NAME = re.compile(r"(?i)" + SECRET_WORD)

CRED_ENV = re.compile(
    r"(?i)secret|token|passw|api_?key|access_?key|private_?key|credential|_dsn$|database_url"
    r"|_db_url|conn(?:ection)?_?str|^pg(?:password|user|service)$|^aws_|^azure_|^arm_|^google_"
    r"|^gcloud|^cloudsdk_|^kube|^stripe_|^twilio_|^sendgrid_|^docker_(?:host|config)|^vault_"
    r"|^tf_var_|^tf_token|^digitalocean|^cloudflare_|^vercel_|^netlify_|^fly_|^heroku_|^supabase_"
    r"|^slack_|^openai_|^anthropic_|^gemini_|^mongo|^redis_url|^mysql_"
)
# Variables whose value is a context name or a path, not a secret. Printed so
# the audit can answer "is the default context production?".
SELECTORS = {
    "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "KUBECONFIG",
    "CLOUDSDK_ACTIVE_CONFIG_NAME", "CLOUDSDK_CORE_PROJECT", "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_APPLICATION_CREDENTIALS", "NODE_ENV", "RAILS_ENV", "APP_ENV", "ENVIRONMENT",
    "FLASK_ENV", "DJANGO_SETTINGS_MODULE", "TF_WORKSPACE", "PGHOST", "PGDATABASE", "PGPORT",
    "BASH_ENV", "ENV",
}

# (path relative to home, what it holds). Existence, mode and size only.
CRED_PATHS = [
    (".aws/sso/cache", "AWS SSO token cache"),
    (".azure", "Azure CLI profile and token cache"),
    (".pypirc", "PyPI upload credentials"),
    (".terraform.d/credentials.tfrc.json", "Terraform Cloud token"),
    (".config/doctl/config.yaml", "DigitalOcean token"),
    (".fly/config.yml", "Fly.io token"),
    (".config/netlify/config.json", "Netlify token"),
    ("Library/Application Support/com.vercel.cli/auth.json", "Vercel token"),
    (".local/share/com.vercel.cli/auth.json", "Vercel token"),
    (".config/configstore/firebase-tools.json", "Firebase token"),
    (".supabase/access-token", "Supabase token"),
    (".railway/config.json", "Railway token"),
    (".wrangler/config/default.toml", "Cloudflare token"),
    ("Library/Preferences/.wrangler/config/default.toml", "Cloudflare token"),
    (".config/heroku", "Heroku CLI state"),
    (".my.cnf", "MySQL client password file"),
    (".boto", "boto/GCS credentials"),
    (".s3cfg", "s3cmd credentials"),
    (".config/rclone/rclone.conf", "rclone remotes and secrets"),
    (".vault-token", "Vault token"),
    (".config/op", "1Password CLI state"),
    (".oci/config", "Oracle Cloud credentials"),
    (".config/hcloud/cli.toml", "Hetzner token"),
    (".codex/auth.json", "Codex CLI login"),
    (".claude/.credentials.json", "Claude Code login"),
]

MCP_CONFIGS_REPO = [
    ".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".gemini/settings.json",
    ".claude/settings.json", ".claude/settings.local.json", ".roo/mcp.json",
    ".amazonq/mcp.json", "opencode.json",
]
MCP_CONFIGS_HOME = [
    ".claude.json", ".claude/settings.json", ".claude/settings.local.json", ".cursor/mcp.json",
    ".gemini/settings.json", ".codeium/windsurf/mcp_config.json", ".config/opencode/opencode.json",
    "Library/Application Support/Claude/claude_desktop_config.json",
    "Library/Application Support/Code/User/mcp.json", ".config/Code/User/mcp.json",
    ".config/zed/settings.json", ".aws/amazonq/mcp.json",
]
CLAUDE_SETTINGS_REPO = [".claude/settings.json", ".claude/settings.local.json"]
CLAUDE_SETTINGS_HOME = [".claude/settings.json", ".claude/settings.local.json"]
OTHER_AGENT_SETTINGS_HOME = [
    ".codex/config.toml", ".gemini/settings.json", ".cursor/cli-config.json",
    "Library/Application Support/Code/User/settings.json", ".config/Code/User/settings.json",
    ".config/opencode/opencode.json",
]
SKILL_ROOTS_HOME = [".claude/skills", ".agents/skills", ".codex/skills", ".cursor/skills", ".gemini/skills"]
SKILL_ROOTS_REPO = [".claude/skills", ".agents/skills", ".codex/skills", ".cursor/skills"]
RC_FILES = [
    ".zshenv", ".zprofile", ".zshrc", ".bashrc", ".bash_profile", ".bash_aliases", ".profile",
    ".aliases", ".config/fish/config.fish",
]
SENDS_HINT = re.compile(
    r"(?i)stripe|paypal|plaid|bank|wallet|payment|slack|gmail|mail|twilio|sms|discord|telegram"
    r"|whatsapp|outlook|teams|sendgrid|resend|twitter|linkedin"
)
SYNC_GLOBS = [
    ("Dropbox*", "Dropbox"), ("OneDrive*", "OneDrive"), ("Google Drive*", "Google Drive"),
    ("GoogleDrive*", "Google Drive"), ("Box", "Box"), ("Box Sync", "Box"),
    ("iCloud Drive*", "iCloud Drive"), ("iCloudDrive*", "iCloud Drive"), ("pCloud*", "pCloud"),
]
INTENTIONALLY_EMPTY = {
    ".gitkeep", ".keep", "__init__.py", "py.typed", ".nojekyll", ".placeholder", ".gitignore",
}
SF_DATALESS = 0x40000000  # macOS: file content lives in the cloud, not on disk


def hidden_codepoint(cp: int, previous: int) -> bool:
    if cp == 0x200D:
        # Zero-width joiner is legitimate inside an emoji sequence.
        return not (previous >= 0x1F000 or 0x2600 <= previous <= 0x27BF or previous == 0xFE0F)
    return (
        0x200B <= cp <= 0x200F
        or 0x202A <= cp <= 0x202E
        or 0x2060 <= cp <= 0x2064
        or 0x2066 <= cp <= 0x2069
        or cp in (0xFEFF, 0x00AD, 0x180E, 0x061C)
        or 0xE0000 <= cp <= 0xE007F
        or 0xE0100 <= cp <= 0xE01EF
    )


def parse_toml_tables(text: str) -> dict[str, dict[str, object]]:
    """Minimal TOML reader: table headers and single-line or bracketed values.

    Python 3.9 has no tomllib, and one code path on every interpreter beats
    two. Enough for Codex-style config; not a general TOML parser.
    """
    tables: dict[str, dict[str, object]] = {"": {}}
    current = ""
    pending_key, pending = None, ""
    for raw in text.splitlines():
        line = raw.strip()
        if pending_key is not None:
            pending += " " + line
            if pending.count("[") <= pending.count("]"):
                tables[current][pending_key] = _toml_value(pending)
                pending_key, pending = None, ""
            continue
        if not line or line.startswith("#"):
            continue
        header = re.match(r"^\[\[?\s*(.+?)\s*\]?\]\s*(?:#.*)?$", line)
        if header and "=" not in line.split("]")[0]:
            current = header.group(1)
            tables.setdefault(current, {})
            continue
        pair = re.match(r"^([A-Za-z0-9_.\-\"']+)\s*=\s*(.*)$", line)
        if not pair:
            continue
        key, value = pair.group(1).strip("\"'"), pair.group(2)
        if value.startswith("[") and value.count("[") > value.count("]"):
            pending_key, pending = key, value
            continue
        tables[current][key] = _toml_value(value)
    return tables


def _toml_value(value: str) -> object:
    value = value.strip()
    try:
        return json.loads(value)
    except ValueError:
        pass
    if value.startswith("{"):
        return {name: "" for name in re.findall(r"([A-Za-z0-9_\-]+)\s*=", value)}
    if value.startswith("["):
        return [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", value)]
    return value.split("#")[0].strip().strip("\"'")


def unpinned_reasons(command: str, args: list[str]) -> list[str]:
    """Why a server launch line would fetch code that can change under it."""
    reasons = []
    base = os.path.basename(command or "")
    tokens = [command or ""] + args
    if any(t.endswith("@latest") or t.endswith(":latest") for t in tokens):
        reasons.append("latest tag")
    plain = [a for a in args if not a.startswith("-")]
    if base in ("npx", "bunx", "pnpx") or (base in ("pnpm", "yarn", "bun") and plain[:1] in (["dlx"], ["x"])):
        package = next((a for a in plain if a not in ("dlx", "x")), "")
        if package and not re.search(r".@\d", package):
            reasons.append("package has no version")
        if "-y" in args or "--yes" in args:
            reasons.append("-y installs without asking")
    elif base in ("uvx", "pipx") or (base == "uv" and plain[:2] == ["tool", "run"]):
        package = next((a for a in plain if a not in ("run", "tool")), "")
        if package and not re.search(r"(?:==|@)\d", package) and "--from" not in args:
            reasons.append("package has no version")
    elif base in ("docker", "podman"):
        image = next((a for a in reversed(plain) if "/" in a or ":" in a), "")
        if image and ":" not in image.split("/")[-1] and "@sha256" not in image:
            reasons.append("image has no tag")
    return reasons


# --------------------------------------------------------------------------
# Collector
# --------------------------------------------------------------------------


class Collector:
    def __init__(self, repo: Path, home: Path, environ: dict, github: bool = False,
                 only: set | None = None, system_paths: bool = True):
        self.home = Path(home).resolve()
        self.environ = dict(environ)
        self.github = github
        self.only = only or set()
        self.system_paths = system_paths
        self.items: list[dict] = []
        self.notes: list[str] = []
        self._counts: dict[tuple, int] = {}
        self._unicode_seen: set = set()
        self.repo = Path(repo).resolve()
        top = self._git("rev-parse", "--show-toplevel")
        self.is_git = top is not None
        if top and Path(top).resolve() != self.repo:
            self.notes.append("auditing the enclosing git repository root, not the subdirectory given")
            self.repo = Path(top).resolve()
        if not self.is_git:
            self.notes.append("not a git repository: tracked/ignored status and GitHub checks are unavailable")
        # Nothing is exempt, this skill's own directory included: an exempt
        # directory is where a planted file would hide.
        self.coverage: dict[int, list[str]] = {}
        self.steps_run: list[str] = []
        self.github_requests = 0
        self._status_cache: dict[str, str] = {}
        self._file_counts: dict[tuple, int] = {}
        self._files: list[str] | None = None
        self._tracked: set | None = None

    # -- plumbing ----------------------------------------------------------

    def _run(self, cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
        if cmd[0] == "git":
            # A fixed environment: inherited GIT_* settings can redirect git to
            # another repository or make it write trace files.
            env = {k: v for k, v in self.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")}
            env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_TRACE="0",
                       GIT_TRACE2="0", GIT_TRACE2_EVENT="0", GIT_TRACE2_PERF="0")
        else:
            env = {k: v for k, v in self.environ.items() if not k.startswith("GIT_TRACE") and k != "GH_DEBUG"}
            env.update(GH_HOST="github.com", GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", NO_COLOR="1")
        env["HOME"] = str(self.home)
        try:
            done = subprocess.run(cmd, cwd=str(cwd or self.repo), env=env, capture_output=True,
                                  text=True, timeout=SUBPROCESS_TIMEOUT, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            return 127, "", "not installed"
        except subprocess.TimeoutExpired:
            return 124, "", "timed out"
        except OSError:
            return 126, "", "could not run"
        return done.returncode, done.stdout, done.stderr

    @staticmethod
    def _git_cmd(*args: str) -> list[str]:
        # A repository's own config can name helper programs (a filesystem
        # monitor hook) and a partial clone can fetch on demand. None of the
        # read-only commands used here needs either, so both are switched off.
        return ["git", "--no-optional-locks", "--no-pager", "-c", "core.fsmonitor=false",
                "-c", "core.untrackedCache=false", *args]

    def _git(self, *args: str) -> str | None:
        code, out, _ = self._run(self._git_cmd(*args))
        return out.rstrip("\n") if code == 0 else None

    def add(self, check: int, kind: str, loc: str, note: str = "") -> None:
        if self.only and check not in self.only:
            return
        # One lead, one line: a path or name with a newline in it must not forge a second row.
        home = str(self.home)
        loc = " ".join(str(loc).replace(home, "~").split())
        note = " ".join(redact(str(note).replace(home, "~")).split())
        anchored = re.match(r"^(.+?):\d+(?::\d+)?$", loc)
        if anchored:
            per_file = (check, kind, anchored.group(1))
            self._file_counts[per_file] = self._file_counts.get(per_file, 0) + 1
            if self._file_counts[per_file] > MAX_PER_FILE:
                return
        key = (check, kind)
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] <= MAX_PER_KIND:
            # redact() is a second layer only: notes are built from names and
            # fixed text, never from file content.
            self.items.append({"check": check, "kind": kind, "loc": loc, "note": note})

    def cover(self, check: int, text: str) -> None:
        """Record what was examined, so a clean check reads differently from one not run."""
        if self.only and check not in self.only:
            return
        self.coverage.setdefault(check, []).append(" ".join(redact(str(text).replace(str(self.home), "~")).split()))

    def show(self, path: Path | str) -> str:
        """Display form of a path: repo-relative, else ~-relative, else as given."""
        path = Path(path)
        for base, prefix in ((self.repo, ""), (self.home, "~/")):
            try:
                inner = path.relative_to(base).as_posix()
            except ValueError:
                continue
            return (prefix + inner) if inner != "." else (prefix or ".")
        return path.as_posix()

    def _skipped(self, name: str) -> bool:
        return any(part in SKIP_DIRS for part in name.split("/")[:-1])

    def walk(self):
        """Every file under the repo, ignored ones included, minus SKIP_DIRS."""
        for root, dirs, names in os.walk(self.repo):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                yield (Path(root) / name).relative_to(self.repo).as_posix()

    def files(self) -> list[str]:
        """Tracked plus untracked-but-not-ignored files; documents last."""
        if self._files is None:
            listing = self._git("ls-files", "-co", "--exclude-standard", "-z") if self.is_git else None
            names = [n for n in listing.split("\0") if n] if listing is not None else list(self.walk())
            names = [n for n in names if not self._skipped(n)]
            names.sort(key=lambda n: (n.lower().endswith(DOC_SUFFIXES), n))
            self._files = names
        return self._files

    def tracked(self) -> set:
        if self._tracked is None:
            listing = self._git("ls-files", "-z") if self.is_git else None
            self._tracked = {n for n in (listing or "").split("\0") if n}
        return self._tracked

    def text(self, path: Path | str, limit: int = MAX_FILE_BYTES) -> str | None:
        """Decoded content of a regular file, or None.

        Anything reached through the repository must resolve to a file inside
        it: a link in a checkout (at any level of the path) can point at any
        file on the machine. The read is bounded, never blocks on a FIFO or
        device, and skips cloud placeholders rather than downloading them.
        """
        path = Path(path)
        if not path.is_absolute():
            path = self.repo / path
        try:
            path.relative_to(self.repo)
            through_repo = True
        except ValueError:
            through_repo = False
        try:
            resolved = path.resolve()
            if through_repo:
                resolved.relative_to(self.repo)
            info = os.stat(resolved)
        except (OSError, ValueError):
            return None
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_flags", 0) & SF_DATALESS:
            return None
        try:
            descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return None
                data = handle.read(limit + 1)
        except OSError:
            return None
        if len(data) > limit or b"\0" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace")

    def load_json(self, path: Path) -> object | None:
        text = self.text(path, MAX_CONFIG_BYTES)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            # JSONC (VS Code, Zed): drop whole-line comments and trailing commas.
            stripped = re.sub(r"^\s*//.*$", "", text, flags=re.M)
            stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
            try:
                return json.loads(stripped)
            except ValueError:
                return None

    def status(self, name: str) -> str:
        if not self.is_git:
            return "no git"
        if name in self.tracked():
            return "tracked in git"
        if name not in self._status_cache:
            code, _, _ = self._run(self._git_cmd("check-ignore", "-q", "--", name))
            self._status_cache[name] = {0: "untracked, ignored", 1: "untracked, NOT ignored"}.get(
                code, "untracked, ignore status unknown")
        return self._status_cache[name]

    # -- check 1 and 2: env files, tracked text ----------------------------

    @staticmethod
    def env_role(name: str) -> str:
        lowered = name.lower()
        for word, role in (("example", "example"), ("sample", "example"), ("template", "example"),
                           ("test", "test"), (".ci", "test"), ("preview", "preview"),
                           ("stag", "staging"), ("prod", "production"), ("dev", "dev"), ("local", "dev")):
            if word in lowered:
                return role
        return "default"

    def env_files(self) -> None:
        found = 0
        for name in sorted(self.walk()):
            base = name.rsplit("/", 1)[-1]
            if not ENV_FILE.match(base):
                continue
            text = self.text(name)
            if text is None:
                continue
            found += 1
            role, status = self.env_role(base), self.status(name)
            assignments = env_assignments(text)
            literal_secrets = []
            for lineno, key, value in assignments:
                if value == MULTILINE:
                    if SECRET_NAME.search(key):
                        literal_secrets.append(f"{key}@{lineno}")
                    continue
                for hint in value_hints(value):
                    if hint.startswith("->"):
                        self.add(1, "db-target", f"{name}:{lineno}", f"{key} {hint} (file role: {role}; {status})")
                    elif "live payment" in hint:
                        self.add(2, "live-payment-key", f"{name}:{lineno}", f"{key}: {hint} ({status})")
                host = DB_HOST_KEY.match(f"{key}={value}")
                if host and not DB_URL.search(value):
                    self.add(1, "db-target", f"{name}:{lineno}",
                             f"{key} -> host {safe_name(host.group(2))} [{classify_host(host.group(2))}] "
                             f"(file role: {role}; {status})")
                if SECRET_NAME.search(key) and not PLACEHOLDER.match(value) and not REFERENCE.match(value):
                    literal_secrets.append(f"{key}@{lineno}")
            note = f"role: {role}; {status}; {len(assignments)} keys"
            if literal_secrets:
                note += f"; secret-named keys holding literal values: {', '.join(literal_secrets[:12])}"
                if len(literal_secrets) > 12:
                    note += f" (+{len(literal_secrets) - 12} more)"
            self.add(2, "env-file", name, note)
        for check in (1, 2):
            self.cover(check, f"{found} env files (ignored ones included)")

    def scan_tracked_text(self) -> None:
        scanned = 0
        db_config = [n for n in self.files() if DB_CONFIG_FILE.search(n)]
        self.cover(1, f"database/ORM/compose config files: {len(db_config)}" if db_config else
                   "database/ORM/compose config files: none, so leads here are string matches in code, tests or docs")
        withheld = 0
        for name in self.files():
            if STATE_OR_VARS.search(name):
                withheld += 1  # state and variable files hold values; they are never pattern-scanned
                continue
            text = self.text(name)
            if text is None:
                continue
            scanned += 1
            is_doc = name.lower().endswith(DOC_SUFFIXES)
            tag = "(doc)" if is_doc else ""
            is_env = ENV_FILE.match(name.rsplit("/", 1)[-1]) is not None
            for lineno, line in enumerate(text.splitlines(), 1):
                if len(line) > 2000:
                    continue
                # Leads carry the location and what matched. The line itself is
                # never printed: read it in the file.
                loc = f"{name}:{lineno}"
                label = shape_label(line)
                if label and not is_env:
                    self.add(2, "token-shaped-string", loc, f"{label} {tag}; {self.status(name)}".replace("  ", " "))
                if not is_env:
                    for match in DB_URL.finditer(line):
                        shown, klass = sanitize_db_url(match.group(1))
                        self.add(1, "db-target", loc, f"{shown} [{klass}] {tag}".rstrip())
                    host = DB_HOST_KEY.search(line)
                    if host and not is_doc and not DB_URL.search(line):
                        klass = classify_host(host.group(2))
                        if klass in ("non-local", "private-network"):
                            self.add(1, "db-target", loc, f"{host.group(1)} -> host {safe_name(host.group(2))} [{klass}]")
                rm = RM_RECURSIVE.search(line)
                if rm:
                    target = rm.group(1)
                    traits = []
                    if "$" in target:
                        traits.append("variable target, guarded with :?" if ":?" in target
                                      else "VARIABLE TARGET, no :? guard")
                    if "*" in target:
                        traits.append("glob")
                    if "~" in target or "$HOME" in target:
                        traits.append("touches HOME")
                    if "`" in target or "$(" in target:
                        traits.append("command substitution")
                    self.add(3, "recursive-delete", loc, f"[{'; '.join(traits) or 'literal target'}] {tag}".rstrip())
                for check, kind, regex, scan_docs in LINE_PATTERNS:
                    if is_doc and not scan_docs:
                        continue
                    if regex.search(line):
                        self.add(check, kind, loc, tag)
        for check in (1, 2, 3, 4, 5, 8, 11):
            self.cover(check, f"{scanned} text files pattern-scanned"
                       + (f" ({withheld} Terraform state or variable files left unscanned)" if withheld else ""))

    # -- check 2: environment and credential files -------------------------

    def environment(self) -> None:
        unusual = 0
        for name in sorted(self.environ):
            value = self.environ[name]
            if not ENV_NAME.match(name):
                unusual += 1
                continue
            hints = value_hints(value)
            if name in SELECTORS:
                # The only values this collector ever prints: a fixed list of
                # context selectors, and only when the value is a plain name or path.
                shown = value.replace(str(self.home), "~")
                if not SELECTOR_VALUE.match(shown) or TOKEN_SHAPES.search(shown) or looks_random(shown):
                    self.add(2, "context-selector", f"env:{name}", "set; value withheld (not a plain name or path)")
                else:
                    prod = " [PROD-LIKE NAME]" if PROD_LIKE.search(shown) else ""
                    self.add(2, "context-selector", f"env:{name}", f"= {shown}{prod}")
                continue
            if not (CRED_ENV.search(name) or [h for h in hints if h != "empty"]):
                continue
            prod = "; PROD-LIKE NAME" if PROD_LIKE.search(name) else ""
            self.add(2, "env-var", f"env:{name}", ("; ".join(hints) or "set") + prod)
            for hint in hints:
                if hint.startswith("->"):
                    self.add(1, "db-target", f"env:{name}", f"{hint} (exported in this shell)")
        if unusual:
            self.add(2, "env-var", "env", f"{unusual} variables with unusual names not listed")
        self.cover(2, f"{len(self.environ)} environment variables examined by name and shape")
        if "SSH_AUTH_SOCK" in self.environ:
            self.add(2, "env-var", "env:SSH_AUTH_SOCK",
                     "an SSH agent is reachable: loaded keys work without reading a key file")

    def _mode(self, path: Path) -> str:
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            return "unreadable"
        return f"mode {mode:o}" + ("; GROUP/WORLD ACCESS" if mode & 0o077 and path.is_file() else "")

    def credential_files(self) -> None:
        home = self.home
        for rel, label in CRED_PATHS:
            path = home / rel
            if path.exists():
                self.add(2, "credential-file", self.show(path), f"{label}; {self._mode(path)}")
        self._aws(home / ".aws")
        self._kube()
        self._gcloud()
        self._simple_cred_files()
        ssh = home / ".ssh"
        if ssh.is_dir():
            keys = []
            for entry in sorted(ssh.iterdir()):
                try:
                    if entry.is_file():
                        with open(entry, "rb") as handle:
                            if b"PRIVATE KEY" in handle.read(64):
                                keys.append(entry.name)
                except OSError:
                    continue
            if keys:
                self.add(2, "credential-file", "~/.ssh", f"{len(keys)} private key files: {safe_names(keys, 15)}")
        self.cover(2, f"{len(CRED_PATHS) + 14} known credential locations probed under ~ "
                      "(AWS, kube, gcloud, netrc, pgpass, npm, docker, gh, git, ssh and other CLIs)")

    def _aws(self, directory: Path) -> None:
        profile = self.environ.get("AWS_PROFILE") or self.environ.get("AWS_DEFAULT_PROFILE") or "default"
        seen = directory.is_dir()
        for variable, filename in (("AWS_SHARED_CREDENTIALS_FILE", "credentials"), ("AWS_CONFIG_FILE", "config")):
            override = self.environ.get(variable)
            path = Path(override) if override else directory / filename
            text = self.text(path)
            if text is None:
                if override:
                    self.add(2, "credential-file", f"env:{variable}",
                             "points at a file that is missing or unreadable: NOT INSPECTED")
                continue
            seen = True
            parser = configparser.RawConfigParser(strict=False)
            try:
                parser.read_string(text)
            except configparser.Error:
                self.add(2, "credential-file", self.show(path), f"present, unparseable; {self._mode(path)}")
                continue
            described = []
            for section in parser.sections():
                keys = set(parser.options(section))
                name = section.replace("profile ", "")
                traits = []
                if "aws_secret_access_key" in keys:
                    traits.append("temporary keys" if "aws_session_token" in keys else "STATIC LONG-LIVED KEY")
                for key, word in (("sso_start_url", "sso"), ("sso_session", "sso"), ("role_arn", "assumes a role"),
                                  ("credential_process", "credential_process")):
                    if key in keys and word not in traits:
                        traits.append(word)
                prod = " [PROD-LIKE NAME]" if PROD_LIKE.search(name) else ""
                described.append(f"{safe_name(name)}{prod} ({', '.join(traits) or 'no credentials here'})")
            self.add(2, "credential-file", self.show(path),
                     f"{self._mode(path)}; profiles: {'; '.join(described[:20]) or 'none'}")
        if seen:
            prod = " [PROD-LIKE NAME]" if PROD_LIKE.search(profile) else ""
            self.add(2, "default-context", "~/.aws", f"aws commands with no --profile use: {safe_name(profile)}{prod}")

    def _kube(self) -> None:
        raw = self.environ.get("KUBECONFIG") or str(self.home / ".kube" / "config")
        for entry in raw.split(os.pathsep):
            path = Path(entry)
            if not path.is_absolute():
                self.add(2, "credential-file", "env:KUBECONFIG", "names a relative path, which resolves against "
                         "whatever directory a command runs in: NOT INSPECTED")
                continue
            text = self.text(path, MAX_CONFIG_BYTES)
            if text is None:
                continue
            current = re.search(r"^current-context:\s*[\"']?([^\"'\n]*)", text, re.M)
            names, section = [], ""
            for line in text.splitlines():
                top = re.match(r"^([A-Za-z-]+):", line)
                if top:
                    section = top.group(1)
                elif section == "contexts":
                    found = re.match(r"^(?:-\s+|\s+)name:\s*[\"']?([^\"'\n]+)", line)
                    if found:
                        names.append(found.group(1).strip())
            embedded = re.search(r"^\s+(?:token|client-key-data|password):\s*\S", text, re.M)
            context = (current.group(1).strip() if current else "") or "(none)"
            prod = " [PROD-LIKE NAME]" if PROD_LIKE.search(context) else ""
            self.add(2, "default-context", self.show(path), f"kubectl current-context: {safe_name(context)}{prod}")
            self.add(2, "credential-file", self.show(path),
                     f"{self._mode(path)}; contexts: {safe_names(names, 15) or 'none'}"
                     + ("; STATIC CREDENTIAL embedded in file" if embedded else ""))

    def _gcloud(self) -> None:
        directory = Path(self.environ.get("CLOUDSDK_CONFIG") or self.home / ".config" / "gcloud")
        if not directory.is_absolute() or not directory.is_dir():
            return
        active = (self.text(directory / "active_config") or "default").strip() or "default"
        active = self.environ.get("CLOUDSDK_ACTIVE_CONFIG_NAME") or active
        note = f"gcloud active configuration: {safe_name(active)}"
        config = self.text(directory / "configurations" / f"config_{active}") if NAME_SAFE.match(active) else None
        if config:
            parser = configparser.RawConfigParser(strict=False)
            try:
                parser.read_string(config)
                project = parser.get("core", "project", fallback="")
                account = parser.get("core", "account", fallback="")
            except configparser.Error:
                project = account = ""
            if project:
                note += f"; project: {safe_name(project)}"
            if account:
                kind = "service account" if account.endswith(".gserviceaccount.com") else "user account"
                note += f"; signed in as a {kind}"
            if PROD_LIKE.search(f"{active} {project}"):
                note += " [PROD-LIKE NAME]"
        self.add(2, "default-context", self.show(directory), note)
        adc = self.load_json(directory / "application_default_credentials.json")
        if isinstance(adc, dict):
            kind = adc.get("type") if adc.get("type") in ("authorized_user", "service_account",
                                                           "external_account", "impersonated_service_account") else "unknown"
            self.add(2, "credential-file", self.show(directory / "application_default_credentials.json"),
                     f"application default credentials, type: {kind}")
        for extra in ("credentials.db", "access_tokens.db", "legacy_credentials"):
            if (directory / extra).exists():
                self.add(2, "credential-file", self.show(directory / extra), "gcloud stored credentials")

    def _simple_cred_files(self) -> None:
        home = self.home
        netrc = self.text(home / ".netrc")
        if netrc is not None:
            machines = netrc_machines(netrc)
            self.add(2, "credential-file", "~/.netrc", f"{self._mode(home / '.netrc')}; " + (
                "could not be tokenised: machine names NOT READ" if machines is None
                else f"logins for: {safe_names(machines) or '(default only)'}"))
        pgpass = self.text(home / ".pgpass")
        if pgpass is not None:
            targets = []
            for line in pgpass.splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    fields = re.split(r"(?<!\\):", line)
                    if len(fields) >= 3:
                        host = fields[0] if HOST_SAFE.match(fields[0]) or fields[0] == "*" else "<withheld>"
                        port = fields[1] if re.fullmatch(r"\d{1,5}|\*", fields[1]) else "?"
                        targets.append(f"{host}:{port}/{safe_name(fields[2])} [{classify_host(fields[0])}]")
            self.add(2, "credential-file", "~/.pgpass",
                     f"{self._mode(home / '.pgpass')}; passwords for: {', '.join(targets[:15]) or 'none'}")
        npmrc = self.text(home / ".npmrc")
        if npmrc is not None:
            registries = []
            for line in npmrc.splitlines():
                found = re.match(r"^\s*([^#;=\s]*?):?(_authToken|_auth|_password)\s*=\s*(.*)$", line)
                if found:
                    how = "from env var" if "${" in found.group(3) else "LITERAL in file"
                    registries.append(f"{safe_name(found.group(1) or '(default registry)')} {found.group(2)} ({how})")
            if registries:
                self.add(2, "credential-file", "~/.npmrc", f"{self._mode(home / '.npmrc')}; {'; '.join(registries[:10])}")
        docker = self.load_json(home / ".docker" / "config.json")
        if isinstance(docker, dict):
            auths = docker.get("auths") if isinstance(docker.get("auths"), dict) else {}
            inline = [h for h, v in auths.items() if isinstance(v, dict) and v.get("auth")]
            note = f"registries: {safe_names(list(auths), 10) or 'none'}"
            note += f"; credsStore: {safe_name(docker.get('credsStore') or 'none')}"
            if inline:
                note += f"; {len(inline)} registry logins stored INLINE (base64, not encrypted)"
            self.add(2, "credential-file", "~/.docker/config.json", note)
        for rel in (".config/gh/hosts.yml", "Library/Application Support/gh/hosts.yml"):
            hosts = self.text(home / rel)
            if hosts is not None:
                names = re.findall(r"^([^\s#][^:\n]*):\s*$", hosts, re.M)
                stored = ("token stored in PLAINTEXT in this file" if re.search(r"^\s+oauth_token:\s*\S", hosts, re.M)
                          else "no token in file (system keychain or none)")
                self.add(2, "credential-file", self.show(home / rel), f"gh hosts: {safe_names(names) or 'none'}; {stored}")
        gitcreds = self.text(home / ".git-credentials")
        if gitcreds is not None:
            hosts = set()
            for line in gitcreds.split():
                try:
                    hosts.add(urlsplit(line).hostname or "?")
                except ValueError:
                    hosts.add("?")
            self.add(2, "credential-file", "~/.git-credentials",
                     f"PLAINTEXT git passwords for: {safe_names(sorted(hosts))}")
        stripe = self.text(home / ".config" / "stripe" / "config.toml")
        if stripe is not None:
            live = "LIVE-MODE KEY PRESENT" if re.search(r"^\s*live_mode_api_key\s*=\s*\S", stripe, re.M) else "no live-mode key"
            self.add(2, "credential-file", "~/.config/stripe/config.toml", f"Stripe CLI; {live}")

    def tracked_sensitive_files(self) -> None:
        for name in sorted(self.tracked()):
            if self._skipped(name) or not SENSITIVE_TRACKED.search(name) or EXAMPLE_NAME.search(name):
                continue
            head = self.text(name) or ""
            extra = "; contains a private key header" if "PRIVATE KEY-----" in head else ""
            self.add(2, "tracked-sensitive-file", name, f"committed to git{extra}")
        self.cover(2, f"{len(self.tracked())} tracked file names checked for key and credential files")
        if self.is_git:
            verdicts = []
            for probe in IGNORE_PROBES:
                code, _, _ = self._run(self._git_cmd("check-ignore", "-q", "--", probe))
                verdicts.append(f"{probe}: " + {0: "ignored", 1: "NOT IGNORED"}.get(code, "unknown"))
            self.add(2, "gitignore-coverage", ".gitignore", "; ".join(verdicts))
        remotes = self._git("remote", "-v") or ""
        for line in remotes.splitlines():
            if re.search(r"://[^/\s@]+@", line) and not re.search(r"://git@", line):
                self.add(2, "credential-in-remote-url", ".git/config",
                         f"remote '{safe_name(line.split()[0])}' embeds credentials in its URL")

    # -- check 3 -----------------------------------------------------------

    def shell_scripts(self) -> None:
        risky, plain, checked = [], [], 0
        for name in self.files():
            text = self.text(name)
            if text is None:
                continue
            first = text.split("\n", 1)[0]
            shebang = re.match(r"^#!.*?\b((?:ba|z|k|da)?sh)\b", first)
            if not (shebang or name.endswith((".sh", ".bash", ".zsh", ".ksh"))):
                continue
            checked += 1
            missing = []
            if not re.search(r"^\s*set\s+(?:-[A-Za-z]*u[A-Za-z]*\b|-o\s+nounset)", text, re.M):
                missing.append("-u")
            if not re.search(r"^\s*set\s+(?:-[A-Za-z]*e[A-Za-z]*\b|-o\s+errexit)", text, re.M):
                missing.append("-e")
            posix_sh = bool(shebang and shebang.group(1) in ("sh", "dash"))
            if not posix_sh and "pipefail" not in text:
                missing.append("pipefail")
            if "-u" not in missing:
                continue
            deletes = bool(RM_RECURSIVE.search(text) or re.search(r"\bfind\b.*-delete|\bgit\s+clean\b", text))
            entry = (name, f"no 'set {' '.join(missing)}' line anywhere" + ("; CONTAINS A RECURSIVE DELETE" if deletes else ""))
            (risky if deletes else plain).append(entry)
        for name, note in risky + plain:
            self.add(3, "shell-without-nounset", f"{name}:1", note)
        self.cover(3, f"{checked} shell scripts checked for a 'set -u' line ({len(risky) + len(plain)} have none; "
                      "a line inside a branch still counts, so read the script before trusting it)")

    def symlinks(self) -> None:
        seen = set()
        for root, dirs, names in os.walk(self.repo):
            for entry in list(dirs) + names:
                path = Path(root) / entry
                if not path.is_symlink():
                    continue
                rel = path.relative_to(self.repo).as_posix()
                if rel in seen:
                    continue
                seen.add(rel)
                try:
                    target = os.readlink(path)
                    resolved = (path.parent / target).resolve()
                except OSError:
                    continue
                try:
                    resolved.relative_to(self.repo)
                    where = "inside repo"
                except ValueError:
                    where = "OUTSIDE REPO"
                kind = "directory" if resolved.is_dir() else ("file" if resolved.exists() else "dangling")
                shown = self.show(resolved) if os.path.isabs(target) else target
                self.add(3, "symlink", rel, f"-> {shown} [{where}; {kind}]")
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (Path(root) / d).is_symlink()]
        self.cover(3, f"{len(seen)} symlinks in the work tree")

    # -- check 4 -----------------------------------------------------------

    @staticmethod
    def _tf_code(text: str) -> str:
        """Terraform source with comments blanked, line numbers preserved."""
        text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        return "\n".join(re.sub(r"(?:#|//).*$", "", line) for line in text.split("\n"))

    def infrastructure(self) -> None:
        tf_files = [n for n in self.files() if n.endswith(".tf")]
        roots: dict[str, dict] = {}
        for name in tf_files:
            code = self._tf_code(self.text(name) or "")
            root = roots.setdefault(name.rpartition("/")[0] or ".", {"remote": False, "resources": 0, "first": name})
            backends = re.findall(r'^\s*backend\s+"(\w+)"', code, re.M)
            # `backend "local"` keeps state on disk; it is not a remote backend.
            root["remote"] = (root["remote"] or any(kind != "local" for kind in backends)
                              or bool(re.search(r"^\s*cloud\s*\{", code, re.M)))
            lines = code.splitlines()
            for index, line in enumerate(lines):
                found = TF_RESOURCE.match(line)
                if not found:
                    continue
                root["resources"] += 1
                if not TF_DATA_TYPES.search(found.group(1)):
                    continue
                # Only the resource's own arguments and its lifecycle block
                # count. The same words inside a tags map protect nothing.
                depth, own, lifecycle, in_lifecycle = 0, [], [], False
                for inner in lines[index:]:
                    before = depth
                    depth += inner.count("{") - inner.count("}")
                    if before == 1:
                        own.append(inner)
                        in_lifecycle = in_lifecycle or bool(re.match(r"^\s*lifecycle\s*\{", inner))
                    if in_lifecycle:
                        lifecycle.append(inner)
                        in_lifecycle = depth > 1
                    if depth <= 0:
                        break
                arguments, guard = "\n".join(own), "\n".join(lifecycle)
                traits = []
                if not (re.search(r"^\s*deletion_protection(?:_enabled)?\s*=\s*true\b", arguments, re.M)
                        or re.search(r"\bprevent_destroy\s*=\s*true\b", guard)):
                    traits.append("neither deletion_protection nor lifecycle.prevent_destroy is set to true")
                for flag in ("force_destroy", "skip_final_snapshot"):
                    if re.search(r"^\s*" + flag + r"\s*=\s*true\b", arguments, re.M):
                        traits.append(f"{flag} = true")
                if traits:
                    self.add(4, "unprotected-data-resource", f"{name}:{index + 1}",
                             f"{safe_name(found.group(1))}.{safe_name(found.group(2))}: {'; '.join(traits)}")
        for directory, root in sorted(roots.items()):
            # Each directory is its own Terraform root; a backend elsewhere says nothing about this one.
            if root["resources"] and not root["remote"]:
                self.add(4, "local-terraform-state", root["first"],
                         f"no remote backend or cloud block among the .tf files in {directory}/: state stays "
                         "on this disk unless a parent module configures it")
        states = 0
        iac = sorted({n.rsplit("/", 1)[-1] for n in self.files() if IAC_FILE.search(n) and not n.endswith(".tf")})
        self.cover(4, f"{len(tf_files)} .tf files in {len(roots)} directories; other infrastructure files: "
                      f"{safe_names(iac, 8) or 'none'}")
        for name in sorted(self.walk()):
            if re.search(r"\.tfstate(?:\.backup|\.\d+)?$", name):
                states += 1
                try:
                    size = (self.repo / name).stat().st_size
                except OSError:
                    size = 0
                self.add(4, "tfstate-file", name, f"{self.status(name)}; {size} bytes; content not scanned "
                         "(state holds resource ids and often plaintext secrets)")
        self.cover(4, f"{states} state files")

    # -- check 5 -----------------------------------------------------------

    def rule_files(self) -> list[Path]:
        found = []
        for name in self.files():
            base = name.rsplit("/", 1)[-1]
            if base in RULE_FILE_NAMES or any(marker in f"/{name}" for marker in RULE_DIR_MARKERS):
                found.append(self.repo / name)
        local = self.repo / "CLAUDE.local.md"
        if local.is_file() and local not in found:
            found.append(local)
        for rel in (".claude/CLAUDE.md", ".codex/AGENTS.md", ".agents/AGENTS.md", ".gemini/GEMINI.md"):
            if (self.home / rel).is_file():
                found.append(self.home / rel)
        for rel in (".claude/rules", ".cursor/rules"):
            directory = self.home / rel
            if directory.is_dir():
                found.extend(sorted(p for p in directory.rglob("*") if p.is_file())[:50])
        return found

    def prose_rules(self) -> None:
        self.cover(5, f"{len(self.rule_files())} agent instruction files (repo and user level)")
        for path in self.rule_files():
            text = self.text(path)
            if text is None:
                continue
            lines = [n for n, line in enumerate(text.splitlines(), 1) if RULE_LINE.search(line)]
            shown = ", ".join(str(n) for n in lines[:30]) + (" ..." if len(lines) > 30 else "")
            self.add(5, "rule-file", self.show(path),
                     f"{len(lines)} imperative lines" + (f" at lines {shown}" if lines else ""))

    def enforcement(self) -> None:
        for path in self._claude_settings_files():
            data = self.load_json(path)
            if not isinstance(data, dict):
                continue
            perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
            deny = [str(d) for d in perms.get("deny") or []]
            ask = perms.get("ask") or []
            hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
            note = f"deny rules: {len(deny)}"
            if deny:
                note += f" ({'; '.join(rule_head(d) for d in deny[:12])}{'; ...' if len(deny) > 12 else ''})"
            note += f"; ask rules: {len(ask)}; PreToolUse hooks: {len(hooks.get('PreToolUse') or [])}"
            sandbox = data.get("sandbox")
            if isinstance(sandbox, dict):
                note += f"; sandbox.enabled: {sandbox.get('enabled') is True}"
            self.add(5, "enforcement", self.show(path), note)
        hooks_path = self._git("config", "--get", "core.hooksPath")
        present = [d for d in (".githooks", ".husky") if (self.repo / d).is_dir()]
        present += [f for f in (".pre-commit-config.yaml", "lefthook.yml", "lefthook.yaml") if (self.repo / f).is_file()]
        active = []
        git_hooks = self.repo / ".git" / "hooks"
        if git_hooks.is_dir():
            active = sorted(p.name for p in git_hooks.iterdir() if p.is_file() and not p.name.endswith(".sample"))
        if self.is_git:
            note = f"core.hooksPath: {safe_name(hooks_path) if hooks_path else 'unset'}; "
            note += f"hook config in repo: {', '.join(present) or 'none'}"
            note += f"; active .git/hooks: {safe_names(active) or 'none'}"
            if present and not hooks_path and not active:
                note += " -- HOOK CONFIG PRESENT BUT NOTHING ACTIVE IN THIS CLONE"
            self.add(5, "enforcement", ".git", note)
        owners = [p for p in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS") if (self.repo / p).is_file()]
        self.add(5, "enforcement", "CODEOWNERS", ", ".join(owners) if owners else "absent")
        wanted = re.compile(r"(?i)test|deploy|migrat|reset|clean|destroy|seed|release|publish|drop")
        makefile = self.text("Makefile") or ""
        targets = sorted({t for t in re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", makefile, re.M) if wanted.search(t)})
        if targets:
            self.add(5, "named-commands", "Makefile", ", ".join(targets[:25]))
        package = self.load_json(self.repo / "package.json")
        if isinstance(package, dict) and isinstance(package.get("scripts"), dict):
            names = sorted(k for k in package["scripts"] if wanted.search(str(k)))
            if names:
                self.add(5, "named-commands", "package.json", safe_names(names, 25))

    def _claude_settings_files(self) -> list[Path]:
        paths = [self.repo / rel for rel in CLAUDE_SETTINGS_REPO] + [self.home / rel for rel in CLAUDE_SETTINGS_HOME]
        if self.system_paths:
            paths += [Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
                      Path("/etc/claude-code/managed-settings.json")]
        return [p for p in paths if p.is_file()]

    # -- check 6 -----------------------------------------------------------

    def github_checks(self) -> None:
        if not self.is_git:
            self.add(6, "not-checked", ".", "not a git repository")
            return
        url = self._git("remote", "get-url", "origin") or ""
        branch = self._git("symbolic-ref", "--short", "refs/remotes/origin/HEAD") or ""
        branch = branch.split("/", 1)[-1]
        branch = branch if re.fullmatch(r"[\w./-]{1,100}", branch) else "main"
        slug = github_slug(url)
        if not slug:
            self.add(6, "not-checked", ".git/config", "origin is absent or not a github.com remote: check the "
                     "host's branch rules by hand")
            return
        owner, repo = slug
        self.add(6, "remote", ".git/config", f"origin: github.com/{owner}/{repo}; default branch: {branch}")
        if not self.github:
            self.add(6, "not-checked", f"{owner}/{repo}",
                     "GitHub was not queried (run again with --github for read-only API calls)")
            return
        if not shutil.which("gh"):
            self.add(6, "not-checked", f"{owner}/{repo}", "gh CLI not installed")
            return
        # --no-refresh: looking must not rotate a stored token. --active: one account, the one gh would use.
        self.github_requests += 1
        code, out, err = self._run(["gh", "auth", "status", "--hostname", "github.com", "--active", "--no-refresh"])
        block = (out + err).splitlines()
        account = next((m.group(1) for line in block for m in [re.search(r"account\s+([\w-]{1,60})", line)] if m), "?")
        scopes = sorted(set(re.findall(r"'([\w:]{1,40})'", " ".join(line for line in block if "scopes" in line))))
        # gh prints the token masked ("gho_****"); its prefix names the type. The token itself is never fetched.
        prefix = next((m.group(1) for line in block
                       for m in [re.search(r"Token:\s*(github_pat_|gh[a-z]_)", line)] if m), "")
        kind = {"ghp_": "classic personal access token", "gho_": "OAuth token",
                "github_pat_": "fine-grained personal access token", "ghs_": "app installation token",
                "ghu_": "app user token"}.get(prefix, "type not shown")
        self.add(6, "gh-token", "gh auth", f"account: {account}; type: {kind}; scopes: {', '.join(scopes) or 'none listed'}")
        reach = [text for scope, text in (
            ("delete_repo", "CAN DELETE REPOSITORIES"),
            ("repo", "full read/write on every repo the account can reach, private included; can create public repos"),
            ("admin:org", "can administer organisations"),
            ("workflow", "can change CI workflows"),
            ("write:packages", "can publish packages"),
            ("admin:repo_hook", "can manage webhooks"),
        ) if scope in scopes]
        if reach:
            self.add(6, "gh-token-reach", "gh auth", "; ".join(reach))
        info = self._gh_json(f"repos/{owner}/{repo}")
        held: list = []
        if isinstance(info, dict):
            perms = info.get("permissions") or {}
            held = [k for k in ("admin", "maintain", "push") if perms.get(k) is True]
            reported = str(info.get("default_branch") or "")
            branch = reported if re.fullmatch(r"[\w./-]{1,100}", reported) else branch
            visibility = info.get("visibility") if info.get("visibility") in ("public", "private", "internal") else "unknown"
            self.add(6, "repo", f"{owner}/{repo}",
                     f"visibility: {visibility}; default branch: {branch}; "
                     f"this token has: {', '.join(held) or 'read only'}")
        else:
            self.add(6, "not-checked", f"{owner}/{repo}", f"repository metadata unavailable ({info})")
        protection = self._gh_json(f"repos/{owner}/{repo}/branches/{branch}/protection")
        if isinstance(protection, dict):
            reviews = protection.get("required_pull_request_reviews") or {}
            checks = (protection.get("required_status_checks") or {}).get("contexts") or []
            approvals = reviews.get("required_approving_review_count", 0)

            def flag(key: str) -> str:
                value = (protection.get(key) or {}).get("enabled")
                return str(value) if isinstance(value, bool) else "unknown"

            self.cover(6, f"required status checks: {safe_names(checks, 10) or 'none'}")
            self.add(6, "branch-protection", f"{owner}/{repo}@{branch}",
                     f"required approvals: {approvals if isinstance(approvals, int) else 'unknown'}; "
                     f"force pushes allowed: {flag('allow_force_pushes')}; "
                     f"deletion allowed: {flag('allow_deletions')}; "
                     f"enforced for admins: {flag('enforce_admins')}; "
                     f"status checks required: {bool(checks)}")
        else:
            self.add(6, "branch-protection", f"{owner}/{repo}@{branch}",
                     f"classic protection not readable ({protection}): either none is set or this token "
                     "cannot see it")
        rules = self._gh_json(f"repos/{owner}/{repo}/rules/branches/{branch}")
        if isinstance(rules, list):
            types = sorted({str(r.get("type")) for r in rules if isinstance(r, dict)})
            self.add(6, "branch-rulesets", f"{owner}/{repo}@{branch}",
                     f"ruleset rule types on this branch: {safe_names(types) or 'none'}")
        else:
            self.add(6, "branch-rulesets", f"{owner}/{repo}@{branch}", f"rulesets not readable ({rules})")
        self.add(6, "default-branch-verdict", f"{owner}/{repo}@{branch}", branch_verdict(protection, rules, held))
        org = self._gh_json(f"orgs/{owner}")
        if isinstance(org, dict):
            def setting(key: str) -> str:
                return str(org.get(key)) if isinstance(org.get(key), bool) else "unknown"

            self.add(6, "org", f"org:{owner}",
                     f"members can create public repos: {setting('members_can_create_public_repositories')}; "
                     f"members can create repos: {setting('members_can_create_repositories')}; "
                     f"2FA required: {setting('two_factor_requirement_enabled')}")

    def _gh_json(self, endpoint: str) -> object:
        # The host is pinned: without it gh would use GH_HOST or its default, which may be another server.
        self.github_requests += 1
        code, out, err = self._run(["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint])
        if code != 0:
            status = re.search(r"HTTP (\d{3})", err + out)
            return f"HTTP {status.group(1)}" if status else "request failed"
        try:
            return json.loads(out)
        except ValueError:
            return "unparseable response"

    # -- check 7 -----------------------------------------------------------

    def cloud_sync(self) -> None:
        home = self.home
        roots = [(home / "Library" / "Mobile Documents", "iCloud Drive")]
        storage = home / "Library" / "CloudStorage"
        if storage.is_dir():
            roots += [(d, d.name.split("-")[0]) for d in storage.iterdir() if d.is_dir()]
        for pattern, label in SYNC_GLOBS:
            roots += [(d, label) for d in home.glob(pattern) if d.is_dir()]
        for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
            if self.environ.get(var):
                roots.append((Path(self.environ[var]), "OneDrive"))
        inside = None
        for root, label in roots:
            for candidate in (root, root.resolve()):
                try:
                    self.repo.relative_to(candidate)
                    inside = (candidate, label)
                except ValueError:
                    continue
        if inside:
            self.add(7, "synced-folder", ".", f"REPO IS INSIDE A {safe_name(inside[1]).upper()} FOLDER ({self.show(inside[0])})")
        else:
            note = "repo is not under a known sync root"
            for name in ("Desktop", "Documents"):
                try:
                    self.repo.relative_to(home / name)
                except ValueError:
                    continue
                mirrored = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / name
                note = (f"repo is under ~/{name} and iCloud Desktop & Documents APPEARS ENABLED"
                        if os.path.lexists(mirrored)
                        else f"repo is under ~/{name}; iCloud Desktop & Documents not detected (heuristic)")
            self.add(7, "synced-folder", ".", note)
        empty, placeholders, examined, meant_empty, special = [], [], 0, 0, 0
        for rel in self.walk():
            base = rel.rsplit("/", 1)[-1]
            try:
                info = os.lstat(self.repo / rel)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                # Links, FIFOs, sockets and devices have no size to speak of.
                special += not stat.S_ISLNK(info.st_mode)
                continue
            examined += 1
            if re.match(r"^\..+\.icloud$", base) or getattr(info, "st_flags", 0) & SF_DATALESS:
                placeholders.append(rel)
            elif re.search(r"(?i)conflicted copy|\(conflict\)", base):
                placeholders.append(rel)
            elif info.st_size == 0 and base in INTENTIONALLY_EMPTY:
                meant_empty += 1
            elif info.st_size == 0:
                empty.append(rel)
        for rel in placeholders:
            self.add(7, "cloud-placeholder", rel, "content is not on this disk (cloud-only placeholder) or is a conflict copy")
        for rel in empty:
            self.add(7, "zero-byte-file", rel, self.status(rel) if rel in self.tracked() else "0 bytes")
        self.cover(7, f"{examined} regular files examined; {len(placeholders)} placeholders; {len(empty)} unexpected "
                      f"zero-byte files; {meant_empty} empty-by-convention files (.gitkeep, __init__.py) not listed"
                      + (f"; {special} special files (FIFO, socket, device) skipped" if special else ""))

    # -- check 8 -----------------------------------------------------------

    def _servers(self, data: object) -> list[tuple[str, str, dict]]:
        found = []
        if not isinstance(data, dict):
            return found
        for key in ("mcpServers", "servers", "context_servers", "mcp"):
            block = data.get(key)
            if isinstance(block, dict) and isinstance(block.get("servers"), dict):
                block = block["servers"]
            if isinstance(block, dict):
                found += [("", name, spec) for name, spec in block.items() if isinstance(spec, dict)]
        projects = data.get("projects")
        if isinstance(projects, dict):
            for project, pdata in projects.items():
                servers = pdata.get("mcpServers") if isinstance(pdata, dict) else None
                if isinstance(servers, dict) and servers:
                    try:
                        applies = self.repo == Path(project).resolve() or Path(project).resolve() in self.repo.parents
                    except OSError:
                        applies = False
                    if applies:
                        found += [("this project", name, spec) for name, spec in servers.items() if isinstance(spec, dict)]
        return found

    def _describe_server(self, loc: str, scope: str, name: str, spec: dict) -> None:
        command, args = spec.get("command"), spec.get("args") or []
        if isinstance(command, list):
            command, args = (command[0] if command else ""), list(command[1:]) + list(args)
        if isinstance(command, str) and " " in command and not args:
            try:
                command, *args = shlex.split(command)
            except ValueError:
                pass
        args = [str(a) for a in args] if isinstance(args, list) else []
        traits = []
        if command:
            traits.append(launch_summary(str(command), args))
            reasons = unpinned_reasons(str(command), args)
            if reasons:
                traits.append("UNPINNED (" + ", ".join(reasons) + ")")
        url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl")
        host = ""
        if isinstance(url, str):
            try:
                parts = urlsplit(url)
                host = parts.hostname or ""
                scheme = parts.scheme if parts.scheme in ("http", "https", "ws", "wss") else "?"
            except ValueError:
                host, scheme = "", "?"
            host = host if HOST_SAFE.match(host) and not looks_random(host) else "<withheld>"
            traits.append(f"remote: {scheme}://{host}")
        literal = []
        for block_name in ("env", "headers"):
            block = spec.get(block_name)
            if isinstance(block, dict) and block:
                traits.append(f"{block_name}: {safe_names(sorted(map(str, block)))}")
                literal += [str(k) for k, v in block.items()
                            if isinstance(v, str) and v and "${" not in v and not v.startswith("$")
                            and (SECRET_NAME.search(str(k)) or shape_label(v) or looks_random(v))]
        if literal:
            traits.append(f"LITERAL SECRET stored in config for: {safe_names(sorted(literal))}")
        label = safe_name(name) + (f" ({scope})" if scope else "")
        self.add(8, "mcp-server", loc, f"{label}: {'; '.join(traits) or 'no launch details'}")
        if SENDS_HINT.search(f"{name} {os.path.basename(str(command or ''))} {host}"):
            self.add(11, "mcp-server-can-send", loc, f"{safe_name(name)}: name suggests it can send money or "
                     "messages; look for a cap, an allowlist and a confirmation step")

    def agent_config(self) -> None:
        configs = [self.repo / rel for rel in MCP_CONFIGS_REPO] + [self.home / rel for rel in MCP_CONFIGS_HOME]
        self._unicode_files = 0
        seen = set()
        for path in configs:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            data = self.load_json(path)
            loc = self.show(path)
            if data is None:
                self.add(8, "config-not-parsed", loc, "present but not read: invalid JSON, or a link that leads "
                         "out of the repository. NOT INSPECTED")
            for scope, name, spec in self._servers(data):
                self._describe_server(loc, scope, name, spec)
            if isinstance(data, dict):
                self._claude_extras(loc, data)
            self._hidden_unicode(path)
        for path in (self.repo / ".codex" / "config.toml", self.home / ".codex" / "config.toml"):
            text = self.text(path)
            if text is None:
                continue
            tables = parse_toml_tables(text)
            for header, values in tables.items():
                found = re.match(r"^mcp_servers\.\"?([^\".]+)\"?$", header)
                if found:
                    spec = dict(values)
                    env = tables.get(header + ".env")
                    if isinstance(env, dict) and env:
                        spec["env"] = env
                    self._describe_server(self.show(path), "", found.group(1), spec)
            notify = tables.get("", {}).get("notify")
            if notify:
                self.add(8, "hook", self.show(path), f"notify: {command_summary(notify)}")
        self._plugins()
        self._skills()
        self._install_scripts()
        for path in self.rule_files():
            self._hidden_unicode(path)
        for name in self.files():
            # Everything an agent loads as instructions: skills and their references, commands, prompts.
            if name.endswith("SKILL.md") or "/skills/" in f"/{name}" and name.endswith(DOC_SUFFIXES):
                self._hidden_unicode(self.repo / name)
        self.cover(8, f"{len(seen)} agent config files found of {len(configs) + 2} known locations; "
                      f"{self._unicode_files} instruction, skill and config files scanned for hidden Unicode")

    def _claude_extras(self, loc: str, data: dict) -> None:
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            for event, groups in hooks.items():
                for group in groups if isinstance(groups, list) else []:
                    if not isinstance(group, dict):
                        continue
                    matcher = f"[{safe_name(group.get('matcher'))}]" if group.get("matcher") else ""
                    for hook in group.get("hooks") or []:
                        if not isinstance(hook, dict):
                            continue
                        kind = hook.get("type") if hook.get("type") in ("command", "prompt", "http", "agent") else "?"
                        if hook.get("command"):
                            body = command_summary(hook["command"])
                        elif hook.get("url"):
                            body = "calls a URL (not shown)"
                        else:
                            body = "prompt text (not shown)"
                        self.add(8, "hook", loc, f"{safe_name(event)}{matcher} ({kind}): {body}")
        for key in ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "otelHeadersHelper"):
            if data.get(key):
                self.add(8, "auto-run-command", loc, f"{key}: {command_summary(data[key])}")
        status_line = data.get("statusLine")
        if isinstance(status_line, dict) and status_line.get("command"):
            self.add(8, "auto-run-command", loc, f"statusLine: {command_summary(status_line['command'])}")
        enabled = data.get("enabledPlugins")
        if isinstance(enabled, dict) and enabled:
            self.add(8, "plugins-enabled", loc, safe_names(sorted(k for k, v in enabled.items() if v), 30))
        markets = data.get("extraKnownMarketplaces")
        if isinstance(markets, dict) and markets:
            described = []
            for name, value in markets.items():
                source = value.get("source") if isinstance(value, dict) else None
                origin = "?"
                if isinstance(source, dict):
                    if source.get("repo"):
                        origin = safe_name(source["repo"])
                    elif source.get("url"):
                        origin = "a URL (host not shown)"
                    elif source.get("path"):
                        origin = "a local path"
                described.append(f"{safe_name(name)} <- {origin}")
            self.add(8, "plugin-marketplace", loc, "; ".join(described[:15]))
        env = data.get("env")
        if isinstance(env, dict) and env:
            literal = sorted(str(k) for k, v in env.items()
                             if isinstance(v, str) and (shape_label(v) or (SECRET_NAME.search(str(k)) and v)))
            self.add(2, "settings-env", loc, f"sets: {safe_names(sorted(map(str, env)), 25)}"
                     + (f"; LITERAL SECRET for: {safe_names(literal)}" if literal else ""))

    def _plugins(self) -> None:
        installed = self.load_json(self.home / ".claude" / "plugins" / "installed_plugins.json")
        plugins = installed.get("plugins") if isinstance(installed, dict) else None
        if not isinstance(plugins, dict):
            return
        for name, entries in sorted(plugins.items()):
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                root = Path(str(entry.get("installPath") or ""))
                ships = [label for rel, label in (("hooks/hooks.json", "hooks"), (".mcp.json", "MCP servers"))
                         if root.is_absolute() and root.is_dir() and (root / rel).is_file()]
                self.add(8, "plugin-installed", "~/.claude/plugins",
                         f"{safe_name(name)} {safe_name(entry.get('version', '?'))} ({safe_name(entry.get('scope', '?'))})"
                         + (f"; SHIPS {' and '.join(ships)}" if ships else ""))

    def _skills(self) -> None:
        roots = [self.repo / rel for rel in SKILL_ROOTS_REPO] + [self.home / rel for rel in SKILL_ROOTS_HOME]
        for root in roots:
            if not root.is_dir():
                continue
            names, scripted, linked = [], 0, 0
            for skill_md in sorted(root.glob("*/SKILL.md")) + sorted(root.glob("*/*/SKILL.md")) + sorted(root.glob("*/*/*/SKILL.md")):
                directory = skill_md.parent
                if any(part.startswith(".") for part in directory.relative_to(root).parts):
                    continue
                names.append(directory.name)
                scripted += (directory / "scripts").is_dir()
                linked += directory.is_symlink()
                self._hidden_unicode(skill_md)
            if names:
                self.add(8, "skills", self.show(root),
                         f"{len(names)} skills ({scripted} bundle scripts, {linked} are symlinks): {safe_names(names, 30)}")

    def _install_scripts(self) -> None:
        lifecycle = ("preinstall", "install", "postinstall", "prepare", "prepublish", "prepack")
        root_package = self.load_json(self.repo / "package.json")
        declared = root_package.get("workspaces") if isinstance(root_package, dict) else None
        if isinstance(declared, dict):
            declared = declared.get("packages")
        patterns = [p.strip("/").replace("./", "", 1) for p in declared or [] if isinstance(p, str)]
        root_locked = any((self.repo / lock).is_file() for lock in LOCKFILES)
        for name in [n for n in self.files() if n.rsplit("/", 1)[-1] == "package.json"][:25]:
            folder = (self.repo / name).parent
            locked = any((folder / lock).is_file() for lock in LOCKFILES)
            # A lockfile at the root covers a nested package only when that package is one of the root's workspaces.
            inside = folder.relative_to(self.repo).as_posix()
            member = any(fnmatch.fnmatch(inside, pattern) for pattern in patterns)
            if not locked and not (root_locked and member):
                self.add(8, "no-lockfile", name, "NO LOCKFILE beside this package.json: an install resolves "
                         "every dependency to the newest matching release and runs its install scripts")
            data = self.load_json(self.repo / name)
            scripts = data.get("scripts") if isinstance(data, dict) else None
            for key in lifecycle:
                if isinstance(scripts, dict) and scripts.get(key):
                    self.add(8, "install-script", name, f"{key}: {command_summary(scripts[key])}")
        container = re.compile(r"\"(postCreateCommand|postStartCommand|onCreateCommand|initializeCommand"
                               r"|updateContentCommand|postAttachCommand)\"")
        for name in self.files():
            base = name.rsplit("/", 1)[-1]
            if base == "devcontainer.json":
                for lineno, line in enumerate((self.text(name) or "").splitlines(), 1):
                    found = container.search(line)
                    if found:
                        self.add(8, "install-script", f"{name}:{lineno}", f"{found.group(1)} runs when the container starts")
            elif name.endswith(".vscode/tasks.json") and "folderOpen" in (self.text(name) or ""):
                self.add(8, "auto-run-command", name, "a task runs on folder open (runOn: folderOpen)")
            elif base == ".envrc":
                self.add(8, "auto-run-command", name, "direnv executes this file on cd once allowed")

    def _hidden_unicode(self, path: Path) -> None:
        loc = self.show(path)
        if loc in self._unicode_seen:
            return
        self._unicode_seen.add(loc)
        text = self.text(path, MAX_CONFIG_BYTES)
        if text is None:
            return
        self._unicode_files += 1
        hits = []
        for lineno, line in enumerate(text.splitlines(), 1):
            previous = 0
            for col, char in enumerate(line, 1):
                cp = ord(char)
                if cp > 0x7F and hidden_codepoint(cp, previous) and not (cp == 0xFEFF and lineno == 1 and col == 1):
                    hits.append((lineno, col, cp))
                previous = cp
        if not hits:
            return
        for lineno, col, cp in hits[:MAX_PER_FILE]:
            self.add(8, "hidden-unicode", f"{loc}:{lineno}:{col}", f"U+{cp:04X} {unicodedata.name(chr(cp), 'UNNAMED')}")
        if len(hits) > MAX_PER_FILE:
            self.add(8, "hidden-unicode", loc, f"{len(hits)} hidden characters in total in this file")

    # -- check 9 -----------------------------------------------------------

    def ci(self) -> None:
        workflows = [n for n in self.files() if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", n)]
        entry = re.compile(r"[\"']?([\w-]{1,40})[\"']?\s*:\s*[\"']?write\b")
        for name in workflows:
            lines = (self.text(name) or "").splitlines()
            jobs_at = next((i for i, l in enumerate(lines) if re.match(r"^jobs\s*:", l)), len(lines))
            head = "\n".join(lines[:jobs_at])
            triggers = [t for t in ALL_TRIGGERS if re.search(r"(?<![\w-])" + t + r"(?![\w-])", head)]
            untrusted = [t for t in triggers if t in UNTRUSTED_TRIGGERS]
            agent, writes, secrets, interp, cache, pr_head = [], [], set(), [], [], []
            declares, block_indent = False, None
            for lineno, line in enumerate(lines, 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                code = line.split(" #", 1)[0]
                indent = len(code) - len(code.lstrip())
                # `write` counts only inside a permissions mapping: an env var
                # or input that happens to be `write` grants nothing.
                opened = re.match(r"^\s*(?:-\s*)?[\"']?permissions[\"']?\s*:\s*(.*)$", code)
                if opened:
                    declares = True
                    inline = opened.group(1).strip()
                    block_indent = None if inline else indent
                    if "write-all" in inline:
                        writes.append(f"write-all@{lineno}")
                    writes += [f"{m.group(1)}@{lineno}" for m in entry.finditer(inline)]
                elif block_indent is not None:
                    if indent <= block_indent:
                        block_indent = None
                    else:
                        found = entry.match(code.strip())
                        if found:
                            writes.append(f"{found.group(1)}@{lineno}")
                if AGENT_MARKER.search(code):
                    agent.append(lineno)
                secrets.update(re.findall(r"secrets\.([A-Za-z0-9_]{1,80})", code))
                if re.search(r"secrets\s*:\s*inherit", code):
                    secrets.add("(inherit: all secrets)")
                if UNTRUSTED_EXPR.search(code):
                    interp.append(lineno)
                if re.search(r"actions/cache|^\s*cache\s*:", code):
                    cache.append(lineno)
                if re.search(r"ref\s*:.*github\.event\.pull_request\.head|refs/pull/", code):
                    pr_head.append(lineno)
            note = f"triggers: {', '.join(triggers) or 'none found'}"
            note += f"; agent/LLM markers at lines {agent[:8]}" if agent else "; no agent marker"
            note += f"; WRITE PERMISSIONS: {', '.join(writes)}" if writes else (
                "; permissions block present, no write found" if declares
                else "; NO permissions BLOCK (repo default token scope applies)")
            note += f"; secrets used: {', '.join(sorted(secrets))}" if secrets else "; no secrets referenced"
            if interp:
                note += f"; untrusted event text interpolated at lines {interp[:8]}"
            if cache:
                note += f"; cache at lines {cache[:5]}"
            if pr_head:
                note += f"; checks out PR head at lines {pr_head[:5]}"
            if re.search(r"^\s*uses\s*:\s*\.?/?[\w./-]*\.github/workflows/|workflow_call", "\n".join(lines), re.M):
                note += "; calls or is a reusable workflow: read the other file too"
            self.add(9, "workflow", name, note)
            if agent and untrusted:
                self.add(9, "agent-on-untrusted-trigger", f"{name}:{agent[0]}",
                         f"AGENT RUNS ON {', '.join(untrusted)}"
                         + (f" WITH SECRETS ({len(secrets)})" if secrets else "")
                         + (f" AND WRITE PERMISSIONS ({', '.join(writes)})" if writes else ""))
            elif agent and "pull_request" in triggers:
                self.add(9, "agent-on-pull-request", f"{name}:{agent[0]}",
                         "an agent runs on pull_request: the PR's content is untrusted input. Fork PRs get a "
                         "read-only token and no secrets by default; same-repo PRs get this workflow's"
                         + (f" WRITE PERMISSIONS ({', '.join(writes)})" if writes else " permissions")
                         + (f" and {len(secrets)} secrets" if secrets else ""))
        other = re.compile(r"(?:^|/)(?:\.gitlab-ci\.yml|Jenkinsfile|azure-pipelines\.yml|bitbucket-pipelines\.yml"
                           r"|\.circleci/config\.yml|\.buildkite/[^/]+\.ya?ml)$")
        for name in self.files():
            if other.search(name):
                for lineno, line in enumerate((self.text(name) or "").splitlines(), 1):
                    if AGENT_MARKER.search(line):
                        self.add(9, "agent-in-ci", f"{name}:{lineno}", "agent or LLM marker")
        self.cover(9, f"{len(workflows)} GitHub Actions workflows; "
                      f"{sum(1 for n in self.files() if other.search(n))} other CI config files")

    # -- check 10 ----------------------------------------------------------

    def agent_modes(self) -> None:
        broad = re.compile(r"^(?:Bash|Bash\(\*\)|\*|Bash\((?:rm|sudo|git push|curl|wget|chmod|chown|dd|kill|terraform"
                           r"|kubectl|aws|gcloud|az|psql|mysql|docker|npm publish|gh|ssh|eval|bash|sh|python|node)\b.*\))$")
        for path in self._claude_settings_files():
            data = self.load_json(path)
            if not isinstance(data, dict):
                continue
            perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
            allow = [str(a) for a in perms.get("allow") or []]
            wide = [a for a in allow if broad.match(a)]
            mode = perms.get("defaultMode", "unset")
            note = f"defaultMode: {mode if mode in PERMISSION_MODES or mode == 'unset' else '<unrecognised value>'}"
            note += f"; allow rules: {len(allow)}"
            if wide:
                note += f"; BROAD ALLOW: {'; '.join(rule_head(w) for w in wide[:12])}"
            note += f"; deny rules: {len(perms.get('deny') or [])}"
            if perms.get("disableBypassPermissionsMode") == "disable":
                note += "; bypass mode disabled by setting"
            if data.get("skipDangerousModePermissionPrompt") is True:
                note += "; BYPASS-MODE WARNING PRE-ACCEPTED (skipDangerousModePermissionPrompt: true)"
            if data.get("enableAllProjectMcpServers") is True:
                note += "; EVERY PROJECT MCP SERVER AUTO-ENABLED (enableAllProjectMcpServers: true)"
            sandbox = data.get("sandbox")
            note += (f"; sandbox.enabled: {sandbox.get('enabled') is True}" if isinstance(sandbox, dict)
                     else "; no sandbox block")
            self.add(10, "agent-mode", self.show(path), note)
        state = self.load_json(self.home / ".claude.json")
        if isinstance(state, dict) and state.get("bypassPermissionsModeAccepted") is True:
            self.add(10, "agent-mode", "~/.claude.json", "bypass-permissions mode has been accepted on this machine")
        others = [self.home / rel for rel in OTHER_AGENT_SETTINGS_HOME]
        others += [self.repo / ".codex" / "config.toml", self.repo / ".gemini" / "settings.json",
                   self.repo / ".vscode" / "settings.json", self.repo / ".cursor" / "cli.json"]
        for path in others:
            for lineno, line in enumerate((self.text(path, MAX_CONFIG_BYTES) or "").splitlines(), 1):
                if line.lstrip().startswith(("#", "//")):
                    continue
                found = re.match(r"^\s*[\"']?([\w.-]{1,60})[\"']?\s*[:=]\s*[\"']?([\w-]{1,30})?", line)
                if found and AGENT_SETTING.search(found.group(1)):
                    value = (found.group(2) or "").lower()
                    shown = value if value in SETTING_WORDS else "(a value; read the line)"
                    self.add(10, "agent-setting", f"{self.show(path)}:{lineno}", f"{found.group(1)} = {shown}")
        # Which startup files a non-interactive shell loads decides whether a
        # safety net exists for an agent. This is read from the files; no shell
        # is started, because starting one would run those files.
        every_shell = {".zshenv"}
        bash_env = self.environ.get("BASH_ENV")
        rc_paths = [(self.home / rel, rel in every_shell) for rel in RC_FILES]
        if bash_env and Path(bash_env).is_absolute():
            rc_paths.append((Path(bash_env), True))
        guard = re.compile(r"^\s*(?:alias\s+(?:-g\s+)?|function\s+)?(rm|mv|cp|git|kubectl|terraform|tofu|docker|psql"
                           r"|aws|gcloud|dropdb)\s*(?:=|\(\))")
        alias_name = re.compile(r"^\s*alias\s+(?:-g\s+)?([\w.-]{1,40})=")
        present = [self.show(path) for path, _ in rc_paths if path.is_file()]
        self.cover(10, f"shell startup files read: {', '.join(present) or 'none found'}; "
                       f"{len(self._claude_settings_files())} Claude Code settings files; "
                       f"{sum(1 for p in others if p.is_file())} other agent settings files; no shell was started")
        for path, loads_for_agents in rc_paths:
            for lineno, line in enumerate((self.text(path) or "").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                where = f"{self.show(path)}:{lineno}"
                if BYPASS.search(line):
                    named = alias_name.match(line)
                    self.add(10, "bypass-in-shell-rc", where,
                             (f"alias {named.group(1)}" if named else "a line") + " launches an agent with a "
                             "permission-bypass flag")
                found = guard.match(line)
                if found:
                    self.add(10, "shell-safety-net", where,
                             f"alias or function named {found.group(1)}; "
                             + ("this file is read by every shell of its kind, agent shells included"
                                if loads_for_agents else
                                "this file is read by INTERACTIVE shells only: an agent's shell does not load it. "
                                "Confirm with: bash -c 'type " + found.group(1) + "'"))

    # -- driver ------------------------------------------------------------

    def run(self) -> None:
        # (checks a step contributes to, step). A step outside --only is not run at all.
        steps = [
            ({1, 2}, self.env_files), ({1, 2, 3, 4, 5, 8, 11}, self.scan_tracked_text),
            ({1, 2}, self.environment), ({2}, self.credential_files), ({2}, self.tracked_sensitive_files),
            ({3}, self.shell_scripts), ({3}, self.symlinks), ({4}, self.infrastructure),
            ({5}, self.prose_rules), ({5}, self.enforcement), ({6}, self.github_checks),
            ({7}, self.cloud_sync), ({2, 8, 11}, self.agent_config), ({9}, self.ci), ({10}, self.agent_modes),
        ]
        for checks, step in steps:
            if self.only and not checks & self.only:
                continue
            self.steps_run.append(step.__name__)
            try:
                step()
            except Exception as error:  # noqa: BLE001 - one broken parser must not end the audit
                # The message is withheld on purpose: it can quote file content.
                self.notes.append(f"collector step '{step.__name__}' failed ({type(error).__name__}); "
                                  f"do check {min(checks)} by hand")

    def render(self) -> str:
        out = [
            "blast-radius-audit collector: LEADS, not findings. Verify each one in the file before reporting it.",
            "Read-only. No secret values are printed: names, paths, hosts and line numbers only.",
            f"repo: {self.show(self.repo) if self.show(self.repo) != '.' else self.repo.name}"
            f" | git: {'yes' if self.is_git else 'no'} | GitHub queried: "
            + (f"yes, {self.github_requests} read-only requests through gh" if self.github_requests else "no"),
            f"directories not scanned: {', '.join(sorted(SKIP_DIRS))}",
            "UPPERCASE marks a trait to look at first. It is a pattern match like the rest, not a verdict.",
        ]
        out += [f"note: {note}" for note in self.notes]
        for check, title in CHECKS.items():
            if self.only and check not in self.only:
                continue
            out += ["", f"## {check}. {title}"]
            if self.coverage.get(check):
                out.append("examined: " + "; ".join(dict.fromkeys(self.coverage[check])))
            rows = [item for item in self.items if item["check"] == check]
            if not rows:
                out.append("(no leads from the collector; the manual part of this check still applies)")
            for item in rows:
                out.append(f"- {item['loc']} | {item['kind']} | {item['note']}".rstrip(" |"))
            for (number, kind), count in sorted(self._counts.items()):
                if number == check and count > MAX_PER_KIND:
                    out.append(f"- ... {count - MAX_PER_KIND} more '{kind}' leads not shown; search the repo for the rest")
            for (number, kind, name), count in sorted(self._file_counts.items()):
                if number == check and count > MAX_PER_FILE:
                    out.append(f"- {name} | {kind} | ... {count - MAX_PER_FILE} more in this file not shown")
        return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only evidence collector for the blast-radius audit.")
    parser.add_argument("--repo", default=".", help="repository to audit (default: current directory)")
    parser.add_argument("--home", default=None, help="treat this directory as the home directory (for testing)")
    parser.add_argument("--github", action="store_true",
                        help="also make read-only GitHub API calls through gh (token scopes, branch protection)")
    parser.add_argument("--only", default="", help="comma-separated check numbers, e.g. 1,3,8")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--keys", metavar="FILE", help="print the key names of one env, JSON or TOML file "
                        "(never its values) and exit")
    args = parser.parse_args(argv)
    if args.keys:
        rows = key_listing(Path(args.keys))
        sys.stdout.write("\n".join(" ".join(row.split()) for row in rows) + "\n" if rows else "no keys found\n")
        return 0
    only = set()
    for part in filter(None, (p.strip() for p in args.only.split(","))):
        if not re.fullmatch(r"[0-9]{1,2}", part) or int(part) not in CHECKS:
            parser.error(f"--only takes check numbers 1-{len(CHECKS)}, got '{part}'")
        only.add(int(part))
    repo = Path(args.repo)
    if not repo.is_dir():
        parser.error(f"--repo is not a directory: {args.repo}")
    home = Path(args.home) if args.home else Path.home()
    collector = Collector(repo, home, os.environ, github=args.github, only=only, system_paths=args.home is None)
    collector.run()
    if args.json:
        json.dump({"notes": collector.notes, "examined": collector.coverage, "leads": collector.items},
                  sys.stdout, indent=1)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(collector.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
