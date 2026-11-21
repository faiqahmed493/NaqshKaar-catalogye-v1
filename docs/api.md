# API

Interactive documentation: **http://localhost:8000/docs** (OpenAPI). This page summarises the parts other
software talks to.

## Authentication

| Caller | Header | How to get it |
|---|---|---|
| Web UI / people | `Authorization: Bearer <jwt>` | `POST /api/auth/login` |
| Collector software | `X-API-Key: nqk_…` (scope `ingest`) | Settings → API keys |
| 3D workers | `X-API-Key: nqk_…` (scope `worker`) | Settings → API keys |
| Naqshkaar planner | `X-API-Key: nqk_…` (scope `catalogue_read`) | Settings → API keys |

Files come from `GET /api/files/{id}?exp=…&sig=…`: signed links that expire, so no header is needed.
Links in responses are relative; prefix them with the API host.

## Ingest API

`POST /api/ingest/products`: one product. `POST /api/ingest/products/batch`: up to 50, each succeeds or fails alone.

```json
{
  "retailer": {"slug": "example-furniture-pk", "name": "Example Furniture PK", "website_url": "https://…"},
  "external_ref": "your-stable-id-for-this-listing",
  "name": "Oslo Sofa",
  "brand": "Example", "category_code": "sofa", "description": "…",
  "listing_url": "https://…/oslo-sofa", "retailer_product_ref": "OSL-3S",
  "variants": [{
    "variant_key": "OSL-3S-GRY", "variant_label": "3-seater · grey", "configuration": "standard",
    "listing_url": null, "sale_unit": "single", "sale_unit_quantity": 1, "placement_type": null,
    "dimensions": {
      "kind": "assembled",
      "width":  {"value": 84, "unit": "in"},
      "depth":  {"value": 36, "unit": "in"},
      "height": {"value": 2, "unit": "ft_in", "inches": 8},
      "source_text": "W 84 x D 36 x H 32 inches", "source_ref": "https://…#specs"
    },
    "price": {"price_pkr": 189000, "availability": "in_stock", "checked_at": "2026-10-24T10:00:00+05:00",
              "source_url": "https://…"},
    "attributes": [{"key": "colour", "value": "grey"}, {"key": "material", "value": "fabric"}],
    "room_uses": [{"room_type": "living_room", "use_tag": "seating"}],
    "set_components": [],
    "images": [{"url": "https://…/front.jpg", "view_angle": "front", "role": "primary"}]
  }]
}
```

Rules:
- Every field except `retailer.slug`, `external_ref`, `name` and one variant is optional. Leave unknowns out.
- Units are required per value: `m`, `cm`, `mm`, `in`, `ft`, or `ft_in` with `inches`.
- `kind` must be `assembled` for the variant to be admissible; send `packaging` or `estimate` only to record them.
- A failed price check: `{"outcome": "failed", "failure_reason": "page timed out", "checked_at": "…"}`.
- `category_code` values come from `GET /api/categories` (e.g. `bed`, `sofa`, `study_chair`, `dining_set`, `floor_lamp`, `rug`).
- `room_type`: `bedroom`, `living_room`, `study`, `dining_room`.
- `view_angle`: `front`, `back`, `left`, `right`, `top`, `three_quarter`, `unknown`.
- `sale_unit`: `single`, `set`, `pair`, `pack` (sets need `set_components` before admission).

Response: `{product_id, created, variants: [{id, variant_key, status}], price_observations, dimension_revisions, images_added, images_skipped, image_errors}`.

Other ingest endpoints:
- `POST /api/ingest/variants/{variant_id}/price-observations`: refresh a price only.
- `POST /api/ingest/variants/{variant_id}/images`: multipart upload of image files (`files`, `view_angle`, `role`).

## Catalogue API (for the planner)

`GET /api/catalogue/variants`

| Query | Default | Meaning |
|---|---|---|
| `eligible_only` | true | only admitted variants |
| `asset_ready` | any | true = has a qualified asset for its current dimensions |
| `room_type`, `category` | — | filters |
| `max_price_pkr`, `max_width_m`, `max_depth_m`, `max_height_m` | — | hard-filter helpers |
| `limit`, `offset` | 100, 0 | paging |

Each item: `variant_id, product_name, variant_label, retailer_name, category_code, product_group, placement_type,
sale_unit, sale_unit_quantity, listing_url, dimension_id, dimension_revision, width_m, depth_m, height_m,
price_pkr, availability, price_checked_at, price_observation_id, eligible, asset_ready, asset_id, glb_url`.

`GET /api/catalogue/variants/{id}` adds `attributes`, `room_uses` and `set_components`.

A planner should store `dimension_id`, `price_observation_id` and `asset_id` with a design revision: they
identify exactly which observation, revision and asset version the design was verified with.

## Worker protocol

All with a `worker` key. See `generator/naqshkaar_generator/client.py` for a complete client.

| Call | Body | Returns |
|---|---|---|
| `POST /api/worker/hello` | `{worker_id, engines[], hostname, gpu_name, gpu_vram_gb, version}` | registration |
| `POST /api/worker/claim` | same as hello | `204` or a job: `{job_id, engine, params, inputs[{url, view_angle, position}], target_dimensions_m, product}` |
| `POST /api/worker/jobs/{id}/progress` | `{worker_id, progress, log}` | `{status, cancel}`; stop work when `cancel` is true |
| `POST /api/worker/jobs/{id}/result` | multipart `file` (GLB), `worker_id`, `meta` (JSON) | `{asset_id}` |
| `POST /api/worker/jobs/{id}/fail` | `{worker_id, error, log, retryable}` | `{status}` (re-queued until `max_attempts`) |

Claims use `SELECT … FOR UPDATE SKIP LOCKED`, so any number of workers can poll safely. A job whose worker sends
no heartbeat for `JOB_STALE_MINUTES` goes back to the queue.

## Studio endpoints (used by the UI)

| Area | Endpoints |
|---|---|
| Auth and admin | `POST /api/auth/login`, `GET /api/auth/me`, `GET/POST/PATCH /api/users`, `GET/POST /api/api-keys`, `POST /api/api-keys/{id}/revoke` |
| Reference | `GET/POST/PATCH /api/retailers`, `GET /api/categories`, `GET /api/engines`, `PATCH /api/engines/{code}` |
| Products | `GET/POST /api/products`, `GET/PATCH/DELETE /api/products/{id}`, `POST /api/products/{id}/variants`, `POST /api/products/{id}/images`, `PATCH/DELETE /api/images/{id}` |
| Variants | `GET/PATCH/DELETE /api/variants/{id}`, `POST …/dimensions`, `POST …/price-observations`, `POST …/link-checks`, `PUT …/attributes`, `PUT …/room-uses`, `PUT …/set-components` |
| Admission | `GET …/admission`, `POST …/submit`, `POST …/admission-reviews`, `POST …/publish`, `POST …/retire` |
| 3D | `POST /api/variants/{id}/generation-jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `POST /api/jobs/{id}/retry`, `POST /api/variants/{id}/assets` (upload GLB), `GET /api/assets/{id}`, `POST /api/assets/{id}/reprocess`, `POST /api/assets/{id}/review`, `POST /api/assets/{id}/select`, `POST /api/assets/{id}/preview` |
| Other | `GET /api/stats`, `GET /api/audit`, `GET /api/health` |
