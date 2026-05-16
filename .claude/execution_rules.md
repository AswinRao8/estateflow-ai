# EstateFlow AI — Execution Rules

## Implementation Discipline

Every implementation decision must serve a specific, current requirement.

Rules:
- Implement what is needed now. Do not implement what might be needed later.
- If a feature is not in the V1 scope document, it does not exist until explicitly added.
- Every new module must have a clear, single responsibility that can be stated in one sentence.
- No module should be added unless removing it would break a specific workflow.
- When in doubt, write less code. Complexity is a liability, not a feature.

Before writing any new module, the implementer must be able to answer:
1. What specific workflow does this serve?
2. What breaks if this does not exist?
3. Where exactly does this fit in the system architecture?

If any of these answers are vague, the implementation should be paused and clarified.

## Module Types and Responsibilities

**Current MVP layers:**
- `routers/` — HTTP endpoint definitions only. Validates input, calls a service or workflow, returns a response. Three things exactly.
- `services/` — Business logic, direct database access (SQLAlchemy), and AI calls (Anthropic SDK). Returns domain objects.
- `workflows/` — Orchestration of service calls in defined sequences. Stateless. No database or AI access directly.
- `models/` — SQLAlchemy ORM models, Pydantic schemas, domain enums. No logic beyond field validation.
- `utils/` — Pure functions with no side effects and no imports from any other app module.

**Not present at MVP (extraction-triggered):**
- `repositories/` — Added when query complexity or reuse across services justifies it. See extraction triggers in `architecture.md`.
- `app/ai/` — Added when AI call patterns repeat across 2+ services or a service exceeds ~150 lines of AI-specific code. Named `ai/` not `agents/` — "agents" implies autonomous chaining, which this platform does not use.

## Cross-Boundary Rules

- **Routers call services or workflows only.** A router function that contains a database query or an AI call is an architecture violation.
- **Services own their data access.** A service calls SQLAlchemy directly. There is no mandatory intermediate layer.
- **Services own their AI calls.** A service calls the Anthropic SDK directly for the AI operations it needs.
- **Workflows call services only.** A workflow that calls SQLAlchemy or the Anthropic SDK directly is an architecture violation — it must go through a service.
- **Services do not call each other across domain boundaries.** If `lead_service` needs listing data, the calling workflow or router provides it — `lead_service` does not import `listing_service`.
- **Utils have no project imports.** A utility function that imports from `app.services` or `app.models` is not a utility — it belongs in the layer it serves.

## Dependency Restrictions

**Allowed core dependencies:**
- `fastapi` — HTTP routing and request handling
- `pydantic` — Data validation and schema definition
- `pydantic-settings` — Settings management
- `sqlalchemy` — Database ORM (async)
- `anthropic` — LLM API client (called directly — no wrappers)
- `httpx` — Async HTTP client for external API calls
- `alembic` — Database schema migrations
- `pytest` — Testing framework
- `httpx` — TestClient and async HTTP in tests

**Deferred dependencies (added when the phase requires them):**
- `redis` — Session cache, added in Phase 3
- `celery` — Background task scheduling, added in Phase 9

**Explicitly prohibited dependencies:**
- `langchain` or `langchain_*` — Wraps the LLM API behind abstractions that obscure routing, break testability, and add unstable transitive dependencies
- `llamaindex` — NLP pipeline framework not suited to this architecture
- `chromadb`, `weaviate`, `pinecone` — Vector databases; listing matching is a SQL problem at MVP
- `autogen`, `crewai`, `agentops` — Multi-agent frameworks; this platform uses deterministic routing, not autonomous agents
- `haystack` — Unnecessary indirection over the Anthropic SDK
- Any package whose primary function is to wrap an LLM API call

**Dependency evaluation criteria:**
1. Does it solve a problem that cannot be solved with existing dependencies?
2. Does it remove more complexity than it adds?
3. Can it be removed later without significant refactoring?

If a dependency fails any of these, do not add it.

## Naming Conventions

**Files:**
- Services: `{domain}_service.py`
- Routers: `{domain}_router.py`
- Workflows: `{domain}_workflow.py`
- Domain models: `{domain}.py` inside `models/` — contains both the SQLAlchemy ORM class
  and the Pydantic DTOs for that domain (e.g. `models/lead.py` holds `Lead` ORM +
  `LeadCreate`/`LeadRead` Pydantic models). Do not split these across separate files
  until the file exceeds ~150 lines.
- Tests: `test_{module_name}.py`

**Functions:**
- Services: verb-first, domain-specific (`qualify_lead`, `advance_lifecycle_state`, `build_context`)
- Routers: REST-style (`list_leads`, `get_lead`, `update_lead_state`)
- Workflows: process-oriented (`run_qualification_flow`, `execute_handoff`, `process_inbound_message`)
- Private service helpers: prefixed with underscore (`_build_system_prompt`, `_parse_intent_response`)

