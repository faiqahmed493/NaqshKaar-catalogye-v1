"""SQLAlchemy ORM mapping of sql/0001_initial_schema.sql.

The SQL migration owns the schema (types, constraints, views); these classes only
map it. When you change a table, change the SQL migration first, then mirror it here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Boolean, CHAR, REAL, DateTime, ForeignKey, Integer, Numeric,
                        SmallInteger, Text, func)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import (AssetDecision, AssetOrigin, AssetStatus, AttributeKey, AttributeSource, Availability,
                    CheckOutcome, DimensionKind, EngineKind, ImageRole, JobStatus, LengthUnit,
                    LinkCheckOutcome, ObservationOutcome, PlacementType, ProductGroup, RecordSource,
                    ReviewDecision, RoomType, SaleUnit, UserRole, VariantStatus, ViewAngle, pg_enum)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def user_fk(nullable: bool = True) -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=nullable)


# --------------------------------------------------------------------------- people
class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.curator.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    __tablename__ = "api_key"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoredFile(Base):
    __tablename__ = "stored_file"
    id: Mapped[uuid.UUID] = uuid_pk()
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()


# --------------------------------------------------------------------------- reference
class Retailer(Base):
    __tablename__ = "retailer"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(CHAR(2), nullable=False, default="PK")
    contact_notes: Mapped[str | None] = mapped_column(Text)
    usage_terms: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Category(Base):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    product_group: Mapped[str] = mapped_column(pg_enum(ProductGroup, "product_group"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("category.id"))
    default_placement: Mapped[str | None] = mapped_column(pg_enum(PlacementType, "placement_type"))
    is_planar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# --------------------------------------------------------------------------- products
class Product(Base):
    __tablename__ = "product"
    id: Mapped[uuid.UUID] = uuid_pk()
    retailer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("retailer.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("category.id"))
    description: Mapped[str | None] = mapped_column(Text)
    listing_url: Mapped[str | None] = mapped_column(Text)
    retailer_product_ref: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(pg_enum(RecordSource, "record_source"), nullable=False,
                                        default=RecordSource.manual.value)
    external_ref: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    retailer: Mapped[Retailer] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan",
                                                            order_by="ProductVariant.created_at")
    images: Mapped[list["ProductImage"]] = relationship(back_populates="product", cascade="all, delete-orphan",
                                                        order_by=lambda: [ProductImage.sort_order,
                                                                          ProductImage.created_at])


class ProductVariant(Base):
    __tablename__ = "product_variant"
    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
                                                  nullable=False)
    variant_key: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    variant_label: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[str] = mapped_column(Text, nullable=False, default="standard")
    listing_url: Mapped[str | None] = mapped_column(Text)
    sale_unit: Mapped[str | None] = mapped_column(pg_enum(SaleUnit, "sale_unit_kind"))
    sale_unit_quantity: Mapped[int | None] = mapped_column(Integer)
    sale_unit_note: Mapped[str | None] = mapped_column(Text)
    placement_type: Mapped[str | None] = mapped_column(pg_enum(PlacementType, "placement_type"))
    status: Mapped[str] = mapped_column(pg_enum(VariantStatus, "variant_status"), nullable=False,
                                        default=VariantStatus.draft.value)
    status_reason: Mapped[str | None] = mapped_column(Text)
    dimension_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eligible_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product: Mapped[Product] = relationship(back_populates="variants")
    room_uses: Mapped[list["VariantRoomUse"]] = relationship(cascade="all, delete-orphan")
    attributes: Mapped[list["VariantAttribute"]] = relationship(cascade="all, delete-orphan",
                                                                order_by="VariantAttribute.key")
    dimensions: Mapped[list["VariantDimension"]] = relationship(cascade="all, delete-orphan",
                                                                order_by="VariantDimension.revision.desc()")
    set_components: Mapped[list["SetComponent"]] = relationship(cascade="all, delete-orphan",
                                                                order_by="SetComponent.sort_order")


class VariantRoomUse(Base):
    __tablename__ = "variant_room_use"
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"),
                                                  primary_key=True)
    room_type: Mapped[str] = mapped_column(pg_enum(RoomType, "room_type"), primary_key=True)
    use_tag: Mapped[str] = mapped_column(Text, primary_key=True, default="general")


class VariantAttribute(Base):
    __tablename__ = "variant_attribute"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(pg_enum(AttributeKey, "attribute_key"), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    colour_hex: Mapped[str | None] = mapped_column(CHAR(7))
    source: Mapped[str] = mapped_column(pg_enum(AttributeSource, "attribute_source"), nullable=False,
                                        default=AttributeSource.curator.value)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(REAL)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()


class VariantDimension(Base):
    __tablename__ = "variant_dimension"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(pg_enum(DimensionKind, "dimension_kind"), nullable=False,
                                      default=DimensionKind.assembled.value)
    width_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    depth_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    height_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    entered_unit: Mapped[str | None] = mapped_column(pg_enum(LengthUnit, "length_unit"))
    entered_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_text: Mapped[str | None] = mapped_column(Text)
    source_axis_order: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()


class PriceObservation(Base):
    __tablename__ = "price_observation"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    outcome: Mapped[str] = mapped_column(pg_enum(ObservationOutcome, "observation_outcome"), nullable=False,
                                         default=ObservationOutcome.success.value)
    price_pkr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    compare_at_price_pkr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sale_unit: Mapped[str | None] = mapped_column(pg_enum(SaleUnit, "sale_unit_kind"))
    availability: Mapped[str] = mapped_column(pg_enum(Availability, "availability_status"), nullable=False,
                                              default=Availability.unknown.value)
    includes_delivery: Mapped[bool | None] = mapped_column(Boolean)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(pg_enum(RecordSource, "record_source"), nullable=False,
                                             default=RecordSource.manual.value)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recorded_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()


class LinkCheck(Base):
    __tablename__ = "link_check"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(pg_enum(LinkCheckOutcome, "link_check_outcome"), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[uuid.UUID | None] = user_fk()
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SetComponent(Base):
    __tablename__ = "set_component"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("category.id", ondelete="SET NULL"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    width_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    depth_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    height_m: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProductImage(Base):
    __tablename__ = "product_image"
    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
                                                  nullable=False)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         ForeignKey("product_variant.id", ondelete="CASCADE"))
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"), nullable=False)
    processed_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"))
    thumbnail_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"))
    original_format: Mapped[str] = mapped_column(Text, nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(pg_enum(ImageRole, "image_role"), nullable=False,
                                      default=ImageRole.gallery.value)
    view_angle: Mapped[str] = mapped_column(pg_enum(ViewAngle, "view_angle"), nullable=False,
                                            default=ViewAngle.unknown.value)
    depicts_variant: Mapped[bool | None] = mapped_column(Boolean)
    usable_for_3d: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[uuid.UUID | None] = user_fk()
    source_url: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()

    product: Mapped[Product] = relationship(back_populates="images")
    file: Mapped[StoredFile] = relationship(foreign_keys=[file_id], lazy="joined")


class AdmissionReview(Base):
    __tablename__ = "admission_review"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)
    decision: Mapped[str] = mapped_column(pg_enum(ReviewDecision, "review_decision"), nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    dimension_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("variant_dimension.id"))
    price_observation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                                   ForeignKey("price_observation.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


# --------------------------------------------------------------------------- generation
class GenerationEngine(Base):
    __tablename__ = "generation_engine"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(pg_enum(EngineKind, "engine_kind"), nullable=False)
    license: Mapped[str] = mapped_column(Text, nullable=False)
    is_open_source: Mapped[bool] = mapped_column(Boolean, nullable=False)
    commercial_use_note: Mapped[str | None] = mapped_column(Text)
    supports_multi_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_input_images: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    required_views: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    supports_texture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_vram_gb: Mapped[int | None] = mapped_column(SmallInteger)
    default_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GenerationWorker(Base):
    __tablename__ = "generation_worker"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    engines: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    hostname: Mapped[str | None] = mapped_column(Text)
    gpu_name: Mapped[str | None] = mapped_column(Text)
    gpu_vram_gb: Mapped[float | None] = mapped_column(REAL)
    version: Mapped[str | None] = mapped_column(Text)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_key.id"))
    first_seen_at: Mapped[datetime] = created_at_col()
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GenerationJob(Base):
    __tablename__ = "generation_job"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    engine_code: Mapped[str] = mapped_column(Text, ForeignKey("generation_engine.code"), nullable=False)
    status: Mapped[str] = mapped_column(pg_enum(JobStatus, "job_status"), nullable=False,
                                        default=JobStatus.queued.value)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dimension_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("variant_dimension.id"))
    requested_by: Mapped[uuid.UUID | None] = user_fk()
    worker_id: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    progress: Mapped[float | None] = mapped_column(REAL)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_output_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"))
    result_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_3d.id"))
    runtime_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    log: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    engine: Mapped[GenerationEngine] = relationship(lazy="joined")
    inputs: Mapped[list["JobInputImage"]] = relationship(cascade="all, delete-orphan",
                                                         order_by="JobInputImage.position")


class JobInputImage(Base):
    __tablename__ = "job_input_image"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("generation_job.id", ondelete="CASCADE"),
                                              primary_key=True)
    image_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("product_image.id", ondelete="CASCADE"),
                                                primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    image: Mapped[ProductImage] = relationship(lazy="joined")


class Asset3D(Base):
    __tablename__ = "asset_3d"
    id: Mapped[uuid.UUID] = uuid_pk()
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                  ForeignKey("product_variant.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(pg_enum(AssetOrigin, "asset_origin"), nullable=False)
    engine_code: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_engine.code"))
    generation_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("generation_job.id"))
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_3d.id"))
    dimension_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("variant_dimension.id"))
    source_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"), nullable=False)
    glb_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"))
    preview_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stored_file.id"))
    status: Mapped[str] = mapped_column(pg_enum(AssetStatus, "asset_status"), nullable=False,
                                        default=AssetStatus.processing.value)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orientation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False,
                                                        default=lambda: {"rotation_deg": [0, 0, 0], "auto_yaw": True})
    native_extents: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scaled_extents_m: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scale_factors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    triangle_count: Mapped[int | None] = mapped_column(Integer)
    vertex_count: Mapped[int | None] = mapped_column(Integer)
    texture_count: Mapped[int | None] = mapped_column(Integer)
    glb_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualified_by: Mapped[uuid.UUID | None] = user_fk()
    created_by: Mapped[uuid.UUID | None] = user_fk()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    checks: Mapped[list["AssetCheck"]] = relationship(cascade="all, delete-orphan", order_by="AssetCheck.code")
    reviews: Mapped[list["AssetReview"]] = relationship(cascade="all, delete-orphan",
                                                        order_by="AssetReview.created_at.desc()")


class AssetCheck(Base):
    __tablename__ = "asset_check"
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_3d.id", ondelete="CASCADE"),
                                                nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(pg_enum(CheckOutcome, "check_outcome"), nullable=False)
    measured: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    threshold: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    checked_by: Mapped[uuid.UUID | None] = user_fk()
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssetReview(Base):
    __tablename__ = "asset_review"
    id: Mapped[uuid.UUID] = uuid_pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_3d.id", ondelete="CASCADE"),
                                                nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)
    decision: Mapped[str] = mapped_column(pg_enum(AssetDecision, "asset_decision"), nullable=False)
    checklist: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[uuid.UUID | None] = user_fk()
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_key.id"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
