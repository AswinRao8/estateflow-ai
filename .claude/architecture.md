# EstateFlow AI — Architecture

## Folder Structure

```
app/
├── routers/      HTTP boundary. Validates inbound requests, delegates to
│                 services or workflows, returns responses. No business logic.
│
├── services/     Business logic layer. Owns domain operations, database access
│                 (direct SQLAlchemy), and AI calls (direct Anthropic SDK).
│                 Returns domain objects. Never returns HTTP responses.
│
├── workflows/    Orchestration layer. Sequences service calls across domain
│                 boundaries to execute multi-step operational flows.
│                 No business logic. No direct database or AI access.
│
├── models/       All data structures for the project. Three kinds of files live here:
│                   base.py    — APIResponse[T] and ErrorResponse (Pydantic envelopes
│                                used by all routers)
│                   enums.py   — All domain StrEnums (LeadState, IntentType, etc.)
│                   {domain}.py — One file per domain entity containing both the
│                                SQLAlchemy ORM model and its Pydantic DTOs
│                                (e.g. lead.py holds Lead ORM + LeadCreate/LeadRead)
│
├── integrations/  Channel-specific payload parsing. Created per channel when
│                  that channel's implementation begins. No business logic here —
│                  only translation from provider payload to internal types.
│                   whatsapp/  — WhatsApp Cloud API integration (Phase 2+)
│
├── utils/        Pure utility functions. No side effects. No imports from
│                 any other app module. String formatting, date handling,
│                 geographic normalization.
│
├── database.py   SQLAlchemy async engine, session factory, declarative Base,
│                 TimestampMixin, and DB connection check.
│
├── dependencies.py  FastAPI Annotated dependency aliases. SettingsDep, DbSessionDep.
│
├── config.py     Single source of all environment variables and settings.
│                 Includes MarketConfig — the lightweight market-awareness block.
│                 All modules read settings through here — never os.environ.
│
└── main.py       FastAPI application factory. Router registration only.
```

## Market Configuration

EstateFlow AI operates in any real estate market. Market-specific behavior is
controlled through a `MarketConfig` block inside application `Settings` — not
through code branching, parallel service implementations, or translation frameworks.

**What `MarketConfig` controls:**
- Currency code and symbol (ISO 4217 — e.g., `USD`, `EUR`, `AED`, `SGD`)
- Area measurement unit (`sqm` or `sqft`)
- Timezone (IANA — used for follow-up scheduling and display timestamps)
- Communication locale tag (e.g., `"en"`, `"fr"`, `"ar"`) — passes as a
  parameter to prompt-building helpers to adjust tone and phrasing; it is not a
  translation framework
- Property terminology overrides (optional dict) — e.g., `"apartment": "flat"`
  for UK-market deployments; used only in prompt construction

**What `MarketConfig` does not control:**
- Workflow logic — qualification, matching, handoff, and follow-up sequences
  are identical across all markets; only terminology varies, not behavior
- Lead lifecycle states — `NEW_INQUIRY → ... → CLOSED_WON` is universal
- Service interfaces — services accept typed domain objects independent of market
- Database schema — no market-specific columns; preferences live in settings
- Language selection — V1 operates in one language, set by `communication_locale`;
  full multi-language infrastructure is deferred

**Implementation location:** `MarketConfig` is a `BaseModel` nested inside
`Settings` in `app/config.py`. It is read at startup. Prompt-building helpers
in `conversation_service` accept it as a parameter. No other layer reads it
directly — the calling context (workflow or service) passes it through.

