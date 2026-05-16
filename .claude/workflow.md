# EstateFlow AI — Development Workflow

## Sequencing Philosophy

Implementation follows: **validated workflow behavior → stable domain understanding → infrastructure hardening.**

This is the inverse of the intuitive build order. The intuitive order ("lay infrastructure, then build product") produces hardened infrastructure serving workflows that do not yet exist. When those workflows finally run, they reveal that the data model was wrong, the caching assumptions were wrong, and the scheduled task structure was wrong — after the infrastructure is already in place and resisting change.

The correct order:

1. **Validated workflow behavior first.** Run the core pipeline end-to-end before committing to infrastructure. A qualification workflow running against real messages reveals the actual shape of the data model. Schema decisions made before this moment are guesses.

2. **Stable domain understanding before schema hardening.** Migrations are reversible but friction-heavy in practice. Domain model structure should stabilize through running workflows before constraints, cascade rules, and structured columns are locked in.

3. **Infrastructure hardening only under observed pressure.** Redis, Celery, and a repository layer are justified by measured operational problems — not anticipated ones. Adding them speculatively adds complexity without adding workflow capability.

## Market Compatibility Principle

**Workflows are market-agnostic. Configuration is market-aware.**

All workflow logic — lead qualification, listing inquiry, property matching, human handoff, follow-up — is identical across all markets. The questions asked, the states transitioned, and the routing rules applied are universal real estate operations.

What changes between markets: terminology in AI responses, price formatting, area units, timezone, and communication style. These are controlled by `MarketConfig` in application settings, passed as parameters to prompt-building helpers. They do not affect workflow routing, service logic, or database schema.

A new market deployment requires a configuration update. It does not require new workflows, new services, or code changes.

---

## Implementation Phase Order

Implementation must proceed in strict phase order. Do not begin a later phase until the current phase is validated.

---

### Phase 0 — Foundation
**Goal:** Working project skeleton with no business logic

Deliverables:
- FastAPI application factory with health and readiness endpoints
- Database connection and Alembic migration infrastructure
- Configuration management via Pydantic settings
- `MarketConfig` block wired into Settings: currency code, currency symbol, area unit,
  IANA timezone, communication locale tag
- Folder structure established per architecture spec
- CI baseline: lint, type check, empty test suite passes

**Intentionally excluded:**
- Redis — session handling uses the database directly until a cache layer is justified
  by measured latency
- Celery — no background task infrastructure until scheduling complexity demands it
- Repository layer — services call SQLAlchemy directly from day one
- i18n/l10n framework — `MarketConfig` parameters cover all V1 localization needs

Validation checkpoint:
- `GET /health` returns 200
- `GET /ready` reflects real database reachability
- Database migrations run cleanly on a fresh schema
- All lint and type checks pass
- `MarketConfig` fields readable from settings with correct defaults

---

### Phase 1 — Core Data Layer
**Goal:** Minimal domain models and direct-access services sufficient to support Phase 3 workflows

Deliverables:
- Lead model + `lead_service` — get_or_create, lifecycle state transitions
- Listing model + `listing_service` — CRUD, availability queries
- Session model + `session_service` — get or create active session
- Message model + `conversation_service` — save and retrieve messages
- Alembic migration for all four tables
- Unit tests: lifecycle state machine (no database required)
- Integration tests: `lead_service` against real test database

**Intentionally excluded:**
- Repository layer — no `repositories/` directory; services own their queries
- Deep cascade and FK constraints beyond what Phase 3 workflows have verified they need
- Speculative indexes — added under observed query pressure, not preemptively
- Structured qualification columns — `qualification_data` stays as JSON until Phase 6
  runs and the actual field set is known
- Market-specific schema columns — geographic and currency fields live in settings,
  not in the database

Validation checkpoint:
- Lifecycle state transitions enforce valid paths and reject invalid ones
- `get_or_create_lead` is idempotent for the same phone number and tenant
- Services tested against a real test database — no mocking of SQLAlchemy
- Migration is reversible (downgrade implemented and tested)

---

### Phase 2 — WhatsApp Integration
**Goal:** Receive and send WhatsApp messages reliably

