"""Rules loader — reads default YAML, merges user override, validates.

Invariants:
- Default rules always load successfully and round-trip through the schema.
- User overrides merge deeply; lists replace entirely.
- Validation errors raise `RulesLoadError` with a path into the failing field.
- The function is side-effect free — pass in paths, get back a `Rules` instance.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bujo_scribe_mcp.rules.schema import Rules

DEFAULT_RULES_PATH = Path(str(files("bujo_scribe_mcp.rules").joinpath("default.yaml")))


class RulesLoadError(Exception):
    """Raised when rules cannot be loaded or validated."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge `override` on top of `base`.

    Dict values merge recursively. Non-dict values (scalars, lists) replace.
    Returns a new dict; inputs are not mutated.
    """
    result: dict[str, Any] = {}
    for key, base_value in base.items():
        if key in override:
            override_value = override[key]
            if isinstance(base_value, dict) and isinstance(override_value, dict):
                result[key] = _deep_merge(base_value, override_value)
            else:
                result[key] = override_value
        else:
            result[key] = base_value
    for key, override_value in override.items():
        if key not in base:
            result[key] = override_value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise RulesLoadError(f"Rules file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise RulesLoadError(f"YAML parse error in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RulesLoadError(f"Rules file {path} must contain a mapping at the top level.")
    return data


def load_rules(
    *,
    default_path: Path = DEFAULT_RULES_PATH,
    user_path: Path | None = None,
) -> Rules:
    """Load rules from YAML, optionally merging a user override.

    Args:
        default_path: Path to the shipped default rules. Rarely overridden
            outside tests.
        user_path: Optional path to a user override YAML. If provided and the
            file exists, its keys merge on top of the defaults. If the path
            is provided but the file doesn't exist, that's an error — absence
            should be signalled by `user_path=None`.

    Returns:
        A validated `Rules` instance.

    Raises:
        RulesLoadError: on file-not-found, YAML parse error, or schema
            validation failure.
    """
    merged = _load_yaml(default_path)
    if user_path is not None:
        overrides = _load_yaml(user_path)
        merged = _deep_merge(merged, overrides)

    try:
        return Rules.model_validate(merged)
    except ValidationError as exc:
        raise RulesLoadError(f"Rules failed validation:\n{exc}") from exc
