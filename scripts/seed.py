"""
Local development seed script.

Usage:
    python scripts/seed.py            # truncate and reseed everything
    python scripts/seed.py --reset    # truncate only, no reseed

Inserts:
  - 20 realistic international property listings
  - 9 leads at varied lifecycle states with full conversation histories
  - Sessions, messages, and follow-ups for each lead
"""
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make app importable when running from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionFactory
from app.models.conversation import Message
from app.models.enums import (
    BuyerType,
    FollowUpStatus,
    FollowUpTriggerType,
    IntentType,
    LeadState,
    MessageDirection,
    PropertyStatus,
    PropertyType,
    TransactionType,
)
from app.models.follow_up import FollowUp
from app.models.lead import Lead
from app.models.listing import Listing
from app.models.session import Session as LeadSession

TENANT = "default"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _ago(days: float = 0, hours: float = 0, minutes: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days, hours=hours, minutes=minutes)


def _future(days: float = 0, hours: float = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days, hours=hours)


# ---------------------------------------------------------------------------
# Truncate
# ---------------------------------------------------------------------------

async def truncate_all(db: AsyncSession) -> None:
    # FK-safe deletion order: children before parents.
    for table in ("follow_ups", "messages", "sessions", "leads", "listings"):
        await db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": TENANT})
    await db.commit()
    print("  Truncated all seed tables.")


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

