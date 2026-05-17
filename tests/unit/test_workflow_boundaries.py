"""Structural tests that verify layer boundaries without running code.

These tests inspect source code to catch accidental boundary violations — e.g.
a workflow reaching into the AI layer directly, or a template workflow growing
a database dependency it should not have.
"""
import inspect


# ---------------------------------------------------------------------------
# inbound_message_workflow
# ---------------------------------------------------------------------------

def test_inbound_workflow_has_no_anthropic_import():
    from app.workflows import inbound_message_workflow
    source = inspect.getsource(inbound_message_workflow)
    assert "anthropic" not in source, "Workflow layer must not import the AI SDK directly"


def test_inbound_workflow_has_no_direct_sqlalchemy_calls():
    from app.workflows import inbound_message_workflow
    source = inspect.getsource(inbound_message_workflow)
    assert "select(" not in source, "Workflows must call services, not SQLAlchemy directly"
    assert "db.execute" not in source
    assert "db.add(" not in source


# ---------------------------------------------------------------------------
# clarification_workflow — no AI, no DB
# ---------------------------------------------------------------------------

def test_clarification_workflow_has_no_anthropic_import():
    from app.workflows import clarification_workflow
    source = inspect.getsource(clarification_workflow)
    assert "anthropic" not in source


def test_clarification_workflow_has_no_sqlalchemy_import():
    from app.workflows import clarification_workflow
    source = inspect.getsource(clarification_workflow)
    assert "sqlalchemy" not in source
    assert "AsyncSession" not in source


# ---------------------------------------------------------------------------
# out_of_scope_workflow — no AI, no DB
# ---------------------------------------------------------------------------

def test_out_of_scope_workflow_has_no_anthropic_import():
    from app.workflows import out_of_scope_workflow
    source = inspect.getsource(out_of_scope_workflow)
    assert "anthropic" not in source


def test_out_of_scope_workflow_has_no_sqlalchemy_import():
    from app.workflows import out_of_scope_workflow
    source = inspect.getsource(out_of_scope_workflow)
    assert "sqlalchemy" not in source
    assert "AsyncSession" not in source


# ---------------------------------------------------------------------------
# escalation_workflow — no AI
# ---------------------------------------------------------------------------

def test_escalation_workflow_has_no_anthropic_import():
    from app.workflows import escalation_workflow
    source = inspect.getsource(escalation_workflow)
    assert "anthropic" not in source


def test_escalation_workflow_calls_service_not_db_directly():
    from app.workflows import escalation_workflow
    source = inspect.getsource(escalation_workflow)
    assert "db.execute" not in source
    assert "db.add(" not in source
    assert "select(" not in source