Deliverables:
- WhatsApp webhook endpoint (inbound message reception)
- WhatsApp message send function (outbound)
- Webhook signature validation
- Message payload parsing into internal `InboundMessage` type
- Basic inbound handler that logs and returns 200

**Intentionally excluded:**
- Business logic — this phase is transport only
- Market-specific message parsing — `InboundMessage` is a universal internal type

Validation checkpoint:
- Webhook receives a real WhatsApp test message
- Message payload is correctly parsed into `InboundMessage`
- Outbound message sends successfully to a test number
- Invalid webhook signatures are rejected before any processing occurs
- No business logic in this layer confirmed by code review

---

### Phase 3 — Core Pipeline (Session + Lead + Message)
**Goal:** End-to-end message flow runs correctly without any AI

Deliverables:
- `inbound_message_workflow` — orchestrates session, lead, and message persistence in sequence
- Session created or retrieved on every inbound message
- Lead created or retrieved from session
- Inbound message stored to conversation history
- Human-active check: leads with `is_human_active = True` are detected and routed
  to agent queue (stub at this phase)
- Outbound message stored after send
- Integration test: inbound message → session → lead → message stored → 200 returned

**Intentionally excluded:**
- AI response generation — not in this phase
- Intent classification — not in this phase
- Any workflow beyond the core pipeline

Validation checkpoint:
- Full flow: WhatsApp message arrives → session created → lead created → message
  stored → 200 returned
- Second message from same number retrieves existing session and lead — no duplicates
- Human-active leads are detected before any AI path is entered
- Zero AI calls in this phase — confirmed by asserting no Anthropic client calls in test

---

### Phase 4 — Intent Classification
**Goal:** Classify lead intent with enough precision to route deterministically to the correct workflow

Deliverables:
- `conversation_service.classify_intent(message, context)` → `IntentResult`
- `IntentType` enum: `LISTING_INQUIRY`, `BUYER_QUALIFICATION`, `VIEWING_REQUEST`,
  `FOLLOW_UP`, `HUMAN_REQUESTED`, `GENERAL_INQUIRY`, `OUT_OF_SCOPE`
- `IntentResult`: `intent_type`, `confidence`, `extracted_data`
- Deterministic routing map: `intent_type` × `lead_state` → workflow handler
- Rule-based pre-classification for known patterns (listing reference in message
  → `LISTING_INQUIRY`)
- Low-confidence path routes to clarification, not a random handler

**Market note:** Intent classification is universal. The LLM understands buyer intent
regardless of market. `MarketConfig.communication_locale` influences the classification
prompt's language register, not its routing output.

Validation checkpoint:
- Tested against 20+ representative messages covering all intent types
- Every `intent_type × lead_state` combination maps to a specific handler — no
  unhandled combinations
- Low-confidence path returns a clarification response, not a workflow execution
- Rule-based patterns fire correctly without an LLM call
- Routing decision is logged with intent, confidence, and lead state for every message

---

### Phase 5 — Listing-Aware Responses
**Goal:** Answer questions about listings from structured data without hallucination

Deliverables:
- `listing_inquiry_workflow` — retrieves listing, builds context, generates response
- Listing inquiry prompt template inside `conversation_service`
- Price and area formatted using `MarketConfig` currency and unit settings
- Response parsing — extract follow-up triggers from structured response
- Honest no-match handling: if listing not found or data incomplete, acknowledge;
  do not invent

**Market note:** This phase is where `MarketConfig` first appears in prompt construction.
Price display uses `currency_symbol` and area uses `area_unit`. Property type labels
use `property_terminology` overrides if defined. The workflow logic itself does not branch
on market.

Validation checkpoint:
- Tested with 5 real listings: questions about price, location, and features answered
  correctly
- Price and area units displayed consistently with market config settings
- System does not produce details not present in the database record
- Listing-not-found case returns honest acknowledgment — no hallucination
- Prompt builder and response parser tested with fixed inputs (no live Anthropic calls in tests)

---

### Phase 6 — Buyer Qualification
**Goal:** Build a buyer profile progressively across multiple conversation turns