LISTINGS: list[dict] = [
    # ── FOR SALE ────────────────────────────────────────────────────────────
    {
        "reference_code": "REF-001",
        "title": "3-Bedroom Apartment — Marina Quarter",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 485_000,
        "bedrooms": 3,
        "bathrooms": 2,
        "floor_area_sqm": 142,
        "location_area": "Marina Quarter",
        "location_description": "High-floor unit in Marina Quarter's best-connected tower. Direct sea views from the living room and master bedroom. 5 min walk to tram, cafes, and the waterfront promenade.",
        "description": "Bright open-plan living space with premium finishes throughout. Floor-to-ceiling windows, fully fitted kitchen with Bosch appliances, two en-suite bathrooms, and a sizeable balcony overlooking the marina.",
        "features": "Sea view, balcony, covered parking x2, gym, pool, 24-hr concierge, storage room",
    },
    {
        "reference_code": "REF-002",
        "title": "2-Bedroom Apartment — Downtown Heights",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 320_000,
        "bedrooms": 2,
        "bathrooms": 2,
        "floor_area_sqm": 98,
        "location_area": "Downtown Heights",
        "location_description": "Central Downtown location. Walking distance to the business district, main metro line, and the city's premier retail mall.",
        "description": "Well-proportioned two-bedroom apartment with an open kitchen, separate laundry, and a covered balcony. Recently repainted and with new flooring throughout.",
        "features": "Balcony, covered parking, gym, pool, close to metro",
    },
    {
        "reference_code": "REF-003",
        "title": "4-Bedroom Villa — Palm Residences",
        "property_type": PropertyType.VILLA,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 1_250_000,
        "bedrooms": 4,
        "bathrooms": 4,
        "floor_area_sqm": 380,
        "land_area_sqm": 520,
        "location_area": "Palm Residences",
        "location_description": "Sought-after gated community on the west peninsula. Private beach access, boat moorings available, 15 min drive to city centre.",
        "description": "Spacious four-bedroom villa across two floors. Large open-plan kitchen and dining area leading to a private pool terrace. Maid's room, double garage, and beautifully landscaped garden.",
        "features": "Private pool, garden, double garage, beach access, gated community, smart home system, maid's room",
    },
    {
        "reference_code": "REF-006",
        "title": "5-Bedroom Villa — Golf Estates",
        "property_type": PropertyType.VILLA,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 2_800_000,
        "bedrooms": 5,
        "bathrooms": 6,
        "floor_area_sqm": 650,
        "land_area_sqm": 900,
        "location_area": "Golf Estates",
        "location_description": "Premium golf-front address in Golf Estates. Unobstructed fairway views, private gate access, and direct connection to the 18-hole championship course.",
        "description": "Grand contemporary villa with a double-height entrance foyer, chef's kitchen, cinema room, and temperature-controlled wine cellar. Master suite with private terrace overlooking the golf course.",
        "features": "Golf view, private pool, cinema room, wine cellar, 3-car garage, staff quarters, smart home",
    },
    {
        "reference_code": "REF-007",
        "title": "2-Bedroom Apartment — Harbour View",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.UNDER_OFFER,
        "price": 595_000,
        "bedrooms": 2,
        "bathrooms": 2,
        "floor_area_sqm": 118,
        "location_area": "Harbour View",
        "location_description": "Mid-rise tower with direct views of the working harbour and city skyline. Ferry terminal within walking distance.",
        "description": "Corner apartment with wrap-around balcony and dual aspect harbour and city views. Open-plan living, updated kitchen, built-in wardrobes throughout.",
        "features": "Harbour view, wrap-around balcony, 1 parking, gym, roof terrace",
    },
    {
        "reference_code": "REF-008",
        "title": "3-Bedroom Penthouse — Sky Residences",
        "property_type": PropertyType.PENTHOUSE,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 1_900_000,
        "bedrooms": 3,
        "bathrooms": 3,
        "floor_area_sqm": 290,
        "location_area": "Sky Residences",
        "location_description": "Full-floor penthouse on the 42nd floor of Sky Residences — the city's most recognisable residential tower. Panoramic 270° views.",
        "description": "Architect-designed penthouse with double-height ceilings, a private rooftop terrace with plunge pool, and bespoke Italian kitchen. Entire floor with no shared walls.",
        "features": "Private rooftop terrace, plunge pool, panoramic views, 2 parking spaces, concierge, private lift lobby",
    },
    {
        "reference_code": "REF-009",
        "title": "Retail Unit — Commerce Park",
        "property_type": PropertyType.COMMERCIAL,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 980_000,
        "floor_area_sqm": 210,
        "location_area": "Commerce Park",
        "location_description": "Ground-floor retail unit in Commerce Park's main pedestrian zone. High foot traffic, established tenant mix including F&B, health, and services.",
        "description": "Shell-and-core retail unit with full-height glazed frontage, 6m ceiling height, rear service access, and two dedicated customer parking bays. Vacant possession.",
        "features": "Ground floor, full-height glazing, rear service access, 2 parking bays, high foot traffic zone",
    },
    {
        "reference_code": "REF-011",
        "title": "4-Bedroom House — Greenfield Villas",
        "property_type": PropertyType.HOUSE,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 875_000,
        "bedrooms": 4,
        "bathrooms": 3,
        "floor_area_sqm": 310,
        "land_area_sqm": 480,
        "location_area": "Greenfield Villas",
        "location_description": "Quiet, tree-lined suburban enclave 20 min from the CBD. Excellent international schools within 5 min drive.",
        "description": "Detached family home with generous garden, large covered terrace, and an eat-in kitchen that opens to the rear lawn. Fourth bedroom currently used as a home office.",
        "features": "Private garden, covered terrace, double garage, quiet cul-de-sac, near top schools",
    },
    {
        "reference_code": "REF-012",
        "title": "2-Bedroom Apartment — Waterfront Walk",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.SOLD,
        "price": 445_000,
        "bedrooms": 2,
        "bathrooms": 2,
        "floor_area_sqm": 105,
        "location_area": "Waterfront Walk",
        "location_description": "Popular waterfront development with direct promenade access.",
        "description": "Sold. Two-bedroom apartment on the 8th floor with partial water views and a west-facing balcony. Sold off-plan, completed Q1 this year.",
        "features": "Partial water view, balcony, 1 parking, pool",
    },
    {
        "reference_code": "REF-014",
        "title": "3-Bedroom Townhouse — Heritage Oaks",
        "property_type": PropertyType.HOUSE,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 720_000,
        "bedrooms": 3,
        "bathrooms": 3,
        "floor_area_sqm": 245,
        "land_area_sqm": 195,
        "location_area": "Heritage Oaks",
        "location_description": "Established low-rise community with mature oak trees. Communal park, playground, and residents' gym.",
        "description": "End-of-row townhouse across three floors. Private courtyard garden at ground level, integrated garage, and a generous roof terrace on the top floor.",
        "features": "Courtyard garden, roof terrace, integrated garage, communal park, pet-friendly",
    },
    {
        "reference_code": "REF-015",
        "title": "Land Plot — North Gardens",
        "property_type": PropertyType.LAND,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 350_000,
        "land_area_sqm": 800,
        "location_area": "North Gardens",
        "location_description": "Residential plot in an approved development zone. All utilities at the boundary. Approved for a G+2 detached villa.",
        "description": "Freehold residential plot with approved permits for a single detached villa up to G+2. Flat terrain, well-defined boundaries, full ownership title.",
        "features": "Freehold title, utilities connected, G+2 approved, clear boundaries, paved road access",
    },
    {
        "reference_code": "REF-017",
        "title": "6-Bedroom Villa — Royal Palm Estate",
        "property_type": PropertyType.VILLA,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 4_200_000,
        "bedrooms": 6,
        "bathrooms": 7,
        "floor_area_sqm": 950,
        "land_area_sqm": 1_400,
        "location_area": "Royal Palm Estate",
        "location_description": "Ultra-premium beachfront plot in the most exclusive gated estate. Private beach, direct marina berth, full concierge service.",
        "description": "Custom-built beachfront villa with direct beach access from the rear terrace. Features a 25m lap pool, outdoor kitchen, 4-car garage, and a private cinema wing. Fully furnished by a renowned interior designer.",
        "features": "Beachfront, 25m lap pool, 4-car garage, cinema wing, outdoor kitchen, smart home, marina berth",
    },
    {
        "reference_code": "REF-019",
        "title": "3-Bedroom Apartment — Lakeview Towers",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.AVAILABLE,
        "price": 560_000,
        "bedrooms": 3,
        "bathrooms": 2,
        "floor_area_sqm": 155,
        "location_area": "Lakeview Towers",
        "location_description": "Twin tower development beside the city's central lake. Jogging paths, paddleboat hire, and weekend markets directly outside.",
        "description": "Upper-floor three-bedroom apartment with full lake views and a generous wrap-around balcony. Modern finishes, open-plan kitchen, study nook, and ample storage.",
        "features": "Lake view, wrap-around balcony, 2 parking spaces, gym, infinity pool, children's area",
    },
    {
        "reference_code": "REF-018",
        "title": "Studio Penthouse — The Arc",
        "property_type": PropertyType.PENTHOUSE,
        "transaction_type": TransactionType.SALE,
        "status": PropertyStatus.UNDER_OFFER,
        "price": 680_000,
        "bedrooms": 1,
        "bathrooms": 1,
        "floor_area_sqm": 88,
        "location_area": "The Arc",
        "location_description": "Iconic curved tower in the financial district. 38th-floor single-level penthouse with private terrace.",
        "description": "Studio penthouse with mezzanine sleeping area and a 40 sqm private terrace. Currently under offer. Enquiries for similar units welcome.",
        "features": "Private terrace, city views, 1 parking, concierge, rooftop pool, under offer",
    },
    # ── FOR RENT ────────────────────────────────────────────────────────────
    {
        "reference_code": "REF-004",
        "title": "Studio Apartment — Business Bay",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.AVAILABLE,
        "price_per_month": 1_800,
        "bedrooms": 0,
        "bathrooms": 1,
        "floor_area_sqm": 48,
        "location_area": "Business Bay",
        "location_description": "Compact, well-managed studio in the heart of Business Bay. Metro station 3 min walk.",
        "description": "Furnished studio on the 12th floor. Queen bed, sofa bed, kitchenette with microwave and fridge, built-in wardrobe. Ideal for a single professional.",
        "features": "Fully furnished, gym, pool, metro access, high-speed WiFi included",
    },
    {
        "reference_code": "REF-005",
        "title": "1-Bedroom Apartment — Canal View",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.AVAILABLE,
        "price_per_month": 2_400,
        "bedrooms": 1,
        "bathrooms": 1,
        "floor_area_sqm": 72,
        "location_area": "Canal View",
        "location_description": "Low-rise boutique building beside the main canal. Cycling paths and farmers' market at the weekend.",
        "description": "Bright and airy one-bedroom with canal-facing balcony. Unfurnished but with white goods. Long-term lease preferred (12 months+).",
        "features": "Canal view, balcony, white goods included, 1 parking, pet-friendly on approval",
    },
    {
        "reference_code": "REF-010",
        "title": "1-Bedroom Apartment — Old Town District",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.RENTED,
        "price_per_month": 1_500,
        "bedrooms": 1,
        "bathrooms": 1,
        "floor_area_sqm": 65,
        "location_area": "Old Town District",
        "location_description": "Charming low-rise building in the historic Old Town. Walking distance to restaurants, galleries, and the weekly souk.",
        "description": "Currently tenanted. One-bedroom apartment in a restored heritage building with original tile floors and high ceilings. Available for re-tenancy in 3 months.",
        "features": "Heritage building, high ceilings, close to souk, 1 parking, rented",
    },
    {
        "reference_code": "REF-013",
        "title": "Grade-A Office Space — Central Business District",
        "property_type": PropertyType.COMMERCIAL,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.AVAILABLE,
        "price_per_month": 8_500,
        "floor_area_sqm": 320,
        "location_area": "Central Business District",
        "location_description": "Fitted-out Grade-A office on the 19th floor of a landmark CBD tower. Three reserved parking bays included.",
        "description": "Open-plan office fitted with raised flooring, server room, eight private offices, board room, breakout zone, and kitchenette. Ready to occupy on short notice.",
        "features": "Fitted Grade-A, 3 parking bays, server room, board room, 24-hr access, backup generator",
    },
    {
        "reference_code": "REF-016",
        "title": "2-Bedroom Apartment — Sunset Boulevard",
        "property_type": PropertyType.APARTMENT,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.AVAILABLE,
        "price_per_month": 2_200,
        "bedrooms": 2,
        "bathrooms": 2,
        "floor_area_sqm": 110,
        "location_area": "Sunset Boulevard",
        "location_description": "Leafy residential street popular with families and young professionals. Bus and metro links 7 min walk.",
        "description": "Semi-furnished two-bedroom apartment. Master with en-suite, second bedroom with large built-in. West-facing balcony with afternoon sun.",
        "features": "Semi-furnished, balcony, 1 parking, gym, children's play area",
    },
    {
        "reference_code": "REF-020",
        "title": "Warehouse Unit — Industrial Park East",
        "property_type": PropertyType.COMMERCIAL,
        "transaction_type": TransactionType.RENTAL,
        "status": PropertyStatus.INACTIVE,
        "price_per_month": 5_200,
        "floor_area_sqm": 1_100,
        "location_area": "Industrial Park East",
        "location_description": "Large logistics warehouse unit near the main freight corridor. High bay, dock leveller, and forklift access.",
        "description": "Not currently available. 1,100 sqm clear-span warehouse with 9m eaves height, dock leveller, 400A three-phase power, and office mezzanine. Interest for future availability welcome.",
        "features": "9m eaves, dock leveller, 3-phase power, office mezzanine, 24-hr security",
    },
]