**Constants and enums:**
- Lead lifecycle states, intent types, property types: defined as `StrEnum` in `models/enums.py`
- Configuration keys: `SCREAMING_SNAKE_CASE` in `.env` and `config.py`
- Internal variables: `snake_case`

**Database tables:**
- Entity tables: `{domain}s` (e.g., `leads`, `listings`, `sessions`)
- Join tables: `{domain_a}_{domain_b}` (e.g., `lead_listings`)

## Architecture Enforcement Rules

1. **No business logic in routers.** A router function does three things: validates input, calls a service or workflow, returns a response. Any conditional logic, domain rule, or data transformation that appears in a router belongs in a service.

2. **No environment variables accessed outside `config.py`.** Reading `os.environ` or `os.getenv` anywhere except `config.py` is an architecture violation.

3. **No hardcoded strings for domain constants.** Lead states, intent types, property types, and handoff reasons must be imported from `models/enums.py`. No inline string literals that control behavior.

4. **No circular imports.** If module A imports module B and B imports A, resolve it by extracting shared types to `models/`. Circular imports are a sign that a boundary is wrong.

5. **Migrations only through Alembic.** Never modify a schema by writing `ALTER TABLE` in application code or editing the database directly.

6. **No unbounded list queries.** Every function that retrieves a collection must accept pagination parameters. No `SELECT * FROM leads` without `LIMIT`.

7. **`tenant_id` on all persistent records.** Lead, listing, session, conversation, and agent records all carry a `tenant_id` field. Even in V1 single-tenant mode.

## Code Organization

```
app/
  routers/          # HTTP route handlers — one file per domain
  services/         # Business logic + DB access (SQLAlchemy) + AI calls (Anthropic SDK)
  workflows/        # Multi-step orchestration sequences
  models/
    base.py         #   APIResponse[T], ErrorResponse — Pydantic envelopes for all routers
    enums.py        #   All domain StrEnums
    {domain}.py     #   ORM model + Pydantic DTOs per domain (Phase 1+)
  utils/            # Pure utility functions
  database.py       # Engine, SessionFactory, Base, TimestampMixin, DB health check
  dependencies.py   # SettingsDep, DbSessionDep — FastAPI Depends() aliases
  config.py         # Settings (pydantic-settings, single source)
  main.py           # Application factory, router registration, exception handlers

tests/
  unit/             # Pure function and service logic tests
  integration/      # Service tests against a real test database
  e2e/              # Full end-to-end workflow tests

migrations/         # Alembic migration files (env.py, script.py.mako, versions/)
```

**Directories that do not exist and must not be created speculatively:**
- `schemas/` — redundant with `models/`; Pydantic DTOs belong in their domain's model file
- `core/` — undefined responsibility; no code belongs here that lacks a proper named home
- `integrations/` — created as `app/integrations/whatsapp/` when Phase 2 begins, not before
- `repositories/` — extraction target; see extraction triggers in `architecture.md`
- `agents/` or `ai/` — extraction target; see extraction triggers in `architecture.md`

## Testing Philosophy

Tests exist to verify behavior, not to prove the code was written.

**Unit tests:**
- Test pure functions (utils, enum logic, schema validation) in isolation
- No mocking of internal modules — if a function requires mocking its dependencies, it has too many
- Fast, deterministic, no I/O

**Integration tests:**
- Test service functions with a real test database
- No mocking of SQLAlchemy — the query IS the logic being tested
- Verify lifecycle state transitions enforce valid paths and reject invalid ones
- Verify that workflow sequences produce the correct state outcomes

**AI call tests:**
- Test prompt-building helpers (the `_build_system_prompt` private functions) with fixed inputs
- Test response parsing logic against fixed mock API responses
- Never make live Anthropic API calls in the automated test suite

**What is not tested:**
- FastAPI routing internals
- SQLAlchemy ORM behavior
- Pydantic validation behavior
- LLM output quality or conversational coherence

**Coverage expectations:**
- All lifecycle state transition logic: 100%
- All service functions with branching logic: 100%
- All prompt-building helpers: 100%
- All response-parsing helpers: 100%
- Happy-path workflows: covered via integration tests

## Anti-Spaghetti Constraints

1. **No function longer than 40 lines.** If a function exceeds 40 lines, it is doing more than one thing. Extract helpers.

2. **No module longer than 200 lines.** If a module exceeds 200 lines, it has more than one responsibility. Split it. This limit is a signal, not a guarantee — a 180-line module with poor cohesion still needs splitting.

3. **No more than 3 levels of nesting.** Flatten with early returns and extracted helpers.

4. **No commented-out code committed.** Delete it. Git history preserves it.

5. **No TODO comments without a tracked issue reference.** A TODO with no issue number will never be addressed. Either fix it now or create a ticket.

6. **No feature flags in V1.** Code either runs or it does not.

7. **No god services.** A service that imports from 6+ other services is a monolith in disguise. Decompose it, or introduce a workflow to own the orchestration.

8. **No magic strings.** Any string that controls branching behavior must be a named constant imported from `models/enums.py`.
