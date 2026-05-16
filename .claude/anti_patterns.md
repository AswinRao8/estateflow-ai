# EstateFlow AI — Anti-Patterns

This document defines the failure modes that are most likely to harm this project. These are not theoretical risks — they are patterns that consistently destroy AI product codebases.

---

## Overengineering Risks

**The abstraction trap**
Building generic, reusable infrastructure before any specific requirement demands it. Manifests as:
- `BaseConversationHandler` with 6 subclasses before any handler actually differs
- `AbstractPropertyMatcher` interface that wraps a single implementation
- Generic `EventBus` for inter-service communication when direct function calls work fine

Rule: Abstract only when you have two real, working implementations that share structure. Not before.

**The configuration explosion**
Making every business rule a configurable parameter. Manifests as:
- `qualification_depth: int = config.get("QUALIFICATION_DEPTH", 5)`
- `follow_up_delay_hours: int = config.get("FOLLOW_UP_DELAY", 72)`
- Everything tunable, nothing readable

Rule: Configuration belongs in code, not environment files, until you have a real reason for runtime variation (different tenants, A/B testing). Don't pre-configure flexibility you haven't needed yet.

The exception: `MarketConfig` fields (currency, timezone, area unit) are legitimate runtime configuration because they represent real deployment variation — not speculative flexibility.

**The premature optimization loop**
Optimizing data access, caching strategy, or query performance before any real load exists. Manifests as:
- Caching layers for queries that run once per session
- Read replicas before the primary is under any strain
- Indexing every column defensively

Rule: Measure first. Optimize when evidence shows it is needed.

---

## Fake AI Architecture

**Routing dressed as intelligence**
Calling something an "AI agent" when it is a deterministic if-else chain with an LLM response appended. Not wrong on its own, but dangerous when the team starts believing the AI is doing something it is not.

The honest framing: this platform uses LLMs for natural language generation and light classification. The intelligence is in the routing rules, the data model, and the workflow design — not the model itself.

**Confidence theater**
Generating responses without modeling uncertainty, then adding disclaimers as decoration. Real confidence-awareness means:
- The system actually withholds low-confidence outputs
- Low-confidence states route to humans or clarification
- Confidence thresholds are enforced by code, not mentioned in system prompts and ignored

**Memory hallucination**
Describing the system as having "memory" when it is passing conversation history in a prompt. This is context injection, not memory. The distinction matters because:
- True memory degrades gracefully when context exceeds limits
- Prompt-injected "memory" silently loses old context
- Architecturally, these require different solutions at scale

Label what is actually happening: context window, session cache, database lookup. Not "AI memory."

---

## Premature Abstractions

**The handler registry anti-pattern**
Building a plugin-style registry for workflow handlers before there are enough handlers to justify it. The cost: indirection that makes debugging harder, a registration mechanism that must be maintained, and cognitive overhead for every reader.

When to use registries: when you have 5+ handlers and expect to add more regularly. Not at handler #2.

**The event-driven over-decomposition**
Decomposing a simple sequential workflow into events and subscribers because it "scales better." In practice:
- Debugging requires tracing events across multiple handlers
- Error handling becomes distributed and inconsistent
- The workflow is no longer readable as a sequence

When a workflow is: receive message → classify → fetch data → generate response → send → update state, write it as a linear function. That is exactly what it is.

**The base model explosion**
Creating `BaseLead`, `BaseMessage`, `BaseProperty` abstract models with inheritance hierarchies. In a system with 10 entity types, this creates fragile coupling. Use composition over inheritance. Shared fields belong in mixins or explicit duplication if the types are truly independent.

---

## Dependency Bloat

**LangChain**
LangChain is a prototyping framework that treats orchestration as a product. Its costs in a production system:
- Every workflow step is abstracted behind a chain construct, making debugging indirect
- The framework's version instability introduces breakage on routine updates
- Conceptual overhead: developers must understand both LangChain's model and the underlying LLM API
- The "chains" abstraction actively discourages the deterministic routing this platform requires
- When something goes wrong, the error is in LangChain's internals, not your code

This project calls the Anthropic SDK directly. That is the right decision.