Deliverables:
- `qualification_workflow` — extracts and merges buyer profile across turns
- Qualification fields: budget range, location preferences, property type, timeline, urgency
- Question selection: one question per turn, does not re-ask answered fields
- Context-aware entry: adjusts based on listing-centric vs. open inquiry entry
- Qualification data merged into `lead.qualification_data` after each turn (JSON,
  schema-free)

**Market note:** Qualification fields are market-agnostic abstractions. "Location
preferences" means what is locally meaningful — neighborhood, suburb, district,
zone, emirate, arrondissement — the prompt template injects the right terminology
from `MarketConfig`. The qualification logic, state transitions, and data model
do not change between markets.

**Schema note:** `qualification_data` remains JSON through this phase. Structured
column extraction is deferred until this phase runs and the actual field set used
in practice is known. Schema hardening happens after domain understanding is stable.

Validation checkpoint:
- Multi-turn qualification conversation tested end-to-end
- Previously answered fields are not re-asked
- Partial profiles do not block the workflow — system continues with available data
- Qualification data is readable from the lead record after each turn

---

### Phase 7 — Property Matching
**Goal:** Recommend relevant listings using structured SQL matching — no vector database

Deliverables:
- `listing_service.match_listings(buyer_profile, tenant_id)` — SQL filter and rank query
- Matching criteria: property type, price range, location area, bedroom count
- Match result includes relevance indicator and match explanation
- `property_matching_workflow` — generates recommendation message with reasoning
- Honest no-match response: acknowledges gap and offers to adjust criteria;
  does not fabricate alternatives

**Market note:** Matching criteria are universal. Price comparison uses the market's
currency (already stored as a numeric in the database). Location area comparison
is string-based — the geographic concept is whatever is stored in `listing.location_area`
for that market. No market-specific query branches are needed.

Validation checkpoint:
- Matching tested against real listing data with diverse buyer profiles
- No-match case acknowledged honestly — no hallucinated alternatives
- Match explanations reference actual listing field values
- All SQL queries are bounded — no unbounded collection returns

---

### Phase 8 — Human Handoff
**Goal:** Transfer a lead to a human agent with full context and zero conversation break

Deliverables:
- `handoff_service.prepare(lead_id, session_id)` — builds structured handoff briefing
- Trigger conditions: `NEGOTIATION` state, low AI confidence, `HUMAN_REQUESTED` intent,
  agent-initiated
- Agent notification via dashboard and optional WhatsApp message to agent
- Lead transitions to `HUMAN_ACTIVE` state
- `release_human` — agent releases lead and AI resumes
- Lead receives acknowledgment message during handoff

Validation checkpoint:
- Tested for all four trigger conditions
- Agent briefing contains: lead summary, qualification data, listing interests,
  conversation highlights
- Lead does not need to repeat context after handoff
- Agent can release the lead and AI resumes without conversation break

---

### Phase 9 — Follow-Up System
**Goal:** Re-engage stalled leads and execute post-interaction follow-ups deterministically

Deliverables:
- `followup_service` — evaluates follow-up eligibility, writes follow-up records
  with scheduled timestamps
- Follow-up triggers: post-viewing (24h, 48h), stalled lead (3 days inactive),
  no response after recommendation (48h)
- Follow-ups stored as database records; dispatched via a lightweight DB-driven
  poll at message-processing time
- Contextual follow-up messages — reference actual prior conversation context,
  not generic templates
- Suppression: human-active leads are not followed up by AI
- Follow-up timing calculated using `MarketConfig.timezone` for correct local-time
  scheduling

**Scheduling approach:** Follow-up records carry a `scheduled_at` timestamp (UTC).
A lightweight check at message-processing time (or a simple in-process interval task)
queries for due records and dispatches them. Celery is not introduced until follow-up
volume or scheduling precision make this approach insufficient — that trigger is
measured, not assumed.

Validation checkpoint:
- Follow-up records created with correct scheduled timestamps (UTC-converted from
  market timezone)
- Follow-up messages reference actual prior context — not generic check-ins
- Human-active leads are suppressed from AI follow-up
- Stalled lead recovery tested end-to-end

---

### Phase 10 — Agent Dashboard
**Goal:** Minimal agent-facing interface for lead management

