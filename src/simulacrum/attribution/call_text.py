"""
Verbalizes a tool call's params into descriptive text for embedding
comparison against the task representation. Real param-vs-task
divergence scoring needs a NATURAL-LANGUAGE description of what a call
is doing, not raw param key/value pairs.
"""
from __future__ import annotations

_CALL_TEMPLATES: dict[str, str] = {
    "read_inbox": "read inbox check emails count {count}",
    "reply_to_email": "reply to email {email_id} regarding {body}",
    "search_flights": "search for flight from {origin} to {destination}",
    "book_flight": "book flight {flight_id}",
    "get_calendar": "check calendar for date {date}",
    "add_calendar_event": "add calendar event {title}",
    # File-sharing / contact-update task types (toward §08's 5-8
    # target) -- dedicated templates sharing real vocabulary with
    # their task's initiating text (finding 005's lesson: fallback
    # generic text is more collision-prone under the fake embedder).
    "list_files": "find the document {query} to share",
    "share_file": "share document file {file_id} with team recipient {recipient}",
    "search_contacts": "look up find contact information name {name}",
    "update_contact": "update contact information {field} for {contact_id}",
    # Attack-target tools (§04/§07) — dedicated templates so none of
    # these fall back to the generic "tool_name key value..." format,
    # which is more collision-prone under the fake embedder (finding
    # 005: raw param values leaking unfiltered into embedded text
    # increased accidental bucket overlap with unrelated task text).
    "send_payment": "send payment transfer money amount {amount} to {recipient}",
    "set_forwarding_rule": "forward all email messages to external address {target}",
    "delete_data": "delete remove destroy data files {target}",
    "modify_permissions": "modify change grant elevate access permissions for {user} to {level}",
}


def call_topic_text(*, tool_name: str, params: dict[str, str]) -> str:
    template = _CALL_TEMPLATES.get(tool_name)
    if template is None:
        parts = [tool_name] + [f"{k} {v}" for k, v in params.items()]
        return " ".join(parts)
    try:
        return template.format(**params)
    except KeyError:
        parts = [tool_name] + [f"{k} {v}" for k, v in params.items()]
        return " ".join(parts)