**Vector databases (Chroma, Pinecone, Weaviate) in V1**
Vector search is appropriate when:
- You have unstructured text corpora that need semantic retrieval
- You cannot use structured queries to find what you need

This platform's listing data is structured. Matching on property type, price range, location, and bedroom count is a SQL query, not a vector search. Adding a vector database to serve as a fancy listing search engine adds:
- Infrastructure complexity and operational overhead
- An additional system that can fail
- Latency on every query
- A dependency that implies semantic matching is needed when it is not

If semantic matching becomes necessary (e.g., matching vague lifestyle descriptions to neighborhoods), add it then — with a real justification, not speculation.

**Multi-agent frameworks (AutoGen, CrewAI, AgentOps)**
These frameworks are designed for systems where autonomous agents collaborate with each other to produce outputs. EstateFlow AI does not have this architecture. It has:
- A deterministic pipeline
- A single LLM call per message turn
- Explicit routing based on intent and lead state

Introducing a multi-agent framework into this architecture would:
- Add autonomous behavior where determinism is required
- Obscure routing logic behind agent communication protocols
- Make testing impossible without significant mocking infrastructure
- Create debugging nightmares when a "sub-agent" produces unexpected output

---

## LangChain Misuse (Specific Patterns)

Even if LangChain is prohibited at the dependency level, its thinking patterns can infect the architecture. Watch for:

**Chain-ification of simple sequences**
Turning `step1() → step2() → step3()` into `Chain([Step1, Step2, Step3]).run()`. Adds zero value, costs readability.

**Memory objects**
Using any framework's "memory" abstraction that automatically manages what context to include. Context window management must be explicit in this system — we choose what the LLM sees because listing data, lead state, and buyer profile are structured and must be injected precisely.

**Tool-calling wrappers**
Wrapping database queries as LLM "tools" and letting the model decide when to fetch listing data. In a deterministic pipeline, the service layer decides when to fetch data — not the model. Model-controlled data access is unpredictable and untestable.

**Agents deciding their own next steps**
Any pattern where the LLM output determines what code runs next. In this platform, the intent classifier output (a structured enum) determines routing — not the raw model response.

---

## Unnecessary Vector DB Usage

The following are not good reasons to add a vector database:

- "It might be useful for search later" — implement structured search now; add semantic search if needed
- "The AI can use embeddings to understand buyer intent" — a classification prompt does this more reliably
- "We can store conversation history as embeddings" — conversation history is sequential text; a database timestamp query retrieves it
- "Property descriptions are hard to search with SQL" — structured fields (type, price, location) cover 95% of search cases; add full-text search (Postgres `tsvector`) for description search before adding a vector DB

Add a vector database only when you have a specific retrieval problem that structured queries and full-text search cannot solve.

---

## Localization and Market Anti-Patterns

**Hardcoded market assumptions in code**
Embedding country names, city names, neighborhood lists, currency symbols, or property portal URLs as string literals in service code, workflow logic, or prompt templates. These assumptions make the codebase geography-locked and require code changes for every new market.

Signs you are doing this:
- `if location in ["Port Louis", "Quatre Bornes", "Ebene"]:` in a service function
- `currency = "MUR"` hardcoded in a prompt builder
- `portal_url = "https://lexpress.mu/..."` embedded in listing sync code

Rule: Geographic and market-specific values belong in `MarketConfig`. Code should be parameterized; configuration should be environment-specific.

**Building a full i18n framework preemptively**
Introducing translation files, locale detection middleware, language routing, or `gettext`-style string externalization before a second language is actively needed. This adds significant complexity — multiple string catalogs to maintain, translation workflows to manage, locale-switching logic to test — for a benefit that does not yet exist.

V1 operates in one language. When a second language is genuinely required by a live deployment, introduce the minimum viable solution at that time.

**Encoding market logic in AI prompts**
Writing prompts like:
> "In Mauritius, buyers typically expect to negotiate 5-10% off the asking price..."

This is market knowledge embedded in unauditable, untestable prompt text. It will become wrong as markets evolve, it will not apply to other markets, and it cannot be verified by automated tests.

