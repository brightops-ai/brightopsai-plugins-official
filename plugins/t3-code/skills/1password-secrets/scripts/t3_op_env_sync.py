#!/usr/bin/env python3
"""Sync a references file into T3 Code's per-provider variables as 1Password references.

T3 Code resolves the op:// references itself when a provider session starts. Only references
are written; no secret value is read or stored.

Usage: t3_op_env_sync.py [--dry-run] [--replace] [--account=<account>]
                         [--remove=NAME ... | --remove-all] <provider> [<provider> ...]
       t3_op_env_sync.py --show-target
       t3_op_env_sync.py --list-references
  e.g. t3_op_env_sync.py claudeAgent codex cursor

  --show-target  print the settings path, whether it exists, the provider instance names and
                 whether a "onepassword" secret provider exists; write nothing
  --list-references
                 validate the references file with the rules of a sync, then print
                 NAME<TAB>REFERENCE per line; write nothing. Exits non-zero with a
                 line-numbered message, never echoing a line, when the file is invalid.
  --dry-run      report what would change and write nothing
  --replace      overwrite a variable of the same name that holds a literal value or a
                 reference through another secret provider (without it, the run stops)
  --remove=NAME  remove a variable this script manages (a "onepassword" reference) from the
                 named providers; repeatable; works with an empty or missing references file.
                 It wins over a line of the same name in the references file.
  --remove-all   remove every name listed in the references file the same way
  --account      1Password account for a newly added secret provider: the shorthand, sign-in
                 address without https://, or ID (default my.1password.com, the address of
                 individual and family accounts; with a service account token any address
                 works). An existing provider entry is left as it is.

Ownership: only the names in the references file are managed. Every other variable, including
other 1Password references, is kept untouched. A managed variable leaves only through --remove
or --remove-all.

Environment:
  T3_OP_ENV    references file (default ~/.config/claude/op.env), one NAME=op://vault/item/field
               per line; blank lines and lines starting with # are skipped
  T3CODE_HOME  T3 Code data directory (default ~/.t3); settings are read from
               <T3CODE_HOME>/userdata/settings.json

Run it while T3 Code is closed, or when none of the named providers' threads are mid-run: a
settings change restarts that provider's sessions. Re-run after editing the references file.
A real run holds an exclusive lock on <settings>.lock (an empty file, kept after the run so the
lock stays meaningful; safe to leave), writes a 0600 backup of the original
bytes beside settings.json (settings.json.bak-<time>-<pid>[-n]) and aborts without writing if
settings.json changed while it ran. Error messages name a file and line, never a line's content.
"""
import fcntl
import json
import os
import re
import sys
import tempfile
import time

# The id T3 Code stores the secret provider under, and the id each variable points back at.
SECRET_PROVIDER_ID = "onepassword"
DEFAULT_ACCOUNT = "my.1password.com"

# Limits and shapes T3 Code accepts.
MAX_REFERENCE = 1024
MAX_NAME = 128
MAX_ACCOUNT = 253
ACCOUNT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# op://vault/item[/section]/field[?attribute=value]; segments hold letters, digits, space . _ -
SEGMENT = r"[A-Za-z0-9._-](?:[A-Za-z0-9 ._-]*[A-Za-z0-9._-])?"
REFERENCE = re.compile(rf"op://{SEGMENT}(?:/{SEGMENT}){{2,3}}(?:\?[a-z-]+=[A-Za-z0-9_-]+)?")
VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def fail(message):
    sys.exit(f"t3_op_env_sync: {message}")

def op_env_path():
    home = os.path.expanduser("~")
    return os.environ.get("T3_OP_ENV") or os.path.join(home, ".config", "claude", "op.env")

def paths():
    home = os.path.expanduser("~")
    op_env = op_env_path()
    t3_home = os.environ.get("T3CODE_HOME") or os.path.join(home, ".t3")
    raw = os.path.join(t3_home, "userdata", "settings.json")
    real = os.path.realpath(raw)
    if os.path.islink(raw) and os.path.dirname(real) != os.path.realpath(os.path.dirname(raw)):
        fail("settings.json is a symlink to outside its directory; refusing to follow it")
    return op_env, real