async def seed_listings(db: AsyncSession) -> dict[str, Listing]:
    listings: dict[str, Listing] = {}
    for data in LISTINGS:
        listing = Listing(tenant_id=TENANT, **data)
        db.add(listing)
        listings[data["reference_code"]] = listing
    await db.flush()
    print(f"  Inserted {len(listings)} listings.")
    return listings


# ---------------------------------------------------------------------------
# Leads + Conversations
# ---------------------------------------------------------------------------

async def _add_messages(
    db: AsyncSession,
    *,
    session: LeadSession,
    lead: Lead,
    turns: list[tuple[MessageDirection, str, IntentType | None, datetime]],
) -> None:
    for direction, body, intent, ts in turns:
        msg = Message(
            tenant_id=TENANT,
            session_id=session.id,
            lead_id=lead.id,
            direction=direction,
            body=body,
            intent_type=intent,
            created_at=ts,
            updated_at=ts,
        )
        db.add(msg)


async def seed_leads(db: AsyncSession, listings: dict[str, Listing]) -> None:
    IN = MessageDirection.INBOUND
    OUT = MessageDirection.OUTBOUND

    # ── 1. Ahmed Al-Rashidi  ─ NEW_INQUIRY ──────────────────────────────────
    lead1 = Lead(
        tenant_id=TENANT,
        phone_number="+971501234567",
        state=LeadState.NEW_INQUIRY,
        source_listing_ref_code="REF-001",
        is_human_active=False,
    )
    db.add(lead1)
    await db.flush()
    sess1 = LeadSession(
        tenant_id=TENANT, lead_id=lead1.id, channel="whatsapp",
        listing_ref_code="REF-001",
        is_active=True, last_activity_at=_ago(hours=2),
    )
    db.add(sess1)
    await db.flush()
    await _add_messages(db, session=sess1, lead=lead1, turns=[
        (IN,  "Hi, I saw the 3-bedroom apartment in Marina Quarter. Can you tell me more about it?",
         IntentType.LISTING_INQUIRY, _ago(hours=2)),
        (OUT, "Hi Ahmed! Great to hear from you. The Marina Quarter apartment (REF-001) is a beautiful high-floor unit with sea views, 142 sqm, listed at $485,000. It comes with 2 covered parking spaces, gym, and pool access. Would you like to know about the layout or availability of a viewing?",
         None, _ago(hours=1, minutes=55)),
    ])

    # ── 2. Priya Sharma  ─ QUALIFYING ───────────────────────────────────────
    lead2 = Lead(
        tenant_id=TENANT,
        phone_number="+6591234567",
        state=LeadState.QUALIFYING,
        buyer_type=BuyerType.INVESTOR,
        is_human_active=False,
        qualification_data={
            "property_type": "APARTMENT",
            "budget_max": 600_000,
        },
    )
    db.add(lead2)
    await db.flush()
    sess2 = LeadSession(
        tenant_id=TENANT, lead_id=lead2.id, channel="whatsapp",
        is_active=True, last_activity_at=_ago(days=1),
    )
    db.add(sess2)
    await db.flush()
    await _add_messages(db, session=sess2, lead=lead2, turns=[
        (IN,  "Hello, I'm looking to buy an investment apartment.",
         IntentType.BUYER_QUALIFICATION, _ago(days=1, hours=4)),
        (OUT, "Hi Priya! Great to hear from you. I'd love to help you find a good investment apartment. To make sure I show you the most relevant options — what's your approximate budget range?",
         None, _ago(days=1, hours=3, minutes=58)),
        (IN,  "I'm thinking up to around $600k.",
         IntentType.BUYER_QUALIFICATION, _ago(days=1, hours=3, minutes=30)),
        (OUT, "Got it, up to $600,000. Are you looking in a specific area of the city, or are you open to different locations as long as the rental yield is strong?",
         None, _ago(days=1, hours=3, minutes=28)),
        (IN,  "Ideally somewhere with good rental demand. Near the marina or downtown would be great.",
         IntentType.BUYER_QUALIFICATION, _ago(days=1, hours=3)),
        (OUT, "Marina Quarter and Downtown Heights both have strong short-term and long-term rental demand. Any preference on bedroom count? Studios and 1-beds tend to have higher yield; 2-beds attract longer tenancies.",
         None, _ago(days=1, hours=2, minutes=58)),
        (IN,  "Probably 2 bedrooms to keep it versatile.",
         IntentType.BUYER_QUALIFICATION, _ago(days=1, hours=2, minutes=20)),
        (OUT, "Understood — a 2-bedroom gives you flexibility. Just to confirm: are you buying as a cash purchase or with financing? That affects which properties we'd prioritise.",
         None, _ago(days=1, hours=2, minutes=18)),
        (IN,  "Cash purchase, full amount.",
         IntentType.BUYER_QUALIFICATION, _ago(days=1, hours=1, minutes=45)),
        (OUT, "Perfect, that simplifies things considerably. Let me pull together the best 2-bedroom options in your budget across Marina Quarter and Downtown. I'll send those over shortly.",
         None, _ago(days=1, hours=1, minutes=43)),
    ])

    # ── 3. David Mitchell  ─ MATCHING_PROPERTIES ────────────────────────────
    lead3 = Lead(
        tenant_id=TENANT,
        phone_number="+447911234567",
        state=LeadState.MATCHING_PROPERTIES,
        buyer_type=BuyerType.EXPAT,
        is_human_active=False,
        qualification_data={
            "property_type": "APARTMENT",
            "bedrooms": 3,
            "budget_min": 400_000,
            "budget_max": 600_000,
            "location": "Marina Quarter",
            "timeline": "within 3 months",
        },
    )
    db.add(lead3)
    await db.flush()
    sess3 = LeadSession(
        tenant_id=TENANT, lead_id=lead3.id, channel="whatsapp",
        is_active=True, last_activity_at=_ago(days=2),
    )
    db.add(sess3)
    await db.flush()
    await _add_messages(db, session=sess3, lead=lead3, turns=[
        (IN,  "Hi there. I'm relocating from London and need a 3-bed apartment to buy. Budget around 400–600k.",
         IntentType.BUYER_QUALIFICATION, _ago(days=3, hours=5)),
        (OUT, "Welcome! Happy to help you settle in. Any particular area in mind, or are you still exploring?",
         None, _ago(days=3, hours=4, minutes=58)),
        (IN,  "I like the look of Marina Quarter from what I've seen online.",
         IntentType.BUYER_QUALIFICATION, _ago(days=3, hours=4, minutes=20)),
        (OUT, "Marina Quarter is a great choice for expats — very walkable, good transport links, and a lively waterfront. What's your timeline for the move?",
         None, _ago(days=3, hours=4, minutes=18)),
        (IN,  "Ideally within 3 months. I have a job starting end of next quarter.",
         IntentType.BUYER_QUALIFICATION, _ago(days=3, hours=3, minutes=50)),
        (OUT, "Understood — 3 months is workable for a resale purchase. Let me show you what's available in Marina Quarter in your range.\n\nHere are 2 options that match well:\n\n1. REF-001 — 3BR, 142 sqm, sea view, $485,000. High floor, 2 parking, direct marina access.\n\n2. REF-019 — 3BR, 155 sqm, lake view, $560,000. Wrap-around balcony, larger floor plan, top-floor infinity pool.\n\nBoth are available immediately. Which appeals more, or would you like details on either?",
         None, _ago(days=2, hours=2)),
        (IN,  "REF-001 sounds more interesting honestly. I like the sea view.",
         IntentType.LISTING_INQUIRY, _ago(days=2, hours=1, minutes=30)),
        (OUT, "Good instinct — the views on REF-001 are genuinely impressive. The unit is on the 28th floor, so you get unobstructed sea and marina views from the living room and master bedroom. Would you like to schedule a viewing?",
         None, _ago(days=2, hours=1, minutes=28)),
    ])

    # ── 4. Sarah Chen  ─ VIEWING_INTEREST ───────────────────────────────────
    lead4 = Lead(
        tenant_id=TENANT,
        phone_number="+6591234568",
        state=LeadState.VIEWING_INTEREST,
        buyer_type=BuyerType.RESIDENTIAL,
        is_human_active=False,
        source_listing_ref_code="REF-003",
        qualification_data={
            "property_type": "VILLA",
            "bedrooms": 4,
            "budget_max": 1_500_000,
            "location": "Palm Residences",
        },
    )
    db.add(lead4)
    await db.flush()
    sess4 = LeadSession(
        tenant_id=TENANT, lead_id=lead4.id, channel="whatsapp",
        listing_ref_code="REF-003",
        is_active=True, last_activity_at=_ago(days=1, hours=3),
    )
    db.add(sess4)
    await db.flush()
    await _add_messages(db, session=sess4, lead=lead4, turns=[
        (IN,  "I clicked on your listing for the Palm Residences villa. Is the 4-bed still available?",
         IntentType.LISTING_INQUIRY, _ago(days=4, hours=6)),
        (OUT, "Hi Sarah! Yes, REF-003 in Palm Residences is still available at $1,250,000. It's a 4-bedroom, 4-bathroom villa with a private pool, double garage, and beach access. Would you like more details?",
         None, _ago(days=4, hours=5, minutes=55)),
        (IN,  "Yes please — how big is the plot and is the garden usable year round?",
         IntentType.LISTING_INQUIRY, _ago(days=4, hours=5)),
        (OUT, "The land area is 520 sqm with a 380 sqm built-up. The garden is landscaped and south-facing so it gets sun most of the day. There's a covered lounge area for shade, and the pool area is sheltered by the main structure. Very usable.",
         None, _ago(days=4, hours=4, minutes=55)),
        (IN,  "That sounds really nice. Are there good schools nearby?",
         IntentType.GENERAL_INQUIRY, _ago(days=2, hours=8)),
        (OUT, "Yes — there are two well-regarded international schools within a 10-minute drive of Palm Residences, one British curriculum and one IB. A few of our buyers with families specifically chose this area for that reason.",
         None, _ago(days=2, hours=7, minutes=55)),
        (IN,  "I'd love to actually see it. Is it possible to arrange a viewing this week or next?",
         IntentType.VIEWING_REQUEST, _ago(days=1, hours=3)),
        (OUT, "Absolutely! The property is vacant and we can accommodate viewings any weekday. What works best for you — morning or afternoon, and which days are you generally free?",
         None, _ago(days=1, hours=2, minutes=58)),
    ])

    # ── 5. Marco Rossi  ─ VIEWING_SCHEDULED ─────────────────────────────────
    lead5 = Lead(
        tenant_id=TENANT,
        phone_number="+393331234567",
        state=LeadState.VIEWING_SCHEDULED,
        buyer_type=BuyerType.RESIDENTIAL,
        is_human_active=False,
        source_listing_ref_code="REF-011",
        qualification_data={
            "property_type": "HOUSE",
            "bedrooms": 4,
            "budget_max": 1_000_000,
            "location": "Greenfield Villas",
            "timeline": "flexible",
        },
    )
    db.add(lead5)
    await db.flush()
    sess5 = LeadSession(
        tenant_id=TENANT, lead_id=lead5.id, channel="whatsapp",
        listing_ref_code="REF-011",
        is_active=True, last_activity_at=_ago(days=1),
    )
    db.add(sess5)
    await db.flush()
    await _add_messages(db, session=sess5, lead=lead5, turns=[
        (IN,  "Ciao! I'm interested in the house in Greenfield Villas. Is it a family-friendly area?",
         IntentType.LISTING_INQUIRY, _ago(days=5, hours=7)),
        (OUT, "Hi Marco! Yes, Greenfield Villas is one of our most family-popular communities — tree-lined streets, very low traffic, and top international schools 5 minutes away. REF-011 specifically is at the end of a quiet cul-de-sac. Would you like a full overview of the property?",
         None, _ago(days=5, hours=6, minutes=56)),
        (IN,  "Yes. And is the garden big enough for kids to actually play?",
         IntentType.LISTING_INQUIRY, _ago(days=5, hours=6, minutes=10)),
        (OUT, "Definitely — the plot is 480 sqm and the garden at the rear is around 180 sqm of flat, usable lawn. There's also a covered terrace off the kitchen so you can watch the kids from inside. The house itself is 310 sqm across two floors.",
         None, _ago(days=5, hours=6, minutes=7)),
        (IN,  "Great. Can I come see it? Maybe Thursday or Friday?",
         IntentType.VIEWING_REQUEST, _ago(days=4, hours=3)),
        (OUT, "Thursday works well. Would 10:00 AM suit you? The agent will meet you at the property. I'll send you the address and contact details to confirm.",
         None, _ago(days=4, hours=2, minutes=58)),
        (IN,  "Thursday 10am works perfectly. See you then.",
         IntentType.VIEWING_REQUEST, _ago(days=4, hours=2, minutes=20)),
        (OUT, "Confirmed! You're booked for Thursday at 10:00 AM at Greenfield Villas, REF-011. Our agent James will meet you at the entrance. His number is +971 50 100 0001 in case you need to reach him. See you Thursday!",
         None, _ago(days=4, hours=2, minutes=18)),
        (IN,  "Thank you!",
         IntentType.GENERAL_INQUIRY, _ago(days=4, hours=2)),
    ])
    # Post-viewing follow-ups for Marco (viewing was 2 days ago)
    db.add(FollowUp(
        tenant_id=TENANT, lead_id=lead5.id,
        trigger_type=FollowUpTriggerType.POST_VIEWING_24H,
        status=FollowUpStatus.SENT,
        scheduled_at=_ago(days=1),
        sent_at=_ago(days=1),
    ))
    db.add(FollowUp(
        tenant_id=TENANT, lead_id=lead5.id,
        trigger_type=FollowUpTriggerType.POST_VIEWING_48H,
        status=FollowUpStatus.PENDING,
        scheduled_at=_future(hours=6),
    ))

    # ── 6. Jennifer Walsh  ─ HUMAN_ACTIVE ───────────────────────────────────
    lead6 = Lead(
        tenant_id=TENANT,
        phone_number="+12125551234",
        state=LeadState.HUMAN_ACTIVE,
        buyer_type=BuyerType.INVESTOR,
        is_human_active=True,
        assigned_agent_id="agent_james",
        qualification_data={
            "property_type": "PENTHOUSE",
            "bedrooms": 3,
            "budget_max": 2_200_000,
            "location": "Sky Residences",
            "timeline": "immediate",
        },
    )
    db.add(lead6)
    await db.flush()
    sess6 = LeadSession(
        tenant_id=TENANT, lead_id=lead6.id, channel="whatsapp",
        listing_ref_code="REF-008",
        is_active=True, last_activity_at=_ago(hours=5),
    )
    db.add(sess6)
    await db.flush()
    await _add_messages(db, session=sess6, lead=lead6, turns=[
        (IN,  "I want to make an offer on the penthouse in Sky Residences.",
         IntentType.HUMAN_REQUESTED, _ago(days=2, hours=9)),
        (OUT, "Hi Jennifer! Glad to hear you're interested in REF-008. Making an offer is definitely the next step — I'm going to connect you with our senior agent James who handles all offers and negotiations. He'll be in touch very shortly.",
         None, _ago(days=2, hours=8, minutes=55)),
        (IN,  "Great, I want to move quickly on this.",
         IntentType.HUMAN_REQUESTED, _ago(days=2, hours=8, minutes=30)),
        (OUT, "Understood — I've flagged this as high priority. James will call or message you within the next 30 minutes.",
         None, _ago(days=2, hours=8, minutes=28)),
        (IN,  "Hi Jennifer, this is James from the agency. I see you're interested in REF-008 — the Sky Residences penthouse. Happy to walk you through the offer process. What figure were you thinking?",
         None, _ago(days=2, hours=8)),
        (IN,  "I was thinking $1.75m as an opening offer. The listing is at $1.9m.",
         None, _ago(days=2, hours=7, minutes=40)),
        (IN,  "That's a reasonable opening. The seller has had two previous offers, both below $1.8m, which they declined. I'd suggest starting at $1.82m to signal seriousness. Shall I draft a formal letter of intent?",
         None, _ago(days=2, hours=7, minutes=35)),
        (IN,  "Yes please. $1.82m. And can we include a 30-day completion clause?",
         None, _ago(hours=5)),
    ])

    # ── 7. Khalid Al-Mansouri  ─ FOLLOW_UP (stalled) ────────────────────────
    lead7 = Lead(
        tenant_id=TENANT,
        phone_number="+97150987654",
        state=LeadState.FOLLOW_UP,
        buyer_type=BuyerType.RESIDENTIAL,
        is_human_active=False,
        qualification_data={
            "property_type": "VILLA",
            "bedrooms": 5,
            "budget_min": 2_000_000,
            "budget_max": 3_500_000,
            "location": "Golf Estates",
        },
    )
    db.add(lead7)
    await db.flush()
    sess7 = LeadSession(
        tenant_id=TENANT, lead_id=lead7.id, channel="whatsapp",
        is_active=True, last_activity_at=_ago(days=5),
    )
    db.add(sess7)
    await db.flush()
    await _add_messages(db, session=sess7, lead=lead7, turns=[
        (IN,  "I'm looking for a large villa in the Golf Estates area. 5 bedrooms minimum, budget around 2.5–3.5 million.",
         IntentType.BUYER_QUALIFICATION, _ago(days=7, hours=6)),
        (OUT, "Hi Khalid! That's a great budget for Golf Estates — we have a few exceptional villas. Are you looking for golf-front position specifically, or would a golf-view unit work too?",
         None, _ago(days=7, hours=5, minutes=58)),
        (IN,  "Golf-front would be ideal but I'd consider golf-view if the villa itself is impressive.",
         IntentType.BUYER_QUALIFICATION, _ago(days=7, hours=5, minutes=20)),
        (OUT, "Understood. Here's the best match right now:\n\nREF-006 — 5BR Golf-Front Villa, Golf Estates. 650 sqm built, 900 sqm plot, cinema room, wine cellar, 3-car garage. $2,800,000.\n\nAlso available: REF-017 — 6BR Beachfront Villa at $4.2m if you'd consider expanding the search area slightly.\n\nREF-006 seems the strongest fit for your criteria. Interested in a viewing?",
         None, _ago(days=6, hours=2)),
        (IN,  "REF-006 looks good. Let me think about it and discuss with my family.",
         IntentType.LISTING_INQUIRY, _ago(days=5, hours=3)),
        (OUT, "Of course, take your time. I'm here whenever you're ready to move forward or have questions.",
         None, _ago(days=5, hours=2, minutes=58)),
    ])
    db.add(FollowUp(
        tenant_id=TENANT, lead_id=lead7.id,
        trigger_type=FollowUpTriggerType.STALLED_3D,
        status=FollowUpStatus.PENDING,
        scheduled_at=_ago(days=2),
    ))
    db.add(FollowUp(
        tenant_id=TENANT, lead_id=lead7.id,
        trigger_type=FollowUpTriggerType.NO_RESPONSE_48H,
        status=FollowUpStatus.SENT,
        scheduled_at=_ago(days=4),
        sent_at=_ago(days=4),
    ))

    # ── 8. Emma Johansson  ─ CLOSED_WON ─────────────────────────────────────
    lead8 = Lead(
        tenant_id=TENANT,
        phone_number="+46701234567",
        state=LeadState.CLOSED_WON,
        buyer_type=BuyerType.EXPAT,
        is_human_active=False,
        source_listing_ref_code="REF-007",
        qualification_data={
            "property_type": "APARTMENT",
            "bedrooms": 2,
            "budget_max": 650_000,
            "location": "Harbour View",
        },
    )
    db.add(lead8)
    await db.flush()
    sess8 = LeadSession(
        tenant_id=TENANT, lead_id=lead8.id, channel="whatsapp",
        listing_ref_code="REF-007",
        is_active=False, last_activity_at=_ago(days=14),
    )
    db.add(sess8)
    await db.flush()
    await _add_messages(db, session=sess8, lead=lead8, turns=[
        (IN,  "Hi! Interested in the Harbour View 2-bed apartment. Is it still available?",
         IntentType.LISTING_INQUIRY, _ago(days=30, hours=5)),
        (OUT, "Hi Emma! REF-007 is available at $595,000 — it's a corner unit with wrap-around balcony and both harbour and city views. Shall I arrange a viewing?",
         None, _ago(days=30, hours=4, minutes=55)),
        (IN,  "Yes please. Can I come Saturday morning?",
         IntentType.VIEWING_REQUEST, _ago(days=29, hours=9)),
        (OUT, "Saturday 10:00 AM is confirmed at Harbour View, REF-007. See you then!",
         None, _ago(days=29, hours=8, minutes=58)),
        (IN,  "The viewing went really well. I'd like to make an offer.",
         IntentType.HUMAN_REQUESTED, _ago(days=27, hours=6)),
        (OUT, "That's brilliant news! I'm going to connect you with James to handle the offer and contract process.",
         None, _ago(days=27, hours=5, minutes=58)),
        (IN,  "Emma — James here. Congratulations, your offer of $575,000 was accepted this morning. We'll proceed to contract this week!",
         None, _ago(days=14, hours=2)),
        (IN,  "Amazing! Thank you so much for everything.",
         None, _ago(days=14, hours=1, minutes=45)),
    ])

    # ── 9. Rajan Nair  ─ CLOSED_LOST ────────────────────────────────────────
    lead9 = Lead(
        tenant_id=TENANT,
        phone_number="+60123456789",
        state=LeadState.CLOSED_LOST,
        buyer_type=BuyerType.RESIDENTIAL,
        is_human_active=False,
        qualification_data={
            "property_type": "APARTMENT",
            "bedrooms": 2,
            "budget_max": 350_000,
            "location": "Downtown Heights",
        },
    )
    db.add(lead9)
    await db.flush()
    sess9 = LeadSession(
        tenant_id=TENANT, lead_id=lead9.id, channel="whatsapp",
        is_active=False, last_activity_at=_ago(days=10),
    )
    db.add(sess9)
    await db.flush()
    await _add_messages(db, session=sess9, lead=lead9, turns=[
        (IN,  "Hello. I'm looking for a 2 bed apartment around Downtown, budget is 300–350k.",
         IntentType.BUYER_QUALIFICATION, _ago(days=20, hours=7)),
        (OUT, "Hi Rajan! At that price point in Downtown Heights, the best option we currently have is REF-002 at $320,000 — 2BR, 98 sqm, recently updated. Good value for the location.",
         None, _ago(days=20, hours=6, minutes=57)),
        (IN,  "Ok can you send more photos?",
         IntentType.LISTING_INQUIRY, _ago(days=19, hours=5)),
        (OUT, "Of course! I'll have the full photo set and floor plan sent over within the hour.",
         None, _ago(days=19, hours=4, minutes=58)),
        (IN,  "Thanks. I'll think about it.",
         IntentType.GENERAL_INQUIRY, _ago(days=18, hours=9)),
        (OUT, "No rush at all. I'm here whenever you're ready.",
         None, _ago(days=18, hours=8, minutes=57)),
        (IN,  "Hi, I've decided to go with another agency. They had something that suited us better. Thanks for your help.",
         IntentType.GENERAL_INQUIRY, _ago(days=10, hours=4)),
        (OUT, "No problem at all, Rajan — I hope the purchase goes smoothly. You're always welcome to come back if things change. Best of luck!",
         None, _ago(days=10, hours=3, minutes=58)),
    ])

    await db.commit()
    print("  Inserted 9 leads with sessions, messages, and follow-ups.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(reset_only: bool = False) -> None:
    async with SessionFactory() as db:
        print("Truncating existing seed data…")
        await truncate_all(db)

        if reset_only:
            print("Reset complete (no reseed requested).")
            return

        print("Seeding listings…")
        listings = await seed_listings(db)

        print("Seeding leads and conversations…")
        await seed_leads(db, listings)

        print("\nDone. Summary:")
        print(f"  Listings : {len(LISTINGS)}")
        print("  Leads    : 9  (NEW_INQUIRY, QUALIFYING, MATCHING, VIEWING_INTEREST,")
        print("                  VIEWING_SCHEDULED, HUMAN_ACTIVE, FOLLOW_UP,")
        print("                  CLOSED_WON, CLOSED_LOST)")
        print("  Follow-ups: 4 (2x SENT, 1x PENDING post-viewing, 1x PENDING stalled)")


if __name__ == "__main__":
    reset_only = "--reset" in sys.argv
    asyncio.run(run(reset_only=reset_only))
