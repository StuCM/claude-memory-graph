"""Extension discovery and the enabled-set.

Discovery: Python entry points in the `claude_hook_kit` group — any installed
package can provide extensions:

    [project.entry-points."claude_hook_kit"]
    my-extension = "my_package.hooks:MyExtension"

Enablement: discovered ≠ running. The enabled list lives in
<state-home>/config.json and is edited via `claude-hooks enable/disable`
(surfaced to users as the /hook-kit:install skill). The dispatcher runs only
extensions that are both discovered and enabled.
"""

import json
from importlib.metadata import entry_points

from .extension import HookExtension
from .state import state_home, _read_json, _write_json


def discover() -> dict[str, type[HookExtension]]:
    found: dict[str, type[HookExtension]] = {}
    for ep in entry_points(group="claude_hook_kit"):
        try:
            cls = ep.load()
        except Exception:
            continue  # a broken extension package must not break dispatch
        if isinstance(cls, type) and issubclass(cls, HookExtension):
            found[ep.name] = cls
    return found


def _config_path():
    return state_home() / "config.json"


def enabled_names(available: dict[str, type[HookExtension]] | None = None) -> list[str]:
    """The extensions that should run. The user's explicit config wins; with
    no config yet, extensions marked enabled_by_default run out of the box
    (so installing memory-graph gives a working gate with zero setup)."""
    config = _read_json(_config_path())
    if "enabled" in config:
        return list(config["enabled"])
    if available is None:
        available = discover()
    return sorted(n for n, cls in available.items() if cls.enabled_by_default)


def set_enabled(names: list[str]) -> None:
    config = _read_json(_config_path())
    config["enabled"] = sorted(set(names))
    _write_json(_config_path(), config)


def enable(name: str) -> str:
    available = discover()
    if name not in available:
        known = ", ".join(sorted(available)) or "none discovered"
        return f"Unknown extension '{name}'. Discovered: {known}"
    names = enabled_names(available)
    if name in names:
        return f"'{name}' already enabled"
    set_enabled([*names, name])
    return f"Enabled '{name}'"


def disable(name: str) -> str:
    available = discover()
    names = enabled_names(available)
    if name not in names:
        return f"'{name}' is not enabled"
    set_enabled([n for n in names if n != name])
    return f"Disabled '{name}'"


def status() -> str:
    available = discover()
    enabled = set(enabled_names(available))
    if not available and not enabled:
        return "No extensions discovered."
    lines = []
    for name in sorted(set(available) | enabled):
        mark = "enabled" if name in enabled else "disabled"
        missing = "" if name in available else " (enabled but not installed)"
        doc = (available[name].__doc__ or "").strip().splitlines()
        desc = f" — {doc[0]}" if name in available and doc else ""
        lines.append(f"  {name} [{mark}]{missing}{desc}")
    return "Hook extensions:\n" + "\n".join(lines)