def valid_name(name):
    return len(name) <= MAX_NAME and VARIABLE_NAME.fullmatch(name) is not None

def read_references(op_env, allow_empty):
    try:
        with open(op_env, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        if allow_empty:
            return {}
        fail(f"cannot read references file {op_env}: no such file")
    except OSError as error:
        fail(f"cannot read references file {op_env}: {error.strerror}")
    refs = {}
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail(f"{op_env}:{number}: expected NAME=op://vault/item/field")
        name, ref = (part.strip() for part in line.split("=", 1))
        if not valid_name(name):
            fail(f"{op_env}:{number}: the variable name is not valid "
                 f"(letters, digits and underscore, at most {MAX_NAME} characters)")
        if len(ref) > MAX_REFERENCE:
            fail(f"{op_env}:{number}: the reference is longer than {MAX_REFERENCE} characters")
        if not REFERENCE.fullmatch(ref):
            fail(f"{op_env}:{number}: the value is not a reference T3 Code accepts "
                 "(op://vault/item/field); a literal value does not belong in this file")
        if name in refs:
            fail(f"{op_env}:{number}: {name} is defined twice")
        refs[name] = ref
    if not refs and not allow_empty:
        fail(f"{op_env} holds no references")
    return refs

def load_settings(settings_path, data):
    try:
        settings = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"{settings_path} is not valid JSON: {error}")
    if not isinstance(settings, dict):
        fail(f"{settings_path} does not hold a JSON object")
    return settings

def read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as error:
        fail(f"cannot read {path}: {error.strerror}")

def show_target(settings_path):
    print(f"settings: {settings_path}")
    if not os.path.exists(settings_path):
        print("exists: no")
        return
    print("exists: yes")
    settings = load_settings(settings_path, read_bytes(settings_path))
    instances = settings.get("providerInstances")
    names = sorted(instances) if isinstance(instances, dict) else []
    print("provider instances: " + (", ".join(names) if names else "none"))
    secret_providers = settings.get("secretProviders")
    has = isinstance(secret_providers, dict) and isinstance(
        secret_providers.get(SECRET_PROVIDER_ID), dict)
    print(f"secret provider {SECRET_PROVIDER_ID}: {'yes' if has else 'no'}")

def plan_provider(settings_path, provider, instance, refs, removes, replace):
    """Return (new environment list, counts) for one provider; fail on a conflict."""
    existing = instance.get("environment", [])
    if not isinstance(existing, list):
        fail(f"{settings_path}: {provider}.environment is not a list")
    result, placed, removed = [], set(), 0
    for index, variable in enumerate(existing):
        where = f"{settings_path}: provider {provider!r} environment index {index}"
        if not isinstance(variable, dict):
            fail(f"{where} is not an object")
        name = variable.get("name")
        if not isinstance(name, str):
            fail(f"{where} has no string name")
        secret = variable.get("secret")  # absent: a literal value; anything but an object is an error
        if "secret" in variable and not isinstance(secret, dict):
            fail(f"{where} has a secret that is not an object")
        managed = isinstance(secret, dict) and secret.get("provider") == SECRET_PROVIDER_ID
        if name in refs:
            if not managed and not replace:
                kind = "a reference through another secret provider" if secret else "a literal value"
                fail(f"{provider}: {name} already exists as {kind}; "
                     "re-run with --replace to overwrite it")
            if name not in placed:
                result.append(managed_variable(name, refs[name]))
                placed.add(name)
        elif name in removes:
            if not managed:
                fail(f"{provider}: {name} is not a {SECRET_PROVIDER_ID} reference; --remove "
                     "only removes variables this script manages")
            removed += 1
        else:
            result.append(variable)
    kept = len(result) - len(placed)
    for name, ref in refs.items():
        if name not in placed:
            result.append(managed_variable(name, ref))
    return result, {"references": len(refs), "removed": removed, "kept": kept}

def managed_variable(name, ref):
    return {"name": name, "value": "", "sensitive": True,
            "secret": {"provider": SECRET_PROVIDER_ID, "reference": ref}}

def write_backup(settings_path, original):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = f"{settings_path}.bak-{stamp}-{os.getpid()}"
    for counter in range(1000):
        backup = base if counter == 0 else f"{base}-{counter}"
        try:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(original)
        return backup
    fail("could not find a free backup name")

