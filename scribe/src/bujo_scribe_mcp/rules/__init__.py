"""Rules layer — BuJo methodology and per-backend formatting, loaded from YAML.

The rules are the scribe's source of truth for signifiers, classification, run
order, carry-forward, naming conventions, and backend-specific rendering
details. Defaults ship with the package; users override via a YAML file whose
path is resolved from `Config.user_rules_path`.

Deep-merge semantics: user keys override defaults at any depth; lists replace
entirely (no list-element merging — simpler and more predictable).
"""

from __future__ import annotations

from bujo_scribe_mcp.rules.loader import DEFAULT_RULES_PATH, load_rules
from bujo_scribe_mcp.rules.schema import Rules

__all__ = ["Rules", "load_rules", "DEFAULT_RULES_PATH"]