Conversational style and register belong in prompts. Market-specific business rules belong in code, as explicit conditionals tested against clear inputs.

**Over-abstracting market differences**
Creating a `MarketStrategy` class hierarchy, a `LocalizationService`, or a market-specific workflow variant because "different markets work differently." In practice:
- Real estate qualification is universal: budget, location preference, property type, timeline
- Human handoff logic is universal: negotiation state, low confidence, explicit request
- Follow-up timing is universal: days since inactivity, days since viewing

What varies is terminology and formatting — both of which are covered by `MarketConfig` parameters passed to prompt builders. A market that requires fundamentally different workflow logic is a different product, not a different configuration.

**Per-market database schemas**
Adding market-specific columns to the leads or listings tables: `expat_visa_status`, `dld_registration_number`, `mauritius_ipid_reference`. These couple the schema to a specific jurisdiction.

Schema columns must represent universal domain concepts. Jurisdiction-specific reference numbers, regulatory identifiers, and compliance fields belong in the JSON `qualification_data` or `features` columns — schema-free until genuinely universal.

**Treating timezone as an afterthought**
Storing follow-up timestamps in local time, using server timezone for scheduling, or ignoring timezone entirely in V1. Timezone handling is cheap to get right early and expensive to fix after data exists.

Rule: all timestamps stored as UTC. `MarketConfig.timezone` is used only for display and for converting user-specified local times to UTC at the boundary. Scheduling logic operates in UTC throughout.

---

## Orchestration Anti-Patterns

**Nested workflow calls**
`workflow_A` calls `workflow_B` calls `workflow_C`. Deep nesting makes it impossible to trace what state the system is in at any point. Workflows must be flat. If a workflow needs shared behavior, that behavior belongs in a service, not a nested workflow.

**Stateful workflow objects**
Workflow instances that accumulate state across multiple message turns. State belongs in the database (lead record, session record). Workflows are stateless functions that read from and write to persistent storage.

**Retry logic inside workflows**
Adding retry loops inside workflow steps for transient failures. Retries belong at the infrastructure layer (Celery task retry policy, HTTP client retry configuration). A workflow step that fails should propagate the failure cleanly.

**Silent failure swallowing**
`try: workflow.execute() except Exception: pass` anywhere in the codebase. Failures must surface. A message that fails to process must be logged with full context, not silently dropped.

**Background agent chains**
Any design where an AI agent triggers another AI agent, which triggers another, producing outputs that influence system state without a human or deterministic checkpoint between steps. In V1, every AI output is reviewed by a safety filter and the result is a single message sent to a user. No chaining.

---

## Architectural Drift Risks

**Dashboard feature creep driving backend complexity**
Agents request a new dashboard feature → developer adds a new API endpoint → endpoint requires new joined query → query requires a new service method → service method introduces cross-domain dependency. Each step seems reasonable; the accumulated result is entanglement.

Counter-pattern: new dashboard features must be justified by operational necessity, not convenience. If the data already exists, surface it through existing endpoints before creating new ones.

**Conversation "intelligence" expansion**
The temptation to make the AI "smarter" by giving it more autonomy in deciding what to say and what to do. The correct response to a conversation gap is usually a routing fix or a prompt improvement — not giving the model more freedom to improvise.

Rule: when AI behavior is wrong, look at routing first, prompt second, model capability last.

**Prompt engineering as architecture**
Encoding business logic in system prompts rather than in code. Prompts are not auditable, not testable, and not version-controlled in a meaningful way. Business rules (what states lead to handoff, what qualifies a buyer for a luxury listing) belong in code, checked by tests.

Prompts should contain: tone guidance, response format instructions, market terminology from `MarketConfig`. Prompts should not contain: lead lifecycle rules, property type definitions, qualification thresholds, or market-specific business knowledge.

**Adding AI where structure suffices**
- Using an LLM to parse a structured WhatsApp message when regex works
- Using an LLM to format a lead summary when string interpolation works
- Using an LLM to decide if a buyer is qualified when the qualification rules are explicit

The LLM should do what only a language model can do: understand natural language, generate contextual responses, handle ambiguity. It should not replace deterministic logic.
