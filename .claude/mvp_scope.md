# EstateFlow AI — MVP Scope (V1)

## Platform Identity

EstateFlow AI is a **globally compatible conversational real estate workflow engine**.
It is not a Mauritius-specific system, a regional chatbot, or a market-locked tool.

V1 launches with a single agency in one market. The architecture is designed to make
a second-market deployment a configuration change, not a code change.

---

## Included in V1

These features must be shipped in V1. They constitute the minimum viable operational platform.

**WhatsApp Integration**
- Receive inbound WhatsApp messages via provider webhook
- Send outbound WhatsApp messages via provider API
- Session management per phone number
- Listing context extraction from entry URL/message (when available)

**Market Configuration**
- `MarketConfig` block in application settings: currency code, currency symbol,
  area unit (sqm/sqft), IANA timezone, communication locale tag
- Optional property terminology overrides (e.g., "flat" instead of "apartment")
- Market config injected into AI prompt builders — not into routing or data logic
- Configuration is deployment-level: one market per deployment in V1

**AI Qualification**
- Intent classification: listing inquiry, buyer qualification, viewing request,
  human request, general inquiry
- Progressive buyer qualification through multi-turn conversation
- Buyer profile construction: budget range, location preferences, property type, timeline
- Qualification fields are market-agnostic; local terminology injected via market config
- Confidence-aware responses — system acknowledges uncertainty rather than guessing

**Listing-Aware Conversations**
- Listing-centric entry: AI knows property details before responding
- Listing data used in conversation: price, location, type, size, status
- Price display respects market currency and unit settings
- Basic property matching against buyer profile using SQL criteria
- Match recommendations with brief reasoning (why this property fits)

**Lead Lifecycle Management**
- Lead creation on first contact
- Lifecycle states: NEW_INQUIRY → QUALIFYING → MATCHING_PROPERTIES → VIEWING_INTEREST
  → VIEWING_SCHEDULED → POST_VIEWING → NEGOTIATION → CLOSED_WON / CLOSED_LOST
- State transitions triggered by conversation outcomes
- Lead state visible on agent dashboard

**Human Handoff**
- Handoff triggers: negotiation intent, explicit user request, low AI confidence,
  high-intent buyer
- Structured handoff briefing for human agent (lead summary, qualification, listing interests)
- User acknowledgment during handoff transition
- Agent takeover and release controls
- AI does not respond while human is active

**Basic Follow-Up**
- Post-viewing follow-up (24h, 48h after viewing)
- Stalled lead re-engagement (3 days inactive)
- Follow-up messages reference prior conversation context
- No follow-up while human agent is active
- Follow-up scheduling is database-driven, no external task queue required at V1

**Agent Dashboard (Minimal)**
- Lead list with state, source, last activity timestamp
- Lead detail: conversation history, buyer profile, listing interests
- Takeover and release controls
- Basic listing management: add, edit, mark inactive

**Infrastructure**
- Single-tenant deployment (one agency, one market)
- WhatsApp as sole user-facing channel
- Anthropic Claude as the LLM provider
- PostgreSQL for persistent data
- No Redis, no Celery — these are deferred until scaling pressure justifies them

---

## Excluded from V1

These features are deliberately excluded from the first version.

**Excluded AI Capabilities**
- Autonomous price negotiation
- Legal or financial advisory responses
- Voice note transcription and processing
- Image and document analysis (property photos, contracts)
- Behavioral learning from historical interaction patterns
- Personalization based on long-term user behavior

**Excluded Channels**
- Email integration
- SMS integration
- Web chat widget
- In-app messaging

**Excluded Operational Features**
- Automated viewing calendar integration (viewing requests collected, not auto-scheduled)
- CRM system integration
- Property portal sync (market-specific portals — deferred to V2+)
- Contract document generation
- Automated payment tracking
- Inventory management beyond basic listing CRUD

**Excluded Infrastructure**
- Multi-tenant architecture (single agency only in V1)
- Multi-agent orchestration frameworks
- Vector database for semantic search
- Real-time dashboard with WebSocket updates
- Enterprise analytics and BI reporting
- Role-based access control beyond agent vs. admin
- Redis session cache (not justified until session lookup latency is measured)
- Celery task queue (not justified until follow-up volume exceeds DB polling capacity)

**Excluded Localization**
- Multi-language support (deferred — see Deferred Features)
- Full i18n/l10n framework
- Per-lead language detection and switching
- Translation APIs or services
- Jurisdiction-specific compliance rules

---

## Deferred Features

These features are valid for this platform and will be implemented after V1, based on
real usage data.

**V2 Candidates (likely next)**
- Multi-tenant support — multiple agencies, potentially across markets
- Tenant-specific branding and WhatsApp numbers
- Viewing scheduler integration with agent calendars
- Lead source attribution (Facebook, website, portal, direct)
- Renter qualification flow (separate from buyer flow)
- Seller-side lead management (property valuation requests)
- Agent mobile notifications
- Redis session cache — when DB session lookup is a measured latency bottleneck

**V3 Candidates (after V2 validation)**
- Voice note processing
- Property recommendation refinement through feedback loops
- Contextual follow-up sequence builder (configurable per agency)
- Automated portal listing sync (market-specific portal APIs)
- Investor-specific qualification workflow
- International buyer qualification workflow (non-resident, overseas buyer context)
- Basic analytics: lifecycle progression rates, source performance
- Celery task queue — when follow-up volume demands it
- Multi-language support — when a deployment requires a second language

**Future Platform Capabilities**
- CRM integration (export leads to external systems)
- Document generation (viewing confirmation, offer summary)
- AI-assisted agent briefing summaries for team meetings
- Lead sharing and assignment between agents
- Full internationalization framework (if multiple languages are actively required)

---

## Non-Goals

These are things this platform will never do, regardless of version.

**Never Autonomous**
- The platform will never negotiate prices autonomously
- The platform will never make binding commitments on behalf of the agency
- The platform will never operate without a human oversight layer
- The platform will never replace human agents — it assists them

**Never Advisory**
- The platform will not provide legal advice
- The platform will not provide mortgage or financial advice
- The platform will not advise on investment strategy
- The platform will not provide valuations presented as professional assessments

**Never Geography-Locked**
- The platform will not contain hardcoded assumptions about any specific country,
  city, neighborhood, or regulatory environment
- Geographic concepts (location area, district, neighborhood) are terminology
  choices, not schema constraints
- A new market deployment must not require code changes — only configuration

**Never a Generic Product**
- The platform will not be rebuilt as a general-purpose real estate chatbot
- The platform will not be made horizontally applicable to any industry
- The architecture will not be generalized to support arbitrary vertical use cases

**Never Impression-Driven**
- AI conversational quality will not be optimized for impressiveness
- The platform will not add AI features to appear more sophisticated
- Response verbosity will not be increased to seem more intelligent
- The platform will not simulate human personality traits

---

## V1 Success Criteria

V1 is successful when:

1. A buyer contacts the agency via WhatsApp from a listing link
2. The AI responds within 10 seconds with listing-specific context, formatted for the
   deployment market (correct currency, correct area units)
3. The AI qualifies the buyer over 3–5 message turns without re-asking answered questions
4. If the buyer expresses viewing interest, the lead state advances and the agent is notified
5. The agent can take over the conversation, review full context, and release back to AI
6. The agent dashboard shows all active leads with their qualification status
7. A stalled lead receives a contextual follow-up after 3 days of inactivity
8. The agency can add and edit listings without developer involvement
9. Deploying to a second market requires only updating `MarketConfig` — not modifying
   workflow logic, service code, or database schema
