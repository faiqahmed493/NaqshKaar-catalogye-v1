"""Unit tests for the pure domain rules. Run with:  cd backend && pytest -q"""
import json
import struct
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest

from app.domain import admission_rules as ar
from app.domain import mesh_math as mm
from app.domain.units import (UnitError, parse_labelled_dimensions, parse_length, parse_ordered_dimensions,
                              to_metres)


# ----------------------------------------------------------------------- units (FR-CAT-005)
def test_inches_to_metres_exact():
    assert to_metres(28, "in") == Decimal("0.7112")


def test_feet_and_inches_not_decimal_feet():
    assert to_metres(5, "ft_in", 6) == Decimal("1.6764")
    assert parse_length("6 ft 8 in") == Decimal("2.0320")
    assert parse_length("6'8\"") == Decimal("2.0320")


def test_equivalent_metric_inputs():
    assert to_metres(1, "m") == to_metres(100, "cm") == to_metres(1000, "mm") == Decimal("1")


def test_bare_number_needs_unit():
    with pytest.raises(UnitError):
        parse_length("12")
    assert parse_length("12", default_unit="ft") == Decimal("3.6576")


def test_negative_or_zero_rejected():
    with pytest.raises(UnitError):
        to_metres(-1, "cm")
    with pytest.raises(UnitError):
        to_metres(0, "cm")


def test_labelled_dimensions_any_order():
    d = parse_labelled_dimensions("Height: 75cm, Width: 120cm, Depth: 60cm")
    assert d == {"height": Decimal("0.75"), "width": Decimal("1.20"), "depth": Decimal("0.60")}


def test_labelled_dimensions_trailing_unit():
    d = parse_labelled_dimensions("W 72 x D 36 x H 30 in")
    assert d["width"] == Decimal("1.8288") and d["depth"] == Decimal("0.9144") and d["height"] == Decimal("0.7620")


def test_unlabelled_dimensions_are_not_guessed():
    assert parse_labelled_dimensions("72 x 36 x 30 in") is None
    d = parse_ordered_dimensions("30 x 72 x 36 in", "H x W x D")
    assert d["height"] == Decimal("0.7620") and d["width"] == Decimal("1.8288")


# ----------------------------------------------------------------------- tolerance (NFR-ACC-002)
def test_tolerance_floor_and_relative():
    assert mm.extent_tolerance_m(0.2) == 0.005           # 1 % of 0.2 m is below the 5 mm floor
    assert mm.extent_tolerance_m(2.0) == pytest.approx(0.02)
    assert mm.within_tolerance(0.305, 0.3) and not mm.within_tolerance(0.306, 0.3)   # 5 mm floor
    assert mm.within_tolerance(0.808, 0.8) and not mm.within_tolerance(0.809, 0.8)   # 1 % of 0.8 m


# ----------------------------------------------------------------------- mesh math
def _box(x, y, z, offset=(0, 0, 0)):
    pts = np.array([[i, j, k] for i in (0, x) for j in (0, y) for k in (0, z)], dtype=float)
    return pts + np.array(offset)


def test_scale_plan_hits_recorded_dimensions():
    verts = _box(2.0, 1.0, 0.5, offset=(3, -1, 7))
    plan = mm.plan_metric_scale(verts, width=0.8, depth=0.6, height=0.9)
    out = mm.apply_transform(verts, plan.matrix)
    ext = mm.extents_by_axis(out)
    assert ext["width"] == pytest.approx(0.8) and ext["depth"] == pytest.approx(0.6)
    assert ext["height"] == pytest.approx(0.9)
    lo, hi = mm.bounds(out)
    assert lo[1] == pytest.approx(0.0)                      # standing on the floor
    assert (lo[0] + hi[0]) / 2 == pytest.approx(0.0)        # centred footprint


def test_degenerate_extent_rejected():
    with pytest.raises(ValueError):
        mm.plan_metric_scale(_box(1, 0, 1), 1, 1, 1)


def test_auto_yaw_swaps_width_and_depth():
    assert mm.choose_yaw_quarter_turns(0.5, 2.0, width=2.0, depth=0.5) == 1
    assert mm.choose_yaw_quarter_turns(2.0, 0.5, width=2.0, depth=0.5) == 0
    assert mm.choose_yaw_quarter_turns(1.0, 1.02, width=0.6, depth=0.6) == 0


