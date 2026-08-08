"""
Verifies sensitive-parameter redaction (§19, day-one requirement).
Tested against a REAL example of the actual exposure this closes: an
LLM reasoning string of the exact shape our real GroqContentPatternDetector
has produced this session, quoting back real-looking sensitive content.
"""
from simulacrum.redaction.redactor import redact_params, redact_text


def test_redacts_email_address():
    text = "Please send this to john.smith@company.com right away."
    result = redact_text(text=text)
    assert "john.smith@company.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_redacts_ssn():
    text = "The record shows SSN 123-45-6789 for this customer."
    result = redact_text(text=text)
    assert "123-45-6789" not in result
    assert "[REDACTED_SSN]" in result


def test_redacts_credit_card():
    text = "Card number 4532 0151 1283 0366 was used for this transaction."
    result = redact_text(text=text)
    assert "4532 0151 1283 0366" not in result
    assert "[REDACTED_CARD]" in result


def test_redacts_credential_keyword_content():
    text = "The password: hunter2xyz was found in the message."
    result = redact_text(text=text)
    assert "hunter2xyz" not in result
    assert "[REDACTED_CREDENTIAL]" in result


def test_real_shaped_llm_reasoning_string():
    """
    Real, honest reproduction of the actual exposure: an LLM
    reasoning string of the SAME shape as real GroqContentPatternDetector
    output this session (docs/findings/007-*.md), which naturally
    quotes back the sensitive content it's analyzing.
    """
    real_shaped_reasoning = (
        "The parameter 'body' contains a message that explicitly mentions "
        "attaching a customer database export including contact "
        "jane.doe@company.com and SSN 987-65-4321, which is a clear "
        "indicator of bulk personal data being transferred."
    )
    result = redact_text(text=real_shaped_reasoning)
    assert "jane.doe@company.com" not in result
    assert "987-65-4321" not in result
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_SSN]" in result
    # The real analytical content (non-sensitive) should survive intact
    assert "customer database export" in result
    assert "bulk personal data" in result


def test_redact_params_handles_dict():
    params = {"email_id": "42", "body": "Contact me at test@example.com"}
    result = redact_params(params=params)
    assert result["email_id"] == "42"  # non-sensitive value untouched
    assert "test@example.com" not in result["body"]


def test_non_sensitive_text_passes_through_unchanged():
    text = "This is a completely normal, non-sensitive message."
    assert redact_text(text=text) == text
