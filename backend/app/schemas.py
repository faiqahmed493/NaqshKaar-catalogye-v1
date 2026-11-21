"""Request bodies. Unknown facts are optional and stay NULL; nothing defaults to zero."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .enums import (AssetDecision, AttributeKey, AttributeSource, Availability, DimensionKind, ImageRole,
                    LinkCheckOutcome, ObservationOutcome, PlacementType, ReviewDecision, RoomType, SaleUnit,
                    UserRole, ViewAngle)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True, validate_default=True)


class Loose(BaseModel):
    """Tolerates extra keys (collector payloads, worker messages)."""
    model_config = ConfigDict(use_enum_values=True, validate_default=True)


# --------------------------------------------------------------------------- auth / users
class LoginIn(Strict):
    email: str
    password: str


class UserCreate(Strict):
    email: str
    display_name: str
    password: str = Field(min_length=10)
    role: UserRole = UserRole.curator


class UserUpdate(Strict):
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)


class ApiKeyCreate(Strict):
    name: str
    scopes: list[Literal["ingest", "worker", "catalogue_read"]]


# --------------------------------------------------------------------------- reference
class RetailerIn(Strict):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    website_url: str | None = None
    city: str | None = None
    country: str = Field(default="PK", min_length=2, max_length=2)
    contact_notes: str | None = None
    usage_terms: str | None = None
    is_active: bool = True


class RetailerPatch(Strict):
    name: str | None = None
    website_url: str | None = None
    city: str | None = None
    contact_notes: str | None = None
    usage_terms: str | None = None
    is_active: bool | None = None


# --------------------------------------------------------------------------- dimensions / prices
class Length(Strict):
    value: Decimal
    unit: Literal["m", "cm", "mm", "in", "ft", "ft_in"]
    inches: Decimal | None = None


class DimensionIn(Strict):
    kind: DimensionKind = DimensionKind.assembled
    width: Length | None = None
    depth: Length | None = None
    height: Length | None = None
    source_text: str | None = None
    source_axis_order: str | None = None
    source_ref: str | None = None
    observed_at: datetime | None = None
    note: str | None = None


class PriceIn(Strict):
    outcome: ObservationOutcome = ObservationOutcome.success
    price_pkr: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    compare_at_price_pkr: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_unit: SaleUnit | None = None
    availability: Availability = Availability.unknown
    includes_delivery: bool | None = None
    source_url: str | None = None
    checked_at: datetime | None = None
    failure_reason: str | None = None


class LinkCheckIn(Strict):
    outcome: LinkCheckOutcome
    url: str | None = None
    http_status: int | None = None
    note: str | None = None


class AttributeIn(Strict):
    key: AttributeKey
    value: str = Field(min_length=1)
    colour_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    source: AttributeSource = AttributeSource.curator
    verified: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)


class RoomUseIn(Strict):
    room_type: RoomType
    use_tag: str = "general"


class SetComponentIn(Strict):
    name: str
    category_id: int | None = None
    quantity: int = Field(ge=1)
    width_m: Decimal | None = Field(default=None, gt=0)
    depth_m: Decimal | None = Field(default=None, gt=0)
    height_m: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


# --------------------------------------------------------------------------- products / variants
class VariantIn(Strict):
    variant_key: str = "default"
    variant_label: str | None = None
    configuration: str = "standard"
    listing_url: str | None = None
    sale_unit: SaleUnit | None = None
    sale_unit_quantity: int | None = Field(default=None, ge=1)
    sale_unit_note: str | None = None
    placement_type: PlacementType | None = None
    notes: str | None = None
    dimensions: DimensionIn | None = None
    price: PriceIn | None = None
    attributes: list[AttributeIn] = []
    room_uses: list[RoomUseIn] = []
    set_components: list[SetComponentIn] = []


class VariantPatch(Strict):
    variant_key: str | None = None
    variant_label: str | None = None
    configuration: str | None = None
    listing_url: str | None = None
    sale_unit: SaleUnit | None = None
    sale_unit_quantity: int | None = Field(default=None, ge=1)
    sale_unit_note: str | None = None
    placement_type: PlacementType | None = None
    notes: str | None = None


class ProductIn(Strict):
    retailer_id: uuid.UUID
    name: str = Field(min_length=1)
    brand: str | None = None
    category_id: int | None = None
    description: str | None = None
    listing_url: str | None = None
    retailer_product_ref: str | None = None
    variant: VariantIn = VariantIn()


class ProductPatch(Strict):
    retailer_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1)
    brand: str | None = None
    category_id: int | None = None
    description: str | None = None
    listing_url: str | None = None
    retailer_product_ref: str | None = None


class ImagePatch(Strict):
    role: ImageRole | None = None
    view_angle: ViewAngle | None = None
    depicts_variant: bool | None = None
    usable_for_3d: bool | None = None
    reviewed: bool | None = None
    sort_order: int | None = None
    variant_id: uuid.UUID | None = None
    shared_with_all_variants: bool | None = None


class AdmissionReviewIn(Strict):
    decision: ReviewDecision
    comment: str | None = None


class RetireIn(Strict):
    reason: str | None = None


# --------------------------------------------------------------------------- generation
class GenerationRequest(Strict):
    engine_codes: list[str] = Field(min_length=1)
    image_ids: list[uuid.UUID] = Field(min_length=1)
    params: dict[str, dict] | None = None   # per-engine overrides, e.g. {"trellis": {"seed": 7}}
    priority: int = Field(default=0, ge=-10, le=10)


class ReprocessIn(Strict):
    rotation_deg: list[float] | None = None
    auto_yaw: bool | None = None


class AssetReviewIn(Strict):
    decision: AssetDecision
    checklist: dict[str, bool] = {}
    comment: str | None = None
    select_for_catalogue: bool = True


class PublishIn(Strict):
    """One-step 'add to catalogue': approve the asset (if given) and the variant together."""
    asset_id: uuid.UUID | None = None
    checklist: dict[str, bool] = {}
    comment: str | None = None


# --------------------------------------------------------------------------- worker protocol
class WorkerHello(Loose):
    worker_id: str = Field(min_length=1, max_length=120)
    engines: list[str]
    hostname: str | None = None
    gpu_name: str | None = None
    gpu_vram_gb: float | None = None
    version: str | None = None


class WorkerProgress(Loose):
    worker_id: str
    progress: float | None = None
    log: str | None = None


class WorkerFailure(Loose):
    worker_id: str
    error: str
    log: str | None = None
    retryable: bool = True


# --------------------------------------------------------------------------- ingest API
class IngestRetailer(Loose):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str | None = None
    website_url: str | None = None
    city: str | None = None


class IngestPrice(Loose):
    outcome: ObservationOutcome = ObservationOutcome.success
    price_pkr: Decimal | None = Field(default=None, ge=0)
    compare_at_price_pkr: Decimal | None = Field(default=None, ge=0)
    sale_unit: SaleUnit | None = None
    availability: Availability = Availability.unknown
    includes_delivery: bool | None = None
    source_url: str | None = None
    checked_at: datetime
    failure_reason: str | None = None
    raw_payload: dict | None = None


class IngestImage(Loose):
    url: HttpUrl
    view_angle: ViewAngle = ViewAngle.unknown
    role: ImageRole = ImageRole.gallery
    depicts_variant: bool | None = None


class IngestVariant(Loose):
    variant_key: str = "default"
    variant_label: str | None = None
    configuration: str = "standard"
    listing_url: str | None = None
    sale_unit: SaleUnit | None = None
    sale_unit_quantity: int | None = Field(default=None, ge=1)
    placement_type: PlacementType | None = None
    dimensions: DimensionIn | None = None
    price: IngestPrice | None = None
    attributes: list[AttributeIn] = []
    room_uses: list[RoomUseIn] = []
    set_components: list[SetComponentIn] = []
    images: list[IngestImage] = Field(default=[], max_length=12)

    @field_validator("attributes")
    @classmethod
    def _api_attributes_unverified(cls, v: list[AttributeIn]) -> list[AttributeIn]:
        # Values pushed by software are recorded but a curator verifies them.
        for a in v:
            if a.source == AttributeSource.curator.value:
                a.source = AttributeSource.listing.value
            a.verified = False
        return v


class IngestProduct(Loose):
    retailer: IngestRetailer
    external_ref: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1)
    brand: str | None = None
    category_code: str | None = None
    description: str | None = None
    listing_url: str | None = None
    retailer_product_ref: str | None = None
    variants: list[IngestVariant] = Field(min_length=1, max_length=50)
