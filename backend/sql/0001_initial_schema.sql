-- =============================================================================
-- Naqshkaar Catalogue Studio — initial schema
-- Basis: Naqshkaar SRS Draft 0.2 (§3.2 FR-CAT, §3.5 FR-3D, §5 data requirements,
--        §5.6 admission conditions, §6.1 NFR-ACC-002, §6.2 asset quality)
--
-- Design rules encoded here
--   * A retailer VARIANT is the unit of identity (FR-CAT-001). Price, dimensions,
--     images and purchase link always refer to one variant.
--   * Prices are dated observations, never a column on the variant (FR-CAT-011,
--     BR-COST-05). A failed refresh is its own row and never advances the last
--     successful check time.
--   * Dimensions are revisioned (dimension_revision). A 3D asset is qualified
--     against exactly one dimension revision (FR-3D-005, DR-ASSET-001).
--   * Unknown facts are NULL, never zero or a category default (DEC-CAT-02).
--   * Catalogue eligibility and asset qualification are separate states.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive email / slugs

-- -----------------------------------------------------------------------------
-- Enumerations
-- -----------------------------------------------------------------------------
CREATE TYPE user_role           AS ENUM ('admin', 'curator', 'asset_reviewer', 'viewer');
CREATE TYPE record_source       AS ENUM ('manual', 'api', 'csv_import');
CREATE TYPE room_type           AS ENUM ('bedroom', 'living_room', 'study', 'dining_room');
CREATE TYPE placement_type      AS ENUM ('floor', 'wall', 'tabletop', 'ceiling');
CREATE TYPE product_group       AS ENUM ('furniture', 'lighting', 'planter', 'decor');
CREATE TYPE variant_status      AS ENUM ('draft', 'in_review', 'eligible', 'ineligible', 'reassessing', 'retired');
CREATE TYPE sale_unit_kind      AS ENUM ('single', 'set', 'pair', 'pack');
CREATE TYPE length_unit         AS ENUM ('m', 'cm', 'mm', 'in', 'ft', 'ft_in');
CREATE TYPE dimension_kind      AS ENUM ('assembled', 'packaging', 'estimate');
CREATE TYPE availability_status AS ENUM ('in_stock', 'out_of_stock', 'preorder', 'discontinued', 'unknown');
CREATE TYPE observation_outcome AS ENUM ('success', 'failed');
CREATE TYPE attribute_key       AS ENUM ('style', 'colour', 'material', 'finish');
CREATE TYPE attribute_source    AS ENUM ('listing', 'curator', 'model_suggested');
CREATE TYPE image_role          AS ENUM ('primary', 'gallery', 'detail', 'dimension_diagram', 'lifestyle');
CREATE TYPE view_angle          AS ENUM ('front', 'back', 'left', 'right', 'top', 'three_quarter', 'unknown');
CREATE TYPE link_check_outcome  AS ENUM ('ok', 'mismatch', 'unreachable');
CREATE TYPE review_decision     AS ENUM ('approve', 'reject', 'request_changes');
CREATE TYPE engine_kind         AS ENUM ('local_gpu', 'external_api', 'cpu');
CREATE TYPE job_status          AS ENUM ('queued', 'claimed', 'running', 'uploaded', 'postprocessing',
                                         'succeeded', 'failed', 'cancelled');
CREATE TYPE asset_origin        AS ENUM ('generated', 'manual_upload', 'corrected');
CREATE TYPE asset_status        AS ENUM ('processing', 'in_review', 'needs_correction', 'qualified', 'rejected', 'stale');
CREATE TYPE check_outcome       AS ENUM ('pass', 'fail', 'warn', 'not_run');
CREATE TYPE asset_decision      AS ENUM ('approve', 'needs_correction', 'reject');