**What is intentionally absent:**
- i18n/l10n frameworks (premature — one language serves V1)
- Per-tenant market configuration (V1 is single-tenant; market is set at deployment)
- Jurisdiction compliance rule engines (legal requirements are not this platform's concern)
- Market-specific workflow variants (one workflow set serves all markets)
- MLS or property portal API integrations (deferred until a specific market demands it)

## What Is Not in This Structure

**`schemas/`** — Does not exist and must not be created. `models/` owns both ORM
models and Pydantic DTOs. Co-locating them per domain eliminates the split entirely.

**`core/`** — Does not exist and must not be created. Every piece of code that
might end up there already has a proper named home: `config.py`, `database.py`,
`dependencies.py`.

**`integrations/`** — Created as `app/integrations/whatsapp/` when Phase 2 begins.
Additional channel directories (`sms/`, `email/`) are created only when those
channels are implemented. No speculative placeholder directories.

**`localization/` or `i18n/`** — Does not exist. Market-aware behavior is handled
through `MarketConfig` parameters passed to prompt builders. A dedicated
localization layer is introduced only when multiple languages are actively served.

```
tests/
├── unit/         Fast isolated tests. No I/O. No mocking of app internals.
├── integration/  Service tests against a real test database.
└── e2e/          Full end-to-end flow tests for complete workflows.

migrations/       Alembic schema migration files.
```

## Why repositories/ Is Not Present at MVP

A repository layer is justified when:
- The same query appears in 3+ different service functions and duplication is a maintenance problem
- A query is complex enough (multi-table joins, window functions, aggregations) to deserve its own named, tested function
- You need to mock data access to unit test service logic in isolation

At MVP, none of these conditions exist. A service function that calls SQLAlchemy directly is:
- Shorter than service → repository → query
- Immediately readable — the query is where the logic is
- Trivially testable with a real test database (which is the correct test strategy anyway)

When the first condition arrives, the right first step is a `{domain}_queries.py` file inside `services/` — a named helper that consolidates query logic within the domain. Graduate to a `repositories/` layer only if that file grows beyond its domain or needs sharing across service boundaries.

## Why agents/ Is Not Present at MVP

An `agents/` (or `ai/`) extraction layer is justified when:
- 2+ services share the same prompt construction pattern
- A service file grows beyond ~150 lines primarily because of AI-specific code
- You need to test prompt construction or response parsing independently of business logic

At MVP, all AI calls will live inside the service that needs them as private helpers. When the first extraction trigger arrives, create `app/ai/` (not `agents/` — "ai" is honest about what it contains; "agents" implies autonomous chaining, which this architecture explicitly avoids).

## Why workflows/ Is Present at MVP

The inbound message pipeline is 10+ ordered steps that span session management, lead state, intent classification, listing data, AI response generation, and follow-up scheduling. This cannot live in a router (it is not HTTP logic), and it cannot live in any one service without turning that service into a god object.

Workflows are the core mechanism that makes this platform's behavior deterministic and traceable. They are justified from the first real inbound message handler.

## Service Boundaries

Each service owns one domain. Services do not own each other's data.
Services are market-agnostic — they operate on domain objects and do not branch on `MarketConfig` values.

| Service | Responsibility |
|---|---|
| `lead_service` | Lead creation, qualification state management, lifecycle transitions |
| `listing_service` | Property data retrieval, matching logic, availability checks |
| `session_service` | WhatsApp session creation, context loading, session expiry |
| `conversation_service` | Message history, context window management, intent classification, AI response generation |
| `notification_service` | Sending messages via WhatsApp API, delivery tracking |
| `handoff_service` | Human takeover initiation, agent briefing construction, continuity preservation |
| `followup_service` | Scheduling and executing follow-up workflows, re-engagement logic |

`conversation_service` owns both context management and AI calls because at MVP these are inseparable — the AI call is what the conversation service does with its context. They are extracted separately only when either grows into a distinct complexity domain.

## Router Boundaries

| Router | Path | Purpose |
|---|---|---|
| `health_router` | `/health`, `/ready` | Infrastructure health checks |
| `whatsapp_router` | `/webhook/inbound`, `/webhook/status` | WhatsApp provider events |
| `lead_router` | `/api/v1/leads`, `/api/v1/leads/{id}` | Lead management |
| `listing_router` | `/api/v1/listings`, `/api/v1/listings/{id}` | Property data |
| `agent_router` | `/api/v1/agents`, `/api/v1/agents/{id}/takeover` | Human agent operations |
| `session_router` | `/api/v1/sessions/{id}` | Session inspection |
| `admin_router` | `/api/v1/admin/config` | Platform administration |

Each router registers only its own prefix. Health and webhook routes sit outside the versioned prefix intentionally — see router registration rationale in `app/main.py`.

## Orchestration Flow

### Inbound WhatsApp Message Pipeline

```
1.  POST /webhook/inbound
    └── whatsapp_router (validates payload, extracts InboundMessage)

2.  Load or create session
    └── session_service.get_or_create(phone_number, listing_ref)

3.  Load or create lead
    └── lead_service.get_or_create(session_id)

4.  Check human takeover status
    └── lead_service.is_human_active(lead_id)
    → if yes: queue message for human agent, return early

5.  Load conversation context
    └── conversation_service.build_context(session_id, lead_id)

6.  Classify intent
    └── conversation_service.classify_intent(message, context)
    → IntentResult(intent_type, confidence, extracted_data)
    [AI call lives inside conversation_service]

7.  Route to appropriate workflow
    └── workflows.inbound_router.route(intent_result, lead, context)

8.  Workflow executes (one of):
    - qualification_workflow
    - listing_inquiry_workflow
    - viewing_workflow
    - handoff_workflow
    - followup_workflow

9.  Generate AI response
    └── conversation_service.generate_response(context, workflow_output, market_config)
    [AI call lives inside conversation_service; market_config injects terminology]

10. Send response
    └── notification_service.send(phone_number, response)

11. Update lead state
    └── lead_service.advance_state(lead_id, transition)

12. Schedule follow-up if applicable
    └── followup_service.schedule_if_needed(lead_id, workflow_output)
```

**The routing decision (step 7) is deterministic.** `IntentResult.intent_type` + current
`lead_state` map to a workflow handler. The LLM output at step 6 is parsed into a typed
struct before influencing any routing. The LLM never decides what code runs next.

**Market config enters only at step 9** — in the prompt-building helper that constructs the
AI response. All routing, state transitions, and data access are market-agnostic.

### Human Handoff Flow

```
1.  Handoff triggered by one of:
    - intent_type == HUMAN_REQUESTED
    - lead_state == NEGOTIATION
    - confidence below threshold after retry
    - agent initiates from dashboard

2.  handoff_service.prepare(lead_id, session_id)
    - builds structured briefing: qualification summary, listing interests, conversation highlights

3.  notification_service.notify_agent(agent_id, briefing)

4.  lead_service.advance_state(lead_id, HUMAN_ACTIVE)

5.  notification_service.send(phone_number, "A property specialist will be with you shortly.")

6.  All subsequent messages routed to agent queue until agent releases
```

## Separation of Concerns

| Layer | Knows About | Does Not Know About |
|---|---|---|
| Routers | HTTP, request parsing, response formatting | Business rules, database, AI, market config |
| Services | Business rules, domain models, SQLAlchemy, Anthropic SDK | HTTP, other services' tables, workflow sequences, market config |
| Workflows | Service function signatures, state transitions, market_config (passed through) | Database internals, AI prompts, HTTP |
| Models | Data shapes, validation constraints | How they are stored, served, or processed |
| Utils | stdlib and third-party libraries | Any app module |
| Prompt builders | MarketConfig parameters, context data | Business routing rules, lead lifecycle |

A layer that knows about something in its "Does Not Know About" column is an architecture violation.

## Infrastructure Layer vs Business Logic Layer

**Infrastructure layer** (changes when the technology stack changes):
- WhatsApp API integration — implemented in Phase 2 as `app/integrations/whatsapp/`
- Database session management (`app/database.py`)
- Anthropic client initialization (inside `conversation_service` until extracted to `app/ai/`)
- External HTTP clients

**Business logic layer** (changes when real estate operations change):
- Lead qualification rules
- Lifecycle state transition conditions
- Property matching criteria
- Follow-up timing logic
- Escalation thresholds

**Market configuration layer** (changes when deploying to a new market):
- `MarketConfig` in `app/config.py`
- Prompt template parameters injected from `MarketConfig`
- Terminology overrides passed to prompt builders

The business logic layer must not depend on infrastructure or market configuration details. Market-aware behavior is a prompt concern, not a routing concern.

## Extraction Triggers (When to Add New Layers)

### Add `repositories/` when:
- The same SQLAlchemy query appears in 3+ service functions → first step: `{domain}_queries.py` inside `services/`
- A service has >100 lines of query logic that is independent of business rules
- Testing service logic requires mocking the data layer

### Add `app/ai/` when:
- 2+ services share the same prompt construction helper
- A service file exceeds ~150 lines primarily due to AI-specific code
- Prompt construction or response parsing needs independent unit tests

### Add `app/integrations/{channel}/` when:
- A new inbound channel is added (Phase 2: WhatsApp, future: SMS, email)
- Channel-specific payload parsing belongs here — never in services or routers

### Add `localization/` or an i18n layer when:
- V1 is live and a second language is actively required by a real deployment
- `MarketConfig.communication_locale` alone is insufficient for the response quality needed
- A real translation or phrasing library is justified by the gap

## Scalability Constraints That Apply Now

These apply regardless of extraction timing:

- **`tenant_id` on all records from day one.** Adding it later to a live database is painful. Even in V1 single-tenant mode, the field exists.
- **Paginated queries only.** No service function returns an unbounded list. All list queries accept `limit` and `offset` parameters.
- **Services accept domain objects, not provider payloads.** A service function signature must not change when the WhatsApp provider changes.
- **Lead lifecycle transitions are validated.** Advancing from `NEW_INQUIRY` to `CLOSED_WON` directly is rejected. Transitions follow the defined state machine.
- **MarketConfig is deployment-level, not per-request.** A single deployment serves one market. Per-request market switching is not an architectural assumption.
