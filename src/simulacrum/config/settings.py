"""
Central, eagerly-validated resource configuration.

Hard rule (Palimpsest bug #1 / finding 001, transplanted per §00b):
NO function anywhere in this codebase that opens a connection to a shared
resource may have a default URL/credential. Ever. This module enforces the
loud, fail-fast half of that rule — validation happens once, at first
import, not silently deferred to whichever code path happens to touch
Redis first.

Scope is deliberately narrow: only resource connection settings live here.
This is not a dumping ground for every config value in the project.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


class MissingConfigError(RuntimeError):
    """Raised when a required resource setting is absent or empty."""


def _require_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if value is None or value.strip() == "":
        raise MissingConfigError(
            f"Required environment variable '{var_name}' is not set. "
            f"Simulacrum never defaults resource URLs/credentials — "
            f"set '{var_name}' explicitly before starting the process."
        )
    return value


@dataclass(frozen=True)
class Settings:
    redis_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Build and cache Settings once. Raises MissingConfigError immediately
    if any required resource setting is missing — called explicitly by
    entrypoints (API startup, CLI, test fixtures), not implicitly on
    module import, so importing this module never has a hidden env
    dependency on its own.
    """
    return Settings(
        redis_url=_require_env("SIMULACRUM_REDIS_URL"),
    )
