"""
Verbalizes a tool call's params into descriptive text for embedding
comparison against the task representation. Real param-vs-task
divergence scoring needs a NATURAL-LANGUAGE description of what a call
is doing, not raw param key/value pairs — comparing {origin: JFK}
against "book a flight to London" embeds nothing meaningful under any
embedder, fake or real. This is a genuine design piece of the
divergence detector, not a test-only shim.
"""
from __future__ import annotations

_CALL_TEMPLATES: dict[str, str] = {
    "read_inbox": "read inbox check emails count {count}",
    "reply_to_email": "reply to email {email_id} regarding {body}",
    "search_flights": "search for flight from {origin} to {destination}",
    "book_flight": "book flight {flight_id}",
}


def call_topic_text(*, tool_name: str, params: dict[str, str]) -> str:
    """
    Falls back to a generic 'tool_name key value key value...' text
    for tools with no registered template, so an unknown/unexpected
    tool still gets SOME text to embed rather than raising.
    """
    template = _CALL_TEMPLATES.get(tool_name)
    if template is None:
        parts = [tool_name] + [f"{k} {v}" for k, v in params.items()]
        return " ".join(parts)
    try:
        return template.format(**params)
    except KeyError:
        # missing param for the template — fall back to generic text
        # rather than raising; schema conformance is a SEPARATE
        # detector's job, this one should degrade gracefully.
        parts = [tool_name] + [f"{k} {v}" for k, v in params.items()]
        return " ".join(parts)