Deliverables:
- Lead list: lifecycle state, source listing, last activity
- Lead detail: conversation history, buyer profile, listing interests
- Takeover: initiate human control from dashboard
- Release: return lead to AI
- Listing management: add, edit, deactivate
- Follow-up visibility: scheduled follow-ups per lead

Validation checkpoint:
- Agent can review, take over, and release a lead without reading this document
- Conversation history is complete and readable
- Buyer profile and listing interests visible without drilling into raw messages
- No broken UI states for leads in any lifecycle stage

---

## Infrastructure Hardening — Deferred, Post-MVP

The following components are not part of MVP. Each has a specific trigger condition.
Adding any of them before the trigger is met is an architecture violation.

| Component | Trigger to add |
|---|---|
| Redis session cache | DB-based session lookup is a measured latency bottleneck |
| Celery task queue | Follow-up volume or scheduling precision exceeds what DB polling can deliver |
| Repository layer | The same SQLAlchemy query appears in 3+ service functions |
| Structured qualification columns | Phase 6 has run and the actual qualification field set is stable |
| Additional indexes | Slow query observed and measured — not speculated |
| i18n/l10n framework | A second language is actively required by a live deployment |
| Per-tenant MarketConfig | Multiple tenants with different market settings exist |

---

## Validation Checkpoints

A phase is not complete until all checkpoints pass.

Checkpoint categories:
- **Functional** — the feature works as specified
- **Integration** — the feature works within the full system flow
- **Behavioral** — the system behaves correctly on edge cases, not just the happy path
- **Quality gate** — code review confirms no architecture violations

## Testing Expectations

| Phase | Test Type Required |
|---|---|
| 0 — Foundation | Smoke: health + readiness endpoints; MarketConfig reads correctly |
| 1 — Data Layer | State machine unit tests; service integration tests against real DB |
| 2 — WhatsApp | Manual integration test with real WhatsApp number |
| 3 — Core Pipeline | Integration: full message → session → lead → message flow; no-AI assertion |
| 4 — Intent | Unit tests for all intent × state routing combinations |
| 5 — Listing Response | Fixed-input tests for prompt builder and response parser; market config formatting verified |
| 6 — Qualification | Multi-turn conversation test; profile completeness and merge behavior |
| 7 — Matching | Matching accuracy test against known listing set |
| 8 — Handoff | End-to-end handoff test with human reviewer |
| 9 — Follow-Up | Scheduling test; context accuracy test on follow-up messages; timezone conversion test |
| 10 — Dashboard | Manual UX test with an agent unfamiliar with the codebase |

## Deployment Progression

```
Local development
       ↓
Staging (single-tenant, single market, real WhatsApp sandbox number)
       ↓
Production pilot (single agency, one market, monitored for 2 weeks)
       ↓
Production stable
       ↓
Second market (MarketConfig update only — no code changes required)
```

Production pilot requirements:
- Phase 1–10 validation checkpoints passed
- At least 50 test conversations run in staging
- Agent briefing reviewed and approved by a real estate agent
- Handoff flow reviewed end-to-end
- Follow-up system reviewed by agency stakeholder
- Second-market deployment validated as configuration-only (criterion 9 of V1 success)

## Development Lifecycle

**For any new feature:**
1. Confirm it is in scope (`mvp_scope.md`)
2. Identify which layer it belongs to (`architecture.md`)
3. Check if any existing module should be extended before creating a new one
4. Implement with tests
5. Code review for architecture violations (`execution_rules.md`)
6. Manual functional validation
7. Deploy to staging, validate again

**For any bug fix:**
1. Reproduce the bug in a test
2. Fix the code
3. Confirm the test passes
4. Confirm no regression in related tests
5. Deploy

**For any AI behavior change:**
1. Document the current behavior and why it is wrong
2. Identify the prompt template or routing logic responsible
3. Update in isolation — do not change multiple prompts at once
4. Test with a fixed set of sample messages covering the affected intent
5. Validate that adjacent intents are not affected

**For a new market deployment:**
1. Update `MarketConfig` fields in the deployment environment
2. Verify price and area formatting in listing responses
3. Verify follow-up timestamps use the correct timezone
4. Run the full staging conversation suite in the new market context
5. No workflow, service, or schema changes should be required
