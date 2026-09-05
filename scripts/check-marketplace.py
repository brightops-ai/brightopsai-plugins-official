#!/usr/bin/env python3
"""Check that marketplace metadata, plugin manifests, README, and skills agree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MARKETPLACE_FILE = ".claude-plugin/marketplace.json"
README_FILE = "README.md"

README_ROW = re.compile(
    r"^\|\s*\*\*\[(?P<name>[^\]]+)\]\(plugins/(?P<slug>[^)]+)\)\*\*"
    r"\s*\|\s*(?P<version>[^|\s]+)\s*\|"
)


def collect_findings(root: Path | str) -> list[str]:
    """Return one-line findings for a marketplace tree. Empty means the tree is clean."""
    root = Path(root)
    found: list[str] = []

    marketplace, marketplace_error = _load_marketplace(root)
    if marketplace_error:
        found.append(marketplace_error)

    disk_plugins = _discover_disk_plugins(root)
    readme_rows, readme_error = _load_readme_rows(root)
    if readme_error:
        found.append(readme_error)

    if marketplace is not None:
        found.extend(_check_marketplace_entries(root, marketplace))

    readme_by_slug = {slug: version for slug, version in readme_rows}

    for name, plugin_dir in disk_plugins.items():
        plugin_data, plugin_error = _load_plugin_json(root, plugin_dir)
        if plugin_error:
            found.append(plugin_error)
            continue

        found.extend(_check_plugin_identity(name, plugin_data))

        plugin_version = plugin_data.get("version") if isinstance(plugin_data, dict) else None

        if marketplace is not None:
            entry = _marketplace_entry(marketplace, name)
            if entry is None:
                found.append(
                    f'plugins/{name}/.claude-plugin/plugin.json: '
                    f'plugin "{name}" is not registered in {MARKETPLACE_FILE}'
                )
            else:
                found.extend(
                    check_marketplace_plugin_version(name, plugin_version, entry)
                )

        if readme_error is None:
            if name not in readme_by_slug:
                found.append(
                    f'{README_FILE}: plugin "{name}" is missing from the Plugins table'
                )
            elif plugin_version is not None and readme_by_slug[name] != plugin_version:
                found.append(
                    f'{README_FILE}: plugin "{name}" version is '
                    f'"{readme_by_slug[name]}", plugin.json has "{plugin_version}"'
                )

        found.extend(_check_plugin_skills(root, plugin_dir, plugin_data))

    if readme_error is None:
        for slug, _version in readme_rows:
            if slug not in disk_plugins:
                found.append(
                    f'{README_FILE}: plugin "{slug}" is listed but does not exist'
                )

    return found


def check_marketplace_plugin_version(
    plugin_name: str,
    plugin_version: Any,
    marketplace_entry: dict[str, Any],
) -> list[str]:
    """Compare plugin.json version to marketplace.json version when present.

    Follow-up #37 will invert this: a marketplace ``version`` field becomes a
    failure instead of a match requirement. Keep the rule in this one function.
    """
    if "version" not in marketplace_entry:
        return []
    marketplace_version = marketplace_entry["version"]
    if marketplace_version != plugin_version:
        return [
            f'{MARKETPLACE_FILE}: plugin "{plugin_name}" version is '
            f'"{marketplace_version}", plugin.json has "{plugin_version}"'
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check marketplace metadata consistency."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Marketplace repository root (default: current directory)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    findings = collect_findings(root)
    if findings:
        sys.stdout.write("\n".join(findings) + "\n")
        return 1
    sys.stdout.write(_ok_line(root) + "\n")
    return 0


def _ok_line(root: Path) -> str:
    plugins = _discover_disk_plugins(root)
    n_skills = 0
    for plugin_dir in plugins.values():
        skills_root = plugin_dir / "skills"
        if skills_root.is_dir():
            n_skills += sum(
                1 for path in skills_root.rglob("SKILL.md") if path.is_file()
            )
    return f"OK: {len(plugins)} plugins, {n_skills} skills"


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _discover_disk_plugins(root: Path) -> dict[str, Path]:
    plugins_dir = root / "plugins"
    found: dict[str, Path] = {}
    if not plugins_dir.is_dir():
        return found
    for child in sorted(plugins_dir.iterdir()):
        manifest = child / ".claude-plugin" / "plugin.json"
        if child.is_dir() and manifest.is_file():
            found[child.name] = child
    return found


def _load_json(root: Path, path: Path) -> tuple[Any, str | None]:
    rel = _rel(root, path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{rel}: cannot read ({exc})"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"{rel}: malformed JSON: {exc}"


def _load_marketplace(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = root / MARKETPLACE_FILE
    if not path.is_file():
        return None, f"{MARKETPLACE_FILE}: file not found"
    data, error = _load_json(root, path)
    if error:
        return None, error
    if not isinstance(data, dict):
        return None, f"{MARKETPLACE_FILE}: top-level value is not an object"
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return None, f'{MARKETPLACE_FILE}: missing "plugins" array'
    return data, None


def _load_plugin_json(
    root: Path, plugin_dir: Path
) -> tuple[dict[str, Any] | None, str | None]:
    path = plugin_dir / ".claude-plugin" / "plugin.json"
    data, error = _load_json(root, path)
    if error:
        return None, error
    if not isinstance(data, dict):
        return None, f"{_rel(root, path)}: top-level value is not an object"
    return data, None


def _marketplace_entry(
    marketplace: dict[str, Any], name: str
) -> dict[str, Any] | None:
    for entry in marketplace.get("plugins", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def _check_marketplace_entries(
    root: Path,
    marketplace: dict[str, Any],
) -> list[str]:
    found: list[str] = []
    for index, entry in enumerate(marketplace["plugins"]):
        if not isinstance(entry, dict):
            found.append(f"{MARKETPLACE_FILE}: plugins[{index}] is not an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            found.append(f'{MARKETPLACE_FILE}: plugins[{index}] missing "name"')
            continue
        if "source" not in entry:
            found.append(f'{MARKETPLACE_FILE}: plugin "{name}" missing "source"')
            continue
        source = entry["source"]
        if not isinstance(source, str):
            found.append(
                f'{MARKETPLACE_FILE}: plugin "{name}" source is not a string'
            )
            continue
        expected = f"./plugins/{name}"
        if source != expected:
            found.append(
                f'{MARKETPLACE_FILE}: plugin "{name}" source is "{source}", '
                f'expected "{expected}"'
            )
        plugin_json = _source_plugin_json(root, source)
        if plugin_json is None or not plugin_json.is_file():
            found.append(
                f'{MARKETPLACE_FILE}: plugin "{name}" source "{source}" '
                f"does not exist"
            )
    return found


def _source_plugin_json(root: Path, source: str) -> Path | None:
    if source.startswith("./"):
        rel = source[2:]
    else:
        rel = source
    if not rel or rel.startswith("/") or any(part == ".." for part in Path(rel).parts):
        return None
    return root / rel / ".claude-plugin" / "plugin.json"


def _check_plugin_identity(dir_name: str, plugin_data: dict[str, Any]) -> list[str]:
    rel = f"plugins/{dir_name}/.claude-plugin/plugin.json"
    name = plugin_data.get("name")
    if not isinstance(name, str) or not name:
        return [f'{rel}: missing "name"']
    if name != dir_name:
        return [f'{rel}: name is "{name}", expected "{dir_name}"']
    return []


def _load_readme_rows(
    root: Path,
) -> tuple[list[tuple[str, str]], str | None]:
    path = root / README_FILE
    if not path.is_file():
        return [], f"{README_FILE}: file not found"
    text = path.read_text(encoding="utf-8")
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = README_ROW.match(line)
        if not match:
            continue
        rows.append((match.group("slug"), match.group("version")))
    return rows, None


def _check_plugin_skills(
    root: Path, plugin_dir: Path, plugin_data: dict[str, Any]
) -> list[str]:
    found: list[str] = []
    name = plugin_dir.name
    manifest_rel = f"plugins/{name}/.claude-plugin/plugin.json"
    listed_raw = plugin_data.get("skills", [])
    if listed_raw is None:
        listed_raw = []
    if not isinstance(listed_raw, list):
        found.append(f'{manifest_rel}: "skills" is not an array')
        listed_raw = []

    listed_norm: dict[str, str] = {}
    for item in listed_raw:
        if not isinstance(item, str):
            found.append(f"{manifest_rel}: skills entry {item!r} is not a string")
            continue
        listed_norm[_normalize_skill_path(item)] = item

    skills_root = plugin_dir / "skills"
    if skills_root.is_dir():
        for skill_md in sorted(skills_root.rglob("SKILL.md")):
            if not skill_md.is_file() or skill_md.name != "SKILL.md":
                continue
            found.extend(_check_skill_frontmatter(root, skill_md))
            rel_under_skills = skill_md.parent.relative_to(skills_root)
            if len(rel_under_skills.parts) > 1:
                norm = (Path("skills") / rel_under_skills).as_posix()
                if norm not in listed_norm:
                    found.append(
                        f'{manifest_rel}: nested skill "./{norm}" is not listed '
                        f"in the skills array"
                    )

    for norm, original in listed_norm.items():
        skill_md = plugin_dir / Path(norm) / "SKILL.md"
        if not skill_md.is_file():
            found.append(
                f'{manifest_rel}: skills entry "{original}" has no SKILL.md'
            )
    return found


def _normalize_skill_path(path: str) -> str:
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def _check_skill_frontmatter(root: Path, skill_md: Path) -> list[str]:
    rel = _rel(root, skill_md)
    text = skill_md.read_text(encoding="utf-8")
    keys = _frontmatter_keys(text)
    if keys is None:
        return [f"{rel}: missing YAML frontmatter"]
    missing = [field for field in ("name", "description") if field not in keys]
    if not missing:
        return []
    label = "fields" if len(missing) > 1 else "field"
    return [f"{rel}: missing YAML frontmatter {label} {', '.join(missing)}"]


def _frontmatter_keys(text: str) -> set[str] | None:
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---"):
        return None
    rest = text[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    else:
        return None
    keys: set[str] = set()
    for line in rest.splitlines():
        if line.strip() == "---":
            break
        if not line or line[0] in " \t#":
            continue
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


if __name__ == "__main__":
    raise SystemExit(main())
