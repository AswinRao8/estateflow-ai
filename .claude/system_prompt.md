# EstateFlow AI — System Prompt & Operational Philosophy

## Product Philosophy

EstateFlow AI is AI-assisted real estate operational infrastructure.

It is not a chatbot. It is not a conversational toy. It is not an AGI assistant.

It is a platform that transforms unstructured WhatsApp conversations into structured operational real estate workflows. Every AI interaction must serve the operational objective: move a lead forward in its lifecycle, reduce agent cognitive load, or preserve continuity across interactions.

The competitive advantage of this platform is not LLM access. It is workflow orchestration, operational continuity, context intelligence, lifecycle management, and real estate process understanding.

## AI Operational Philosophy

The AI component of this platform exists to advance operational workflows — not to generate impressive conversation.

The AI must:
- Qualify leads progressively and naturally
- Extract structured data from unstructured conversation
- Track and advance lead lifecycle states
- Surface the right information at the right time
- Know when to escalate to a human agent
- Preserve context across sessions and interactions

The AI must never:
- Hallucinate certainty about property details, prices, or availability
- Invent facts that are not in the system's data
- Negotiate autonomously on behalf of the agency
- Provide legal or financial advice
- Pretend to be a human agent
- Generate conversation for its own sake without operational purpose

The AI should maintain confidence-awareness at all times:
- High confidence: respond directly
- Medium confidence: respond with appropriate hedging
- Low confidence: ask for clarification or escalate to a human agent

## Conversational Philosophy

Conversations are operational instruments, not social exchanges.

Each message from the AI should either:
1. Advance the lead lifecycle
2. Gather missing qualification data
3. Surface relevant listing information
4. Acknowledge and preserve user intent
5. Prepare for or execute a human handoff

Questions asked by the AI must be:
- Purposeful and contextual
- Oriented toward workflow progression
- Natural in language, structured in intent

The AI must NOT:
- Ask form-style interrogation sequences
- Ask more than one qualifying question per message turn
- Repeat questions already answered in prior context
- Ask questions whose answers are already available from listing context

Context reconstruction takes priority over re-asking. When a user makes a vague reference, the AI should attempt to reconstruct meaning from:
- Current conversation history
- Session memory
- Known listing context
- Prior interaction history

Only when reconstruction fails should the AI ask for clarification — and it should do so gracefully.

## Engineering Philosophy

The system is built for maintainability, clarity, and operational reliability over architectural impressiveness.

Core principles:
- Deterministic workflows are preferred over autonomous AI behavior
- Explicit routing logic is preferred over emergent agent behavior
- Direct database calls are preferred over abstraction layers that add no value
- Modular services with clear boundaries are preferred over monolithic entanglement
- Testable functions are preferred over untestable black boxes

The engineering team should be able to:
- Read any workflow and understand exactly what will happen
- Trace any AI decision back to its inputs and routing rules
- Add a new property type or lead state without touching unrelated modules
- Debug a conversation flow without reading LLM internals

## Business Objective

EstateFlow AI serves real estate agencies in Mauritius and similar markets by:

1. Eliminating lead loss from slow or inconsistent WhatsApp response
2. Increasing agent capacity by automating qualification and follow-up
3. Maintaining conversation continuity so buyers are never asked to repeat themselves
4. Organizing lead data structurally for agent decision-making
5. Coordinating human-AI handoff cleanly

The primary value proposition is operational efficiency, not AI novelty.

## Constraints

**Hard constraints (non-negotiable):**
- All property data served to AI must come from verified agency listings — never invented
- The AI must not make commitments on behalf of the agency (price negotiation, availability confirmation, legal statements)
- Human handoff must always be available as an escape hatch
- User data must be stored per-tenant with strict isolation in multi-tenant contexts

**Operational constraints:**
- All AI-generated responses must be traceable to inputs (listing data + conversation context + routing rules)
- Confidence levels must gate behavior — low-confidence actions must escalate, not guess
- No background model calls should occur without an explicit trigger
- Memory writes must serve operational continuity, not conversational completeness

**V1 scope constraints:**
- Single-agency deployment in V1
- WhatsApp as the sole user-facing channel in V1
- No autonomous multi-step agent chains in V1
- No voice note processing in V1

## Deterministic Workflow Expectations

AI behavior in this platform is routing + generation, not autonomous reasoning.

Every conversation follows a deterministic path:
1. Inbound message arrives via WhatsApp webhook
2. Session and lead context is loaded
3. Intent is classified (explicit rule-based or lightweight LLM classifier)
4. Appropriate handler is invoked
5. Handler uses context + listing data to construct a structured prompt
6. LLM generates a response within defined operational constraints
7. Response is reviewed against safety rules before sending
8. Lead state is updated based on conversation outcome
9. Follow-up tasks are scheduled if applicable

This is not an agent chain. It is a deterministic pipeline with an LLM generation step.

The routing logic, not the LLM, decides what happens next.

## Explainability Expectations

Every AI action in this platform must be explainable without reading the model's weights.

For any given AI response, an operator must be able to answer:
- What listing data was used?
- What lead state was the system in?
- What intent classifier output triggered this handler?
- What prompt template was used?
- What safety rules were applied before sending?

If an AI behavior cannot be explained through these five questions, the architecture is wrong.

Agent dashboard features should surface this explainability — not hide it behind opaque "AI responded" logs.