def parse_args(argv):
    opts = {"dry_run": False, "replace": False, "show_target": False,
            "account": DEFAULT_ACCOUNT, "removes": [], "remove_all": False,
            "list_references": False, "providers": []}
    for arg in argv:
        if arg == "--dry-run":
            opts["dry_run"] = True
        elif arg == "--replace":
            opts["replace"] = True
        elif arg == "--show-target":
            opts["show_target"] = True
        elif arg == "--list-references":
            opts["list_references"] = True
        elif arg == "--remove-all":
            opts["remove_all"] = True
        elif arg.startswith("--account="):
            opts["account"] = arg.split("=", 1)[1]
        elif arg.startswith("--remove="):
            name = arg.split("=", 1)[1]
            if not valid_name(name):
                fail("--remove needs a valid variable name")
            opts["removes"].append(name)
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif arg.startswith("-"):
            fail(f"unknown option {arg}")
        else:
            opts["providers"].append(arg)
    if not (opts["show_target"] or opts["list_references"] or opts["providers"]):
        sys.exit(__doc__)
    account = opts["account"]
    if len(account) > MAX_ACCOUNT or not ACCOUNT.fullmatch(account):
        fail("--account needs a shorthand, sign-in address, or ID: letters, digits, '.', '_' "
             f"and '-', starting with a letter or digit, at most {MAX_ACCOUNT} characters")
    return opts

def main(argv):
    opts = parse_args(argv)
    if opts["list_references"]:
        for name, ref in read_references(op_env_path(), allow_empty=False).items():
            print(f"{name}\t{ref}")
        return
    op_env, settings_path = paths()
    if opts["show_target"]:
        show_target(settings_path)
        return

    removing = bool(opts["removes"]) or opts["remove_all"]
    refs = read_references(op_env, allow_empty=removing)
    # --remove and --remove-all win over a line of the same name in the references file.
    removes = set(opts["removes"])
    if opts["remove_all"]:
        removes |= set(refs)
    refs = {name: ref for name, ref in refs.items() if name not in removes}

    lock_fd = None
    if not opts["dry_run"]:
        if not os.path.exists(settings_path):
            fail(f"cannot read {settings_path}: no such file")
        try:
            lock_fd = os.open(settings_path + ".lock",
                              os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            fail(f"cannot take the settings lock beside {settings_path}: {error.strerror}")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fail("another run holds the settings lock; try again when it finishes")
    try:
        run(opts, settings_path, refs, removes)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)

def run(opts, settings_path, refs, removes):
    original = read_bytes(settings_path)
    settings = load_settings(settings_path, original)
    instances = settings.get("providerInstances")
    if not isinstance(instances, dict):
        fail(f"{settings_path} has no providerInstances; open a thread with each provider once")
    for provider in opts["providers"]:
        if not isinstance(instances.get(provider), dict):
            known = ", ".join(sorted(instances)) or "none"
            fail(f"no provider instance named {provider!r} (found: {known})")

    secret_providers = settings.get("secretProviders", {})
    if not isinstance(secret_providers, dict):
        fail(f"{settings_path}: secretProviders is not an object")
    if refs:
        settings["secretProviders"] = secret_providers
        secret_providers.setdefault(
            SECRET_PROVIDER_ID,
            {"kind": "one_password", "label": "1Password", "config": {"account": opts["account"]}},
        )

    for provider in opts["providers"]:
        instance = instances[provider]
        environment, counts = plan_provider(
            settings_path, provider, instance, refs, removes, opts["replace"])
        instance["environment"] = environment
        print(f"{provider}: {counts['references']} references, {counts['removed']} removed, "
              f"{counts['kept']} other variables kept")

    if opts["dry_run"]:
        print("dry run: nothing written")
        return

    backup = write_backup(settings_path, original)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(settings_path), prefix=".settings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, os.stat(settings_path).st_mode & 0o777)
        if read_bytes(settings_path) != original:
            os.unlink(tmp)
            os.unlink(backup)
            fail("settings.json changed while this ran; nothing was written")
        os.replace(tmp, settings_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print(f"written; backup at {backup}")

if __name__ == "__main__":
    main(sys.argv[1:])
