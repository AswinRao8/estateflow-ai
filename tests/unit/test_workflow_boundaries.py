"""Structural tests that verify layer boundaries without running code."""
import inspect


def test_inbound_workflow_has_no_anthropic_import():
    from app.workflows import inbound_message_workflow
    source = inspect.getsource(inbound_message_workflow)
    assert "anthropic" not in source, "Phase 3 workflow must not reach the AI layer"


def test_inbound_workflow_has_no_direct_sqlalchemy_calls():
    from app.workflows import inbound_message_workflow
    source = inspect.getsource(inbound_message_workflow)
    # Workflows call services, not SQLAlchemy directly
    assert "select(" not in source
    assert "db.execute" not in source
    assert "db.add(" not in source
