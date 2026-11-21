"""Python mirrors of the PostgreSQL enum types in sql/0001_initial_schema.sql.
Keep both in sync: the database is the source of truth."""
from enum import Enum

from sqlalchemy.dialects.postgresql import ENUM


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class UserRole(StrEnum):
    admin = "admin"
    curator = "curator"
    asset_reviewer = "asset_reviewer"
    viewer = "viewer"


class RecordSource(StrEnum):
    manual = "manual"
    api = "api"
    csv_import = "csv_import"


class RoomType(StrEnum):
    bedroom = "bedroom"
    living_room = "living_room"
    study = "study"
    dining_room = "dining_room"


class PlacementType(StrEnum):
    floor = "floor"
    wall = "wall"
    tabletop = "tabletop"
    ceiling = "ceiling"


class ProductGroup(StrEnum):
    furniture = "furniture"
    lighting = "lighting"
    planter = "planter"
    decor = "decor"


class VariantStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    eligible = "eligible"
    ineligible = "ineligible"
    reassessing = "reassessing"
    retired = "retired"


class SaleUnit(StrEnum):
    single = "single"
    set = "set"
    pair = "pair"
    pack = "pack"


class LengthUnit(StrEnum):
    m = "m"
    cm = "cm"
    mm = "mm"
    inch = "in"
    ft = "ft"
    ft_in = "ft_in"


class DimensionKind(StrEnum):
    assembled = "assembled"
    packaging = "packaging"
    estimate = "estimate"


class Availability(StrEnum):
    in_stock = "in_stock"
    out_of_stock = "out_of_stock"
    preorder = "preorder"
    discontinued = "discontinued"
    unknown = "unknown"


class ObservationOutcome(StrEnum):
    success = "success"
    failed = "failed"


class AttributeKey(StrEnum):
    style = "style"
    colour = "colour"
    material = "material"
    finish = "finish"


class AttributeSource(StrEnum):
    listing = "listing"
    curator = "curator"
    model_suggested = "model_suggested"


class ImageRole(StrEnum):
    primary = "primary"
    gallery = "gallery"
    detail = "detail"
    dimension_diagram = "dimension_diagram"
    lifestyle = "lifestyle"


class ViewAngle(StrEnum):
    front = "front"
    back = "back"
    left = "left"
    right = "right"
    top = "top"
    three_quarter = "three_quarter"
    unknown = "unknown"


class LinkCheckOutcome(StrEnum):
    ok = "ok"
    mismatch = "mismatch"
    unreachable = "unreachable"


class ReviewDecision(StrEnum):
    approve = "approve"
    reject = "reject"
    request_changes = "request_changes"


class EngineKind(StrEnum):
    local_gpu = "local_gpu"
    external_api = "external_api"
    cpu = "cpu"


class JobStatus(StrEnum):
    queued = "queued"
    claimed = "claimed"
    running = "running"
    uploaded = "uploaded"
    postprocessing = "postprocessing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


ACTIVE_JOB_STATUSES = (JobStatus.queued, JobStatus.claimed, JobStatus.running,
                       JobStatus.uploaded, JobStatus.postprocessing)


class AssetOrigin(StrEnum):
    generated = "generated"
    manual_upload = "manual_upload"
    corrected = "corrected"


class AssetStatus(StrEnum):
    processing = "processing"
    in_review = "in_review"
    needs_correction = "needs_correction"
    qualified = "qualified"
    rejected = "rejected"
    stale = "stale"


class CheckOutcome(StrEnum):
    pass_ = "pass"
    fail = "fail"
    warn = "warn"
    not_run = "not_run"


class AssetDecision(StrEnum):
    approve = "approve"
    needs_correction = "needs_correction"
    reject = "reject"


def pg_enum(enum_cls: type[Enum], name: str) -> ENUM:
    """Map a Python enum onto an existing PostgreSQL enum type (never created by SQLAlchemy)."""
    return ENUM(*[e.value for e in enum_cls], name=name, create_type=False)
