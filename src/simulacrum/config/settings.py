"""
Central, eagerly-validated resource configuration.

Hard rule (Palimpsest bug #1 / finding 001, transplanted per §00b):
NO function anywhere in this codebase that opens a connection to a
shared resource may have a default URL/credential. Ever.

groq_api_key is the ONE deliberate exception to "no default, ever" —
it's optional by design (§20: explanation layer is optional, fails
open to a deterministic template with NO api key at all, not just on
API failure). Its absence is a valid, expected configuration, not a
misconfiguration — this is why it's Optional[str] with a None default,
unlike redis_url which has no default because its absence IS always
a misconfiguration.
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


def _optional_env(var_name: str) -> str | None:
    value = os.environ.get(var_name)
    if value is None or value.strip() == "":
        return None
    return value


@dataclass(frozen=True)
class Settings:
    redis_url: str
    groq_api_key: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        redis_url=_require_env("SIMULACRUM_REDIS_URL"),
        groq_api_key=_optional_env("GROQ_API_KEY"),
    )
