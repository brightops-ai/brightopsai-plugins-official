#!/usr/bin/env python3
"""Check that marketplace metadata, plugin manifests, READMEs, and skills agree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MARKETPLACE_FILE = ".claude-plugin/marketplace.json"
README_FILE = "README.md"
PLUGIN_STRING_FIELDS = (
    "displayName",
    "homepage",
    "repository",
    "license",
)
PLAYWRIGHT_MCP_MARKER = "mcp__plugin_playwright_playwright__"
PLAYWRIGHT_PLUGIN_NAME = "playwright"
PLAYWRIGHT_MARKETPLACE = "claude-plugins-official"
PLAYWRIGHT_INSTALL_COMMAND = "/plugin install playwright@claude-plugins-official"
PLUGIN_README_HEADINGS = (
    "Overview",
    "Install",
    "Skills",
    "Prerequisites",
    "Data",
    "Update",
    "Uninstall",
)
KNOWN_VERSION_FLOORS = {
    "agent-teams": "v2.1.178",
    "brightops-ai-skills": "v2.1.196",
}

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
        found.extend(check_marketplace_catalog_metadata(marketplace))
        found.extend(_check_marketplace_entries(root, marketplace))

    readme_by_slug = {slug: version for slug, version in readme_rows}
    needed_marketplaces: set[str] = set()
    uses_playwright = False

    for name, plugin_dir in disk_plugins.items():
        plugin_data, plugin_error = _load_plugin_json(root, plugin_dir)
        if plugin_error:
            found.append(plugin_error)
            continue

        found.extend(_check_plugin_identity(name, plugin_data))
        found.extend(check_plugin_manifest_fields(name, plugin_data))

        plugin_version = plugin_data.get("version") if isinstance(plugin_data, dict) else None

        if marketplace is not None and _marketplace_entry(marketplace, name) is None:
            found.append(
                f'plugins/{name}/.claude-plugin/plugin.json: '
                f'plugin "{name}" is not registered in {MARKETPLACE_FILE}'
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
        needed_marketplaces.update(_dependency_marketplaces(plugin_data))
        uses_this_playwright = _plugin_uses_playwright_mcp(plugin_dir)
        if uses_this_playwright:
            uses_playwright = True
            found.extend(
                _check_playwright_plugin(root, name, plugin_dir, plugin_data)
            )
        found.extend(
            check_plugin_readme(
                name, plugin_dir, uses_playwright=uses_this_playwright
            )
        )

    if marketplace is not None:
        for entry in marketplace.get("plugins", []):
            if isinstance(entry, dict):
                needed_marketplaces.update(_dependency_marketplaces(entry))
        this_name = marketplace.get("name")
        if isinstance(this_name, str) and this_name:
            needed_marketplaces.discard(this_name)
        found.extend(
            check_cross_marketplace_allowlist(marketplace, needed_marketplaces)
        )

    if readme_error is None:
        readme_text = (root / README_FILE).read_text(encoding="utf-8")
        if uses_playwright and PLAYWRIGHT_INSTALL_COMMAND not in readme_text:
            found.append(
                f'{README_FILE}: missing "{PLAYWRIGHT_INSTALL_COMMAND}"'
            )
        for name in disk_plugins:
            needle = f"plugins/{name}/README.md"
            if needle not in readme_text:
                found.append(f"{README_FILE}: missing link to {needle}")
        for slug, _version in readme_rows:
            if slug not in disk_plugins:
                found.append(
                    f'{README_FILE}: plugin "{slug}" is listed but does not exist'
                )

    return found


def check_plugin_manifest_fields(
    plugin_name: str,
    plugin_data: dict[str, Any],
) -> list[str]:
    """Fail if plugin.json is missing Discover metadata (#38)."""
    rel = f"plugins/{plugin_name}/.claude-plugin/plugin.json"
    found: list[str] = []
    for field in PLUGIN_STRING_FIELDS:
        if not _nonempty_string(plugin_data.get(field)):
            found.append(f'{rel}: missing "{field}"')
    if not _nonempty_string_list(plugin_data.get("keywords")):
        found.append(f'{rel}: missing "keywords"')
    return found


def check_marketplace_catalog_metadata(
    marketplace: dict[str, Any],
) -> list[str]:
    """Fail if the marketplace root is missing $schema or owner contact (#38)."""
    found: list[str] = []
    if not _nonempty_string(marketplace.get("$schema")):
        found.append(f'{MARKETPLACE_FILE}: missing "$schema"')
    owner = marketplace.get("owner")
    if not isinstance(owner, dict):
        found.append(f'{MARKETPLACE_FILE}: missing "owner"')
        return found
    has_url = _nonempty_string(owner.get("url"))
    has_email = _nonempty_string(owner.get("email"))
    if not has_url and not has_email:
        found.append(f'{MARKETPLACE_FILE}: owner missing "email" or "url"')
    return found


def check_marketplace_entry_metadata(
    plugin_name: str,
    marketplace_entry: dict[str, Any],
    plugin_data: dict[str, Any] | None,
) -> list[str]:
    """Fail if an entry lacks category/tags or its description drifts (#38)."""
    found: list[str] = []
    prefix = f'{MARKETPLACE_FILE}: plugin "{plugin_name}"'
    if not _nonempty_string(marketplace_entry.get("category")):
        found.append(f'{prefix} missing "category"')
    if not _nonempty_string_list(marketplace_entry.get("tags")):
        found.append(f'{prefix} missing "tags"')
    if "description" not in marketplace_entry:
        return found
    plugin_desc = (
        plugin_data.get("description") if isinstance(plugin_data, dict) else None
    )
    if marketplace_entry.get("description") != plugin_desc:
        found.append(f"{prefix} description does not match plugin.json")
    return found


def check_plugin_readme(
    plugin_name: str,
    plugin_dir: Path,
    *,
    uses_playwright: bool = False,
) -> list[str]:
    """Fail if a plugin README is missing or omits the #40 sections."""
    rel = f"plugins/{plugin_name}/README.md"
    path = plugin_dir / "README.md"
    if not path.is_file():
        return [f"{rel}: file not found"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{rel}: cannot read ({exc})"]

    found: list[str] = []
    headings = _markdown_h2_headings(text)
    for heading in PLUGIN_README_HEADINGS:
        if heading not in headings:
            found.append(f'{rel}: missing "## {heading}" heading')
    install = f"/plugin install {plugin_name}@brightopsai-plugins-official"
    if install not in text:
        found.append(f'{rel}: missing "{install}"')
    if f"/{plugin_name}:" not in text:
        found.append(f'{rel}: missing namespaced invoke "/{plugin_name}:..."')
    if "${CLAUDE_PLUGIN_DATA}" not in text:
        found.append(f'{rel}: missing "${{CLAUDE_PLUGIN_DATA}}"')
    if "/plugin update" not in text:
        found.append(f'{rel}: missing "/plugin update"')
    if "CHANGELOG.md" not in text:
        found.append(f"{rel}: missing CHANGELOG.md link")
    floor = KNOWN_VERSION_FLOORS.get(plugin_name)
    if floor is not None and floor not in text:
        found.append(f'{rel}: missing Claude Code version floor "{floor}"')
    if uses_playwright and PLAYWRIGHT_INSTALL_COMMAND not in text:
        found.append(f'{rel}: missing "{PLAYWRIGHT_INSTALL_COMMAND}"')
    return found


def plugin_declares_playwright_dependency(plugin_data: dict[str, Any]) -> bool:
    """True when plugin.json depends on playwright from claude-plugins-official."""
    for name, marketplace in _iter_dependency_refs(plugin_data.get("dependencies")):
        if name == PLAYWRIGHT_PLUGIN_NAME and marketplace == PLAYWRIGHT_MARKETPLACE:
            return True
    return False


def check_cross_marketplace_allowlist(
    marketplace: dict[str, Any],
    needed: set[str],
) -> list[str]:
    """Fail if a named foreign marketplace is not in the allowlist (#39)."""
    if not needed:
        return []
    raw = marketplace.get("allowCrossMarketplaceDependenciesOn")
    listed: set[str] = set()
    if isinstance(raw, list):
        listed = {
            item.strip()
            for item in raw
            if isinstance(item, str) and item.strip()
        }
    found: list[str] = []
    for name in sorted(needed):
        if name not in listed:
            found.append(
                f'{MARKETPLACE_FILE}: cross-marketplace dependency on "{name}" '
                f'is not in "allowCrossMarketplaceDependenciesOn"'
            )
    return found


def check_marketplace_plugin_version(
    plugin_name: str,
    marketplace_entry: dict[str, Any],
) -> list[str]:
    """Fail if a marketplace entry sets ``version``; plugin.json is the pin.

    The README table is compared to plugin.json separately. A marketplace
    copy is not a second source of truth — Claude Code does not warn if it
    drifts.
    """
    if "version" not in marketplace_entry:
        return []
    return [
        f'{MARKETPLACE_FILE}: plugin "{plugin_name}" has "version"; '
        f"plugin.json is the sole pin"
    ]


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


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _markdown_h2_headings(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        if line.startswith("## "):
            found.add(line[3:].strip())
    return found


def _plugin_data_for_source(root: Path, source: Any) -> dict[str, Any] | None:
    if not isinstance(source, str):
        return None
    plugin_json = _source_plugin_json(root, source)
    if plugin_json is None or not plugin_json.is_file():
        return None
    plugin_data, error = _load_plugin_json(root, plugin_json.parent.parent)
    if error:
        return None
    return plugin_data


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
        found.extend(check_marketplace_plugin_version(name, entry))
        plugin_data = _plugin_data_for_source(root, entry.get("source"))
        found.extend(check_marketplace_entry_metadata(name, entry, plugin_data))
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


def _plugin_uses_playwright_mcp(plugin_dir: Path) -> bool:
    skills_root = plugin_dir / "skills"
    if not skills_root.is_dir():
        return False
    for skill_md in skills_root.rglob("SKILL.md"):
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        if PLAYWRIGHT_MCP_MARKER in text:
            return True
    return False


def _check_playwright_plugin(
    root: Path,
    name: str,
    plugin_dir: Path,
    plugin_data: dict[str, Any],
) -> list[str]:
    found: list[str] = []
    rel = f"plugins/{name}/.claude-plugin/plugin.json"
    if not plugin_declares_playwright_dependency(plugin_data):
        found.append(
            f'{rel}: plugin "{name}" uses Playwright MCP tools but does not '
            f"declare a playwright@{PLAYWRIGHT_MARKETPLACE} dependency"
        )
    skills_root = plugin_dir / "skills"
    if skills_root.is_dir():
        for skill_md in sorted(skills_root.rglob("SKILL.md")):
            if not skill_md.is_file():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            if PLAYWRIGHT_MCP_MARKER not in text:
                continue
            if PLAYWRIGHT_INSTALL_COMMAND not in text:
                found.append(
                    f'{_rel(root, skill_md)}: uses Playwright MCP tools but does '
                    f'not mention "{PLAYWRIGHT_INSTALL_COMMAND}"'
                )
    return found


def _dependency_marketplaces(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for _name, marketplace in _iter_dependency_refs(data.get("dependencies")):
        if marketplace:
            names.add(marketplace)
    return names


def _iter_dependency_refs(raw: Any) -> list[tuple[str, str | None]]:
    if not isinstance(raw, list):
        return []
    found: list[tuple[str, str | None]] = []
    for item in raw:
        parsed = _parse_dependency_ref(item)
        if parsed is not None:
            found.append(parsed)
    return found


def _parse_dependency_ref(item: Any) -> tuple[str, str | None] | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        version_at = text.find("@^")
        if version_at != -1:
            text = text[:version_at]
        if "@" in text:
            name, marketplace = text.split("@", 1)
            if name and marketplace:
                return name, marketplace
            return None
        return text, None
    if isinstance(item, dict):
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        marketplace = item.get("marketplace")
        mp = marketplace.strip() if isinstance(marketplace, str) else None
        return name.strip(), mp or None
    return None


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
