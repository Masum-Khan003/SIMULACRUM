"""
Central, eagerly-validated resource configuration.

Hard rule (Palimpsest bug #1 / finding 001, transplanted per §00b):
NO function anywhere in this codebase that opens a connection to a
shared resource may have a default URL/credential. Ever.

groq_api_key and hf_token are the DELIBERATE exceptions to "no default,
ever" -- both are optional by design: groq_api_key because the
explanation layer fails open to a deterministic template with no key
at all (§20); hf_token because MiniLM downloads work fine
unauthenticated (just at lower rate limits), so its absence is valid,
expected configuration, not a misconfiguration -- unlike redis_url,
whose absence is always a misconfiguration.
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
    hf_token: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        redis_url=_require_env("SIMULACRUM_REDIS_URL"),
        groq_api_key=_optional_env("GROQ_API_KEY"),
        hf_token=_optional_env("HF_TOKEN"),
    )
