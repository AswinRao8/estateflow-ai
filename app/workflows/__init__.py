# Orchestration layer.
# Sequences service calls to execute multi-step operational flows.
# No business logic. No database access. No prompt construction.
# Each workflow is a stateless function that reads from and writes to
# persistent storage via services.
#
# Modules added here in Phase 4+:
#   inbound_router.py         — routes by intent + lead state to a workflow
#   qualification_workflow.py
#   listing_inquiry_workflow.py
#   viewing_workflow.py
#   handoff_workflow.py
#   followup_workflow.py
