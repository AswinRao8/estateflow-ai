import pytest

from app.models.enums import LeadState
from app.models.lead import VALID_LEAD_TRANSITIONS


def _all_states() -> list[LeadState]:
    return list(LeadState)


def test_every_state_has_an_entry_in_transitions():
    for state in _all_states():
        assert state in VALID_LEAD_TRANSITIONS, f"{state} missing from VALID_LEAD_TRANSITIONS"


def test_closed_won_is_terminal():
    assert VALID_LEAD_TRANSITIONS[LeadState.CLOSED_WON] == frozenset()


def test_closed_lost_only_allows_re_engagement():
    assert VALID_LEAD_TRANSITIONS[LeadState.CLOSED_LOST] == frozenset({LeadState.NEW_INQUIRY})


def test_new_inquiry_valid_transitions():
    allowed = VALID_LEAD_TRANSITIONS[LeadState.NEW_INQUIRY]
    assert LeadState.CONTEXT_IDENTIFIED in allowed
    assert LeadState.QUALIFYING in allowed
    assert LeadState.HUMAN_ACTIVE in allowed
    assert LeadState.CLOSED_LOST in allowed       # immediate opt-out is valid
    assert LeadState.VIEWING_SCHEDULED in allowed  # direct booking on first contact
    # CLOSED_WON (sale) must not be reachable from first contact
    assert LeadState.CLOSED_WON not in allowed


def test_human_active_can_reach_all_non_terminal_non_new_states():
    allowed = VALID_LEAD_TRANSITIONS[LeadState.HUMAN_ACTIVE]
    # HUMAN_ACTIVE should be able to move to any operational state
    for state in (
        LeadState.QUALIFYING,
        LeadState.MATCHING_PROPERTIES,
        LeadState.VIEWING_INTEREST,
        LeadState.VIEWING_SCHEDULED,
        LeadState.POST_VIEWING,
        LeadState.NEGOTIATION,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_WON,
        LeadState.CLOSED_LOST,
    ):
        assert state in allowed, f"HUMAN_ACTIVE should allow transition to {state}"


def test_human_active_cannot_transition_to_new_inquiry():
    # NEW_INQUIRY is only reachable via CLOSED_LOST re-engagement
    assert LeadState.NEW_INQUIRY not in VALID_LEAD_TRANSITIONS[LeadState.HUMAN_ACTIVE]


def test_negotiation_can_close():
    allowed = VALID_LEAD_TRANSITIONS[LeadState.NEGOTIATION]
    assert LeadState.CLOSED_WON in allowed
    assert LeadState.CLOSED_LOST in allowed


def test_no_transition_targets_undefined_state():
    valid = set(_all_states())
    for from_state, targets in VALID_LEAD_TRANSITIONS.items():
        for target in targets:
            assert target in valid, f"Unknown target state {target!r} from {from_state!r}"


@pytest.mark.parametrize("state", [
    LeadState.QUALIFYING,
    LeadState.MATCHING_PROPERTIES,
    LeadState.VIEWING_INTEREST,
    LeadState.VIEWING_SCHEDULED,
    LeadState.POST_VIEWING,
    LeadState.NEGOTIATION,
    LeadState.FOLLOW_UP,
])
def test_operational_states_include_human_active_escape(state):
    assert LeadState.HUMAN_ACTIVE in VALID_LEAD_TRANSITIONS[state]


def test_follow_up_cannot_reach_closed_won_directly():
    # FOLLOW_UP leads to re-qualification, not directly to a close
    assert LeadState.CLOSED_WON not in VALID_LEAD_TRANSITIONS[LeadState.FOLLOW_UP]
