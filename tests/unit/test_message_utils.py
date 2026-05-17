import pytest

from app.utils.message import is_agent_request


# ---------------------------------------------------------------------------
# Explicit agent / human-request signals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "I want to speak to a human",
    "Can I talk to an agent please?",
    "connect me with a real person",
    "I need to speak to someone from the office",
    "Not a bot — I want a real agent",
    "Please call me",
    "I'm not a bot, I want a real agent",
    "Is there a real person I can speak to?",
    "HUMAN PLEASE",
    "just talk to a person",
])
def test_is_agent_request_matches_explicit_requests(body):
    assert is_agent_request(body) is True


# ---------------------------------------------------------------------------
# Normal property-related messages that must not trigger escalation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "I'm interested in the villa",
    "What is the asking price?",
    "Can I schedule a viewing for Saturday?",
    "Tell me more about the apartment",
    "How many bedrooms does it have?",
    "Is this property still available?",
    "I want to buy this place",
    "What floor is the penthouse on?",
])
def test_is_agent_request_ignores_property_messages(body):
    assert is_agent_request(body) is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_is_agent_request_empty_string_is_false():
    assert is_agent_request("") is False


def test_is_agent_request_is_case_insensitive():
    assert is_agent_request("AGENT please") is True
    assert is_agent_request("Human support") is True


def test_is_agent_request_partial_word_does_not_match():
    # "humanity" contains "human" but is not an agent request.
    # The pattern uses \b word boundary so "humanity" should not match.
    assert is_agent_request("The humanity of this design is inspiring") is False


def test_is_agent_request_multiword_phrase():
    assert is_agent_request("I would like to speak to a real person today") is True
