"""
Parameter schema conformance detector (§09 per-call tier, §14: "exact
feature attribution where the detector is explicit — no approximation
needed"). Pure structural validation, no ML, no calibration corpus.

Returns a structured SchemaViolation, never raises on a violation —
a violation is a detection RESULT to be scored/acted on by the tier
engine, not an exceptional program state.
"""
from __future__ import annotations

from dataclasses import dataclass


class UnregisteredSchemaError(RuntimeError):
    """Raised when checking a tool with no registered schema — this
    IS a configuration error, distinct from a violation finding."""


@dataclass(frozen=True)
class ToolSchema:
    tool_name: str
    required_params: frozenset[str]
    optional_params: frozenset[str] = frozenset()

    @property
    def allowed_params(self) -> frozenset[str]:
        return self.required_params | self.optional_params


@dataclass(frozen=True)
class SchemaViolation:
    tool_name: str
    missing_params: frozenset[str]
    unexpected_params: frozenset[str]

    @property
    def is_violation(self) -> bool:
        return bool(self.missing_params or self.unexpected_params)


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, ToolSchema] = {}

    def register(self, *, schema: ToolSchema) -> None:
        self._schemas[schema.tool_name] = schema

    def get(self, *, tool_name: str) -> ToolSchema:
        try:
            return self._schemas[tool_name]
        except KeyError:
            raise UnregisteredSchemaError(
                f"No schema registered for tool '{tool_name}' — cannot "
                f"check conformance. Register a ToolSchema before "
                f"calling check_schema()."
            ) from None


def check_schema(
    *, registry: SchemaRegistry, tool_name: str, params: dict[str, str]
) -> SchemaViolation:
    schema = registry.get(tool_name=tool_name)
    provided = frozenset(params.keys())
    missing = schema.required_params - provided
    unexpected = provided - schema.allowed_params
    return SchemaViolation(
        tool_name=tool_name, missing_params=missing, unexpected_params=unexpected
    )


def build_default_schema_registry() -> SchemaRegistry:
    """
    Schemas for the default stub tool set, matching task_sim's actual
    param generators exactly — same vocabulary-consistency discipline
    as FakeToolRegistry.
    """
    registry = SchemaRegistry()
    registry.register(
        schema=ToolSchema(tool_name="read_inbox", required_params=frozenset({"count"}))
    )
    registry.register(
        schema=ToolSchema(
            tool_name="reply_to_email",
            required_params=frozenset({"email_id", "body"}),
        )
    )
    registry.register(
        schema=ToolSchema(
            tool_name="search_flights",
            required_params=frozenset({"origin", "destination"}),
        )
    )
    registry.register(
        schema=ToolSchema(tool_name="book_flight", required_params=frozenset({"flight_id"}))
    )
    registry.register(
        schema=ToolSchema(tool_name="get_calendar", required_params=frozenset({"date"}))
    )
    registry.register(
        schema=ToolSchema(
            tool_name="add_calendar_event", required_params=frozenset({"title"})
        )
    )
    registry.register(
        schema=ToolSchema(tool_name="list_files", required_params=frozenset({"query"}))
    )
    registry.register(
        schema=ToolSchema(
            tool_name="share_file", required_params=frozenset({"file_id", "recipient"})
        )
    )
    registry.register(
        schema=ToolSchema(tool_name="search_contacts", required_params=frozenset({"name"}))
    )
    registry.register(
        schema=ToolSchema(
            tool_name="update_contact", required_params=frozenset({"contact_id", "field"})
        )
    )
    return registry