def test_rotation_y_quarter_turn():
    r = mm.rotation_matrix_deg(0, 90, 0)
    p = mm.apply_transform(np.array([[1.0, 0, 0]]), r)
    assert np.allclose(p[0], [0, 0, -1])


def _glb(gltf: dict, bin_bytes: bytes = b"") -> bytes:
    j = json.dumps(gltf).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    chunks = struct.pack("<II", len(j), mm.CHUNK_JSON) + j
    if bin_bytes:
        b = bin_bytes + b"\x00" * ((4 - len(bin_bytes) % 4) % 4)
        chunks += struct.pack("<II", len(b), mm.CHUNK_BIN) + b
    return struct.pack("<III", mm.GLB_MAGIC, 2, 12 + len(chunks)) + chunks


def test_glb_embedded_resources():
    good = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}], "images": [{"bufferView": 0}]}
    gltf, _ = mm.parse_glb(_glb(good, b"abcd"))
    assert mm.external_resources(gltf) == []
    bad = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}], "images": [{"uri": "tex.png"}]}
    assert mm.external_resources(mm.parse_glb(_glb(bad, b"abcd"))[0])


def test_glb_bad_magic():
    with pytest.raises(ValueError):
        mm.parse_glb(b"\x00" * 40)


# ----------------------------------------------------------------------- admission (§5.6)
def _complete_facts(**over) -> ar.VariantFacts:
    now = datetime.now(timezone.utc)
    f = ar.VariantFacts(
        retailer_name="Habitt", product_name="Oslo Sofa", variant_label="3-seater grey", sibling_variant_count=2,
        category_code="sofa", category_supported=True, category_is_group_only=False, room_use_count=1,
        sale_unit="single", sale_unit_quantity=1, listing_url="https://example.pk/oslo",
        latest_link_check_url="https://example.pk/oslo", latest_link_check_outcome="ok",
        dimension=ar.DimensionFacts("assembled", Decimal("2.1"), Decimal("0.9"), Decimal("0.8"), "listing spec table"),
        price=ar.PriceFacts(Decimal("125000"), "single", "in_stock", "https://example.pk/oslo", now - timedelta(days=2)),
        images=[ar.ImageFacts(reviewed=True, depicts_variant=True)],
    )
    for k, v in over.items():
        setattr(f, k, v)
    return f


def test_complete_record_passes():
    res = ar.evaluate(_complete_facts())
    assert ar.all_required_pass(res), [r for r in res if not r.passed]


def test_all_omissions_reported_together():
    res = ar.evaluate(_complete_facts(price=None, dimension=ar.DimensionFacts("assembled", Decimal("2"), Decimal("1"), None, "x")))
    codes = {r.code for r in ar.failed_required(res)}
    assert {"price_known", "dimensions_assembled", "dated_source_evidence"} <= codes


def test_missing_price_is_not_zero():
    f = _complete_facts()
    f.price.price_pkr = None
    assert "price_known" in {r.code for r in ar.failed_required(ar.evaluate(f))}


def test_packaging_dimensions_do_not_qualify():
    f = _complete_facts(dimension=ar.DimensionFacts("packaging", Decimal("2"), Decimal("1"), Decimal("1"), "box label"))
    assert "dimensions_assembled" in {r.code for r in ar.failed_required(ar.evaluate(f))}


def test_set_needs_components():
    f = _complete_facts(sale_unit="set", sale_unit_quantity=5)
    f.price.sale_unit = "set"
    assert "set_composition" in {r.code for r in ar.failed_required(ar.evaluate(f))}


def test_unchecked_link_blocks():
    f = _complete_facts(latest_link_check_url="https://example.pk/old")
    assert "purchase_link_checked" in {r.code for r in ar.failed_required(ar.evaluate(f))}


def test_discontinued_blocks_but_preorder_allowed():
    f = _complete_facts()
    f.price.availability = "discontinued"
    assert "orderable" in {r.code for r in ar.failed_required(ar.evaluate(f))}
    f.price.availability = "preorder"
    assert ar.all_required_pass(ar.evaluate(f))


def test_old_price_is_advisory_only():
    f = _complete_facts()
    f.price.checked_at = datetime.now(timezone.utc) - timedelta(days=90)
    res = ar.evaluate(f)
    assert ar.all_required_pass(res)
    assert any(r.code == "price_recent" and not r.passed for r in res)