-- -----------------------------------------------------------------------------
-- Shared trigger: keep updated_at current
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- -----------------------------------------------------------------------------
-- People and machine credentials
-- -----------------------------------------------------------------------------
CREATE TABLE app_user (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          citext NOT NULL UNIQUE,
  display_name   text NOT NULL,
  password_hash  text NOT NULL,
  role           user_role NOT NULL DEFAULT 'curator',
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  last_login_at  timestamptz
);
CREATE TRIGGER trg_app_user_updated BEFORE UPDATE ON app_user FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Keys for the collector software (scope ingest), GPU workers (worker) and the
-- Naqshkaar planner reading the catalogue (catalogue_read). Only a hash is kept.
CREATE TABLE api_key (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  prefix        text NOT NULL UNIQUE,
  key_hash      text NOT NULL,
  scopes        text[] NOT NULL DEFAULT '{}',
  created_by    uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  CONSTRAINT api_key_scopes_valid CHECK (scopes <@ ARRAY['ingest', 'worker', 'catalogue_read']::text[])
);

-- -----------------------------------------------------------------------------
-- File registry (local disk or S3/MinIO; see STORAGE_BACKEND)
-- -----------------------------------------------------------------------------
CREATE TABLE stored_file (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  storage_key        text NOT NULL UNIQUE,
  mime_type          text NOT NULL,
  size_bytes         bigint NOT NULL CHECK (size_bytes >= 0),
  sha256             char(64) NOT NULL,
  original_filename  text,
  created_by         uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_stored_file_sha256 ON stored_file (sha256);

-- -----------------------------------------------------------------------------
-- Reference data
-- -----------------------------------------------------------------------------
CREATE TABLE retailer (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text NOT NULL,
  slug           citext NOT NULL UNIQUE,
  website_url    text,
  city           text,
  country        char(2) NOT NULL DEFAULT 'PK',
  contact_notes  text,
  usage_terms    text,            -- permission notes for images / listing data
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT retailer_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$')
);
CREATE TRIGGER trg_retailer_updated BEFORE UPDATE ON retailer FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE category (
  id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code               citext NOT NULL UNIQUE,
  name               text NOT NULL,
  product_group      product_group NOT NULL,
  parent_id          integer REFERENCES category(id) ON DELETE RESTRICT,
  default_placement  placement_type,
  is_planar          boolean NOT NULL DEFAULT false,  -- rugs etc. need a thin-volume representation (SRS §7.2)
  is_supported       boolean NOT NULL DEFAULT true,
  sort_order         integer NOT NULL DEFAULT 0
);

-- -----------------------------------------------------------------------------
-- Products and variants
-- -----------------------------------------------------------------------------
-- A product is the retailer listing family; variants are the purchasable things.
CREATE TABLE product (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_id            uuid NOT NULL REFERENCES retailer(id) ON DELETE RESTRICT,
  name                   text NOT NULL CHECK (length(btrim(name)) > 0),
  brand                  text,
  category_id            integer REFERENCES category(id) ON DELETE RESTRICT,
  description            text,
  listing_url            text,
  retailer_product_ref   text,            -- retailer SKU / product code if shown
  source                 record_source NOT NULL DEFAULT 'manual',
  external_ref           text,            -- collector's stable id, makes ingest idempotent
  created_by             uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT product_external_ref_unique UNIQUE (retailer_id, external_ref)
);
CREATE INDEX ix_product_retailer ON product (retailer_id);
CREATE INDEX ix_product_category ON product (category_id);
CREATE INDEX ix_product_name_lower ON product (lower(name));
CREATE TRIGGER trg_product_updated BEFORE UPDATE ON product FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE product_variant (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id          uuid NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  variant_key         text NOT NULL DEFAULT 'default',   -- retailer variant SKU or code
  variant_label       text,                               -- e.g. "3-seater · grey velvet"
  configuration       text NOT NULL DEFAULT 'standard',   -- e.g. closed / extended (DR-PROD-002)
  listing_url         text,                               -- variant-specific link; falls back to product
  sale_unit           sale_unit_kind,                     -- NULL = not yet established
  sale_unit_quantity  integer CHECK (sale_unit_quantity > 0),
  sale_unit_note      text,
  placement_type      placement_type,
  status              variant_status NOT NULL DEFAULT 'draft',
  status_reason       text,
  dimension_revision  integer NOT NULL DEFAULT 0,          -- mirrors the current variant_dimension.revision
  eligible_since      timestamptz,
  notes               text,
  created_by          uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT variant_identity_unique UNIQUE (product_id, variant_key, configuration),
  CONSTRAINT variant_eligible_has_since CHECK (status <> 'eligible' OR eligible_since IS NOT NULL)
);
CREATE INDEX ix_variant_product ON product_variant (product_id);
CREATE INDEX ix_variant_status ON product_variant (status);
CREATE TRIGGER trg_variant_updated BEFORE UPDATE ON product_variant FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Intended use per room type (FR-RET-003). A variant without one is not compatible.
CREATE TABLE variant_room_use (
  variant_id  uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  room_type   room_type NOT NULL,
  use_tag     text NOT NULL DEFAULT 'general',            -- e.g. study_chair, dining_seating
  PRIMARY KEY (variant_id, room_type, use_tag)
);

-- Descriptive attributes; absent means unknown (FR-CAT-007).
CREATE TABLE variant_attribute (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id  uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  key         attribute_key NOT NULL,
  value       text NOT NULL CHECK (length(btrim(value)) > 0),
  colour_hex  char(7) CHECK (colour_hex IS NULL OR colour_hex ~ '^#[0-9A-Fa-f]{6}$'),
  source      attribute_source NOT NULL DEFAULT 'curator',
  verified    boolean NOT NULL DEFAULT false,              -- model suggestions start unverified
  confidence  real CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  created_by  uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT variant_attribute_unique UNIQUE (variant_id, key, value)
);

-- Revisioned, source-backed dimensions (FR-CAT-004, FR-CAT-005).
CREATE TABLE variant_dimension (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id        uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  revision          integer NOT NULL CHECK (revision > 0),
  kind              dimension_kind NOT NULL DEFAULT 'assembled',
  width_m           numeric(9, 4) CHECK (width_m  IS NULL OR width_m  > 0),
  depth_m           numeric(9, 4) CHECK (depth_m  IS NULL OR depth_m  > 0),
  height_m          numeric(9, 4) CHECK (height_m IS NULL OR height_m > 0),
  entered_unit      length_unit,
  entered_values    jsonb NOT NULL DEFAULT '{}'::jsonb,     -- {"width": {"value": 72, "unit": "in"}, ...}
  source_text       text,                                   -- raw listing text, e.g. "W72 x D36 x H30 in"
  source_axis_order text,                                   -- e.g. "H x W x D" as printed by the retailer
  source_ref        text,                                   -- URL or page section the values came from
  observed_at       timestamptz,
  is_current        boolean NOT NULL DEFAULT false,
  note              text,
  recorded_by       uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT variant_dimension_revision_unique UNIQUE (variant_id, revision)
);
CREATE UNIQUE INDEX ux_variant_dimension_current ON variant_dimension (variant_id) WHERE is_current;

-- Dated price and availability observations (FR-CAT-003, FR-CAT-011, FR-CAT-012).
CREATE TABLE price_observation (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id            uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  outcome               observation_outcome NOT NULL DEFAULT 'success',
  price_pkr             numeric(12, 2) CHECK (price_pkr IS NULL OR price_pkr >= 0),
  compare_at_price_pkr  numeric(12, 2) CHECK (compare_at_price_pkr IS NULL OR compare_at_price_pkr >= 0),
  sale_unit             sale_unit_kind,                      -- what this price buys, as stated by the source
  availability          availability_status NOT NULL DEFAULT 'unknown',
  includes_delivery     boolean,                             -- NULL = not stated
  source_url            text,
  source_kind           record_source NOT NULL DEFAULT 'manual',
  checked_at            timestamptz NOT NULL,
  failure_reason        text,
  raw_payload           jsonb,
  recorded_by           uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT price_failed_has_reason CHECK (outcome = 'success' OR failure_reason IS NOT NULL),
  CONSTRAINT price_failed_has_no_price CHECK (outcome = 'success' OR price_pkr IS NULL)
);
CREATE INDEX ix_price_variant_checked ON price_observation (variant_id, checked_at DESC);

-- Purchase-link checks: "matching" is a human judgement; reachability can be automated.
CREATE TABLE link_check (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id   uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  url          text NOT NULL,
  outcome      link_check_outcome NOT NULL,
  http_status  integer,
  note         text,
  checked_by   uuid REFERENCES app_user(id) ON DELETE SET NULL,
  checked_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_link_check_variant ON link_check (variant_id, checked_at DESC);

-- Contents of a set sale unit (DR-PROD-002): placed separately, charged once.
CREATE TABLE set_component (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id   uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  name         text NOT NULL,
  category_id  integer REFERENCES category(id) ON DELETE SET NULL,
  quantity     integer NOT NULL CHECK (quantity > 0),
  width_m      numeric(9, 4) CHECK (width_m  IS NULL OR width_m  > 0),
  depth_m      numeric(9, 4) CHECK (depth_m  IS NULL OR depth_m  > 0),
  height_m     numeric(9, 4) CHECK (height_m IS NULL OR height_m > 0),
  notes        text,
  sort_order   integer NOT NULL DEFAULT 0
);
CREATE INDEX ix_set_component_variant ON set_component (variant_id);

-- Product images. variant_id NULL = shared by every variant of the product.
CREATE TABLE product_image (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id         uuid NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  variant_id         uuid REFERENCES product_variant(id) ON DELETE CASCADE,
  file_id            uuid NOT NULL REFERENCES stored_file(id) ON DELETE RESTRICT,   -- original upload
  processed_file_id  uuid REFERENCES stored_file(id) ON DELETE SET NULL,            -- normalised PNG (SVG rasterised)
  thumbnail_file_id  uuid REFERENCES stored_file(id) ON DELETE SET NULL,
  original_format    text NOT NULL CHECK (original_format IN ('png', 'jpeg', 'webp', 'svg')),
  width_px           integer CHECK (width_px > 0),
  height_px          integer CHECK (height_px > 0),
  role               image_role NOT NULL DEFAULT 'gallery',
  view_angle         view_angle NOT NULL DEFAULT 'unknown',
  depicts_variant    boolean,                               -- NULL = not reviewed yet
  usable_for_3d      boolean NOT NULL DEFAULT true,
  reviewed           boolean NOT NULL DEFAULT false,
  reviewed_by        uuid REFERENCES app_user(id) ON DELETE SET NULL,
  source_url         text,
  sort_order         integer NOT NULL DEFAULT 0,
  created_by         uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_image_product ON product_image (product_id);
CREATE INDEX ix_image_variant ON product_image (variant_id);

-- -----------------------------------------------------------------------------
-- Catalogue admission reviews (FR-CAT-009, FR-CAT-010, DEC-CAT-01)
-- -----------------------------------------------------------------------------
CREATE TABLE admission_review (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id            uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  reviewer_id           uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  decision              review_decision NOT NULL,
  conditions            jsonb NOT NULL,                 -- snapshot of every admission condition at review time
  dimension_id          uuid REFERENCES variant_dimension(id) ON DELETE SET NULL,
  price_observation_id  uuid REFERENCES price_observation(id) ON DELETE SET NULL,
  comment               text,
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_admission_review_variant ON admission_review (variant_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 3D generation engines, workers and jobs
-- -----------------------------------------------------------------------------
CREATE TABLE generation_engine (
  code                  text PRIMARY KEY CHECK (code ~ '^[a-z0-9_]+$'),
  display_name          text NOT NULL,
  kind                  engine_kind NOT NULL,
  license               text NOT NULL,
  is_open_source        boolean NOT NULL,
  commercial_use_note   text,
  supports_multi_image  boolean NOT NULL DEFAULT false,
  max_input_images      smallint NOT NULL DEFAULT 1 CHECK (max_input_images >= 1),
  required_views        text[],                          -- e.g. {front,left,back} for multiview engines
  supports_texture      boolean NOT NULL DEFAULT true,
  min_vram_gb           smallint,
  default_params        jsonb NOT NULL DEFAULT '{}'::jsonb,
  homepage_url          text,
  notes                 text,
  is_enabled            boolean NOT NULL DEFAULT true,
  sort_order            integer NOT NULL DEFAULT 0
);

CREATE TABLE generation_worker (
  id            text PRIMARY KEY,
  engines       text[] NOT NULL DEFAULT '{}',
  hostname      text,
  gpu_name      text,
  gpu_vram_gb   real,
  version       text,
  api_key_id    uuid REFERENCES api_key(id) ON DELETE SET NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE generation_job (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id          uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  engine_code         text NOT NULL REFERENCES generation_engine(code) ON DELETE RESTRICT,
  status              job_status NOT NULL DEFAULT 'queued',
  params              jsonb NOT NULL DEFAULT '{}'::jsonb,
  priority            smallint NOT NULL DEFAULT 0,
  dimension_id        uuid REFERENCES variant_dimension(id) ON DELETE SET NULL,  -- dimensions at request time
  requested_by        uuid REFERENCES app_user(id) ON DELETE SET NULL,
  worker_id           text,
  attempts            smallint NOT NULL DEFAULT 0,
  max_attempts        smallint NOT NULL DEFAULT 2 CHECK (max_attempts >= 1),
  progress            real CHECK (progress IS NULL OR (progress >= 0 AND progress <= 100)),
  claimed_at          timestamptz,
  started_at          timestamptz,
  heartbeat_at        timestamptz,
  finished_at         timestamptz,
  raw_output_file_id  uuid REFERENCES stored_file(id) ON DELETE SET NULL,
  result_asset_id     uuid,                                  -- FK added below (asset_3d)
  runtime_meta        jsonb NOT NULL DEFAULT '{}'::jsonb,     -- seconds, peak VRAM, engine version
  error_message       text,
  log                 text NOT NULL DEFAULT '',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_job_queue ON generation_job (status, engine_code, priority DESC, created_at);
CREATE INDEX ix_job_variant ON generation_job (variant_id, created_at DESC);
CREATE TRIGGER trg_job_updated BEFORE UPDATE ON generation_job FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE job_input_image (
  job_id    uuid NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE,
  image_id  uuid NOT NULL REFERENCES product_image(id) ON DELETE CASCADE,
  position  smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (job_id, image_id)
);

-- -----------------------------------------------------------------------------
-- 3D assets and qualification evidence (FR-3D-002..006, §6.2, DR-ASSET-001)
-- -----------------------------------------------------------------------------
CREATE TABLE asset_3d (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id            uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
  version               integer NOT NULL CHECK (version > 0),
  origin                asset_origin NOT NULL,
  engine_code           text REFERENCES generation_engine(code) ON DELETE SET NULL,
  generation_job_id     uuid REFERENCES generation_job(id) ON DELETE SET NULL,
  parent_asset_id       uuid REFERENCES asset_3d(id) ON DELETE SET NULL,   -- correction lineage
  dimension_id          uuid REFERENCES variant_dimension(id) ON DELETE CASCADE,   -- revision qualified against
  source_file_id        uuid NOT NULL REFERENCES stored_file(id) ON DELETE RESTRICT, -- raw engine output / upload
  glb_file_id           uuid REFERENCES stored_file(id) ON DELETE SET NULL,          -- metric, embedded GLB
  preview_file_id       uuid REFERENCES stored_file(id) ON DELETE SET NULL,
  status                asset_status NOT NULL DEFAULT 'processing',
  is_selected           boolean NOT NULL DEFAULT false,      -- the asset the catalogue serves for this variant
  orientation           jsonb NOT NULL DEFAULT '{"rotation_deg": [0, 0, 0], "auto_yaw": true}'::jsonb,
  native_extents        jsonb,                               -- {"x":..,"y":..,"z":..} before scaling
  scaled_extents_m      jsonb,                               -- {"width":..,"depth":..,"height":..}
  scale_factors         jsonb,
  triangle_count        integer,
  vertex_count          integer,
  texture_count         integer,
  glb_size_bytes        bigint,
  processing_started_at timestamptz,
  processing_error      text,
  qualified_at          timestamptz,
  qualified_by          uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_by            uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT asset_version_unique UNIQUE (variant_id, version),
  CONSTRAINT asset_selected_is_qualified CHECK (NOT is_selected OR status = 'qualified'),
  CONSTRAINT asset_qualified_has_glb CHECK (status <> 'qualified' OR (glb_file_id IS NOT NULL AND dimension_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_asset_selected ON asset_3d (variant_id) WHERE is_selected;
CREATE INDEX ix_asset_processing ON asset_3d (status, processing_started_at) WHERE status = 'processing';
CREATE TRIGGER trg_asset_updated BEFORE UPDATE ON asset_3d FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE generation_job
  ADD CONSTRAINT generation_job_result_asset_fk
  FOREIGN KEY (result_asset_id) REFERENCES asset_3d(id) ON DELETE SET NULL;

CREATE TABLE asset_check (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id    uuid NOT NULL REFERENCES asset_3d(id) ON DELETE CASCADE,
  code        text NOT NULL,
  outcome     check_outcome NOT NULL,
  measured    jsonb,
  threshold   jsonb,
  message     text,
  checked_by  uuid REFERENCES app_user(id) ON DELETE SET NULL,   -- NULL = automated
  checked_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT asset_check_unique UNIQUE (asset_id, code)
);

CREATE TABLE asset_review (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id     uuid NOT NULL REFERENCES asset_3d(id) ON DELETE CASCADE,
  reviewer_id  uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  decision     asset_decision NOT NULL,
  checklist    jsonb NOT NULL DEFAULT '{}'::jsonb,
  comment      text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_asset_review_asset ON asset_review (asset_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Audit trail
-- -----------------------------------------------------------------------------
CREATE TABLE audit_log (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_user_id      uuid REFERENCES app_user(id) ON DELETE SET NULL,
  actor_api_key_id   uuid REFERENCES api_key(id) ON DELETE SET NULL,
  action             text NOT NULL,
  entity_type        text NOT NULL,
  entity_id          text NOT NULL,
  details            jsonb,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Read views
-- -----------------------------------------------------------------------------
-- Latest successful observation per variant. A later failed refresh never
-- replaces it (FR-CAT-011 scenario 2).
CREATE VIEW v_latest_price AS
SELECT DISTINCT ON (po.variant_id)
       po.variant_id, po.id AS price_observation_id, po.price_pkr, po.compare_at_price_pkr,
       po.sale_unit, po.availability, po.includes_delivery, po.source_url, po.checked_at
FROM price_observation po
WHERE po.outcome = 'success'
ORDER BY po.variant_id, po.checked_at DESC, po.created_at DESC;

CREATE VIEW v_latest_link_check AS
SELECT DISTINCT ON (lc.variant_id)
       lc.variant_id, lc.id AS link_check_id, lc.url, lc.outcome, lc.http_status, lc.checked_at
FROM link_check lc
ORDER BY lc.variant_id, lc.checked_at DESC;

-- What the Naqshkaar planner may read. eligible and asset_ready are separate
-- flags because catalogue admission does not imply a qualified asset.
CREATE VIEW v_catalogue_variant AS
SELECT v.id                          AS variant_id,
       p.id                          AS product_id,
       p.name                        AS product_name,
       v.variant_label,
       v.variant_key,
       v.configuration,
       r.id                          AS retailer_id,
       r.name                        AS retailer_name,
       c.code                        AS category_code,
       c.product_group,
       COALESCE(v.placement_type, c.default_placement) AS placement_type,
       v.sale_unit,
       v.sale_unit_quantity,
       COALESCE(v.listing_url, p.listing_url) AS listing_url,
       d.id                          AS dimension_id,
       d.revision                    AS dimension_revision,
       d.width_m, d.depth_m, d.height_m,
       lp.price_pkr, lp.availability, lp.checked_at AS price_checked_at, lp.price_observation_id,
       v.status,
       (v.status = 'eligible')       AS eligible,
       a.id                          AS asset_id,
       a.glb_file_id,
       (a.id IS NOT NULL)            AS asset_ready
FROM product_variant v
JOIN product p            ON p.id = v.product_id
JOIN retailer r           ON r.id = p.retailer_id
LEFT JOIN category c      ON c.id = p.category_id
LEFT JOIN variant_dimension d ON d.variant_id = v.id AND d.is_current
LEFT JOIN v_latest_price lp   ON lp.variant_id = v.id
LEFT JOIN asset_3d a      ON a.variant_id = v.id AND a.is_selected AND a.status = 'qualified'
                         AND a.dimension_id = d.id;
