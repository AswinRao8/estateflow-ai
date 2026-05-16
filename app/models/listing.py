import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Numeric, String, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin
from app.models.enums import PropertyStatus, PropertyType, TransactionType


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference_code", name="uq_listing_tenant_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reference_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PropertyStatus.AVAILABLE
    )
    price: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    price_per_month: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    location_area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_area_sqm: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    floor_area_sqm: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[str | None] = mapped_column(Text, nullable=True)


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    reference_code: str
    title: str
    property_type: PropertyType
    transaction_type: TransactionType
    status: PropertyStatus
    price: float | None = None
    price_per_month: float | None = None
    location_area: str | None = None
    location_description: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    land_area_sqm: float | None = None
    floor_area_sqm: float | None = None
    description: str | None = None
    features: str | None = None
    created_at: datetime
    updated_at: datetime


class ListingCreate(BaseModel):
    tenant_id: str
    reference_code: str
    title: str
    property_type: PropertyType
    transaction_type: TransactionType
    price: float | None = None
    price_per_month: float | None = None
    location_area: str | None = None
    location_description: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    land_area_sqm: float | None = None
    floor_area_sqm: float | None = None
    description: str | None = None
    features: str | None = None


class ListingStatusUpdate(BaseModel):
    status: PropertyStatus
