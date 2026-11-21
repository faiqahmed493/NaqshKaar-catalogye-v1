"""Catalogue admission conditions (SRS §5.6, FR-CAT-009, FR-CAT-010).

`evaluate(facts)` lists every condition with pass/fail and a reason, so the curator
sees all omissions at once (FR-CAT-010 scenario 1). A variant becomes eligible only
when every *required* condition passes and a human approves (DEC-CAT-01).
Asset readiness is deliberately NOT a condition here: eligibility and asset
qualification are separate states.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


@dataclass
class DimensionFacts:
    kind: str | None = None
    width_m: Decimal | None = None
    depth_m: Decimal | None = None
    height_m: Decimal | None = None
    source_ref: str | None = None
    source_text: str | None = None


@dataclass
class PriceFacts:
    price_pkr: Decimal | None = None
    sale_unit: str | None = None
    availability: str = "unknown"
    source_url: str | None = None
    checked_at: datetime | None = None


@dataclass
class ImageFacts:
    reviewed: bool = False
    depicts_variant: bool | None = None


@dataclass
class VariantFacts:
    retailer_name: str | None
    product_name: str | None
    variant_label: str | None
    sibling_variant_count: int
    category_code: str | None
    category_supported: bool
    category_is_group_only: bool
    room_use_count: int
    sale_unit: str | None
    sale_unit_quantity: int | None
    listing_url: str | None
    latest_link_check_url: str | None
    latest_link_check_outcome: str | None
    dimension: DimensionFacts | None
    price: PriceFacts | None
    images: list[ImageFacts] = field(default_factory=list)
    set_component_count: int = 0
    set_components_missing_dims: int = 0


@dataclass
class ConditionResult:
    code: str
    label: str
    passed: bool
    required: bool
    detail: str
    srs: str

    def as_dict(self) -> dict:
        return asdict(self)


def _ok(code, label, srs, detail="OK", required=True) -> ConditionResult:
    return ConditionResult(code, label, True, required, detail, srs)


def _no(code, label, srs, detail, required=True) -> ConditionResult:
    return ConditionResult(code, label, False, required, detail, srs)


def evaluate(f: VariantFacts, *, now: datetime | None = None, price_stale_days: int = 30) -> list[ConditionResult]:
    now = now or datetime.now(timezone.utc)
    out: list[ConditionResult] = []

    # 1. distinguishable retailer variant
    label = "Retailer variant is identifiable"
    if not f.retailer_name or not (f.product_name or "").strip():
        out.append(_no("variant_identity", label, "FR-CAT-001, FR-CAT-002", "Retailer or product name is missing."))
    elif f.sibling_variant_count > 1 and not (f.variant_label or "").strip():
        out.append(_no("variant_identity", label, "FR-CAT-001, FR-CAT-002",
                       "This product has several variants; give this one a label (size, colour, finish)."))
    else:
        out.append(_ok("variant_identity", label, "FR-CAT-001, FR-CAT-002"))

    # 2. supported category
    label = "Supported category"
    if not f.category_code:
        out.append(_no("category_supported", label, "§5.6, FR-RET-003", "No category set."))
    elif not f.category_supported:
        out.append(_no("category_supported", label, "§5.6, FR-RET-003", f"Category '{f.category_code}' is not supported."))
    elif f.category_is_group_only:
        out.append(_no("category_supported", label, "§5.6, FR-RET-003",
                       f"'{f.category_code}' is a top-level group; choose a specific category."))
    else:
        out.append(_ok("category_supported", label, "§5.6, FR-RET-003"))

    # 3. intended use
    label = "Intended room use recorded"
    out.append(_ok("intended_use", label, "FR-RET-003") if f.room_use_count > 0 else
               _no("intended_use", label, "FR-RET-003", "Add at least one room type this product is meant for."))

    # 4. price
    label = "PKR price recorded"
    if f.price is None:
        out.append(_no("price_known", label, "FR-CAT-003", "No successful price observation."))
    elif f.price.price_pkr is None:
        out.append(_no("price_known", label, "FR-CAT-003", "Latest observation has no price; it is never treated as zero."))
    elif f.price.price_pkr < 0:
        out.append(_no("price_known", label, "FR-CAT-003", "Price is negative."))
    else:
        out.append(_ok("price_known", label, "FR-CAT-003", f"PKR {f.price.price_pkr:,.2f}"))

    # 5. sale unit
    label = "Sale unit is unambiguous"
    if not f.sale_unit:
        out.append(_no("sale_unit_clear", label, "FR-CAT-003, DR-PROD-002", "Say what one price buys: single, set, pair or pack."))
    elif f.sale_unit != "single" and not f.sale_unit_quantity:
        out.append(_no("sale_unit_clear", label, "FR-CAT-003, DR-PROD-002",
                       f"Sale unit '{f.sale_unit}' needs the number of items it contains."))
    elif f.price is not None and f.price.sale_unit and f.price.sale_unit != f.sale_unit:
        out.append(_no("sale_unit_clear", label, "FR-CAT-003, DR-PROD-002",
                       f"Price was observed for '{f.price.sale_unit}' but the variant is '{f.sale_unit}'."))
    else:
        out.append(_ok("sale_unit_clear", label, "FR-CAT-003, DR-PROD-002"))

    # 6. source-backed assembled dimensions
    label = "Assembled W × D × H, source-backed"
    d = f.dimension
    if d is None:
        out.append(_no("dimensions_assembled", label, "FR-CAT-004, DEC-CAT-02", "No dimensions recorded."))
    else:
        missing = [n for n, v in (("width", d.width_m), ("depth", d.depth_m), ("height", d.height_m)) if not v or v <= 0]
        if d.kind != "assembled":
            out.append(_no("dimensions_assembled", label, "FR-CAT-004, DEC-CAT-02",
                           f"Dimensions are '{d.kind}'. Packaging sizes and estimates do not qualify."))
        elif missing:
            out.append(_no("dimensions_assembled", label, "FR-CAT-004, DEC-CAT-02", f"Missing: {', '.join(missing)}."))
        elif not (d.source_ref or d.source_text):
            out.append(_no("dimensions_assembled", label, "FR-CAT-004, DEC-CAT-02",
                           "Record where the dimensions came from (listing text or URL)."))
        else:
            out.append(_ok("dimensions_assembled", label, "FR-CAT-004, DEC-CAT-02",
                           f"{d.width_m} × {d.depth_m} × {d.height_m} m"))

    # 7. image
    label = "Reviewed image of this variant"
    good = [i for i in f.images if i.reviewed and i.depicts_variant]
    if good:
        out.append(_ok("image_usable", label, "FR-CAT-006", f"{len(good)} reviewed image(s)"))
    elif f.images:
        out.append(_no("image_usable", label, "FR-CAT-006",
                       "Images exist but none is reviewed as depicting this variant."))
    else:
        out.append(_no("image_usable", label, "FR-CAT-006", "No images uploaded."))

    # 8. purchase link
    label = "Purchase link checked and matching"
    if not f.listing_url:
        out.append(_no("purchase_link_checked", label, "FR-CAT-008", "No listing URL."))
    elif f.latest_link_check_url != f.listing_url or f.latest_link_check_outcome is None:
        out.append(_no("purchase_link_checked", label, "FR-CAT-008", "The current listing URL has not been checked."))
    elif f.latest_link_check_outcome != "ok":
        out.append(_no("purchase_link_checked", label, "FR-CAT-008",
                       f"Last check result: {f.latest_link_check_outcome}."))
    else:
        out.append(_ok("purchase_link_checked", label, "FR-CAT-008"))

    # 9. dated source evidence
    label = "Dated source evidence for the price"
    if f.price is None or f.price.checked_at is None:
        out.append(_no("dated_source_evidence", label, "FR-CAT-011", "No dated observation."))
    elif not f.price.source_url:
        out.append(_no("dated_source_evidence", label, "FR-CAT-011", "Observation has no source URL."))
    else:
        out.append(_ok("dated_source_evidence", label, "FR-CAT-011", f"Checked {f.price.checked_at:%Y-%m-%d}"))

    # 10. orderable
    label = "Not known to be unorderable"
    avail = f.price.availability if f.price else "unknown"
    if avail in ("discontinued", "out_of_stock"):
        out.append(_no("orderable", label, "§5.6", f"Latest observation says '{avail}'."))
    else:
        detail = "Pre-order (disclosed)" if avail == "preorder" else ("Stock unknown" if avail == "unknown" else "In stock")
        out.append(_ok("orderable", label, "§5.6", detail))

    # 11. set composition
    label = "Set contents recorded"
    if f.sale_unit in ("set", "pair", "pack"):
        if f.set_component_count == 0:
            out.append(_no("set_composition", label, "DR-PROD-002", "List the items the set contains and their quantities."))
        else:
            out.append(_ok("set_composition", label, "DR-PROD-002", f"{f.set_component_count} component line(s)"))
        if f.set_components_missing_dims:
            out.append(_no("set_component_dimensions", "Set component dimensions", "DR-PROD-002",
                           f"{f.set_components_missing_dims} component(s) lack W × D × H; needed before layout placement.",
                           required=False))
    else:
        out.append(_ok("set_composition", label, "DR-PROD-002", "Single item"))

    # 12. advisory: price age
    if f.price is not None and f.price.checked_at is not None:
        age = (now - f.price.checked_at).days
        if age > price_stale_days:
            out.append(_no("price_recent", "Price observation is recent", "FR-CAT-012, BR-COST-05",
                           f"Last checked {age} days ago; consider a refresh.", required=False))
    return out


def all_required_pass(results: list[ConditionResult]) -> bool:
    return all(r.passed for r in results if r.required)


def failed_required(results: list[ConditionResult]) -> list[ConditionResult]:
    return [r for r in results if r.required and not r.passed]
