// Shapes returned by the studio API (backend/app/serializers.py).

export type Role = "admin" | "curator" | "asset_reviewer" | "viewer";
export type VariantStatus = "draft" | "in_review" | "eligible" | "ineligible" | "reassessing" | "retired";
export type AssetStatus = "processing" | "in_review" | "needs_correction" | "qualified" | "rejected" | "stale";
export type JobStatus =
  | "queued" | "claimed" | "running" | "uploaded" | "postprocessing" | "succeeded" | "failed" | "cancelled";
export type LengthUnit = "m" | "cm" | "mm" | "in" | "ft" | "ft_in";
export type ViewAngle = "front" | "back" | "left" | "right" | "top" | "three_quarter" | "unknown";
export type ImageRole = "primary" | "gallery" | "detail" | "dimension_diagram" | "lifestyle";
export type RoomType = "bedroom" | "living_room" | "study" | "dining_room";
export type SaleUnit = "single" | "set" | "pair" | "pack";
export type Availability = "in_stock" | "out_of_stock" | "preorder" | "discontinued" | "unknown";

export interface User { id: string; email: string; display_name: string; role: Role; is_active: boolean; last_login_at: string | null }
export interface Retailer { id: string; name: string; slug: string; website_url: string | null; city: string | null; country: string; contact_notes: string | null; usage_terms: string | null; is_active: boolean }
export interface Category { id: number; code: string; name: string; product_group: string; parent_id: number | null; default_placement: string | null; is_planar: boolean; is_supported: boolean }

export interface Dimension {
  id: string; revision: number; kind: "assembled" | "packaging" | "estimate";
  width_m: number | null; depth_m: number | null; height_m: number | null;
  entered_unit: LengthUnit | null; entered_values: Record<string, { value: string; unit: LengthUnit; inches?: string }>;
  source_text: string | null; source_axis_order: string | null; source_ref: string | null;
  observed_at: string | null; is_current: boolean; note: string | null; created_at: string;
}
export interface PriceObservation {
  id: string; outcome: "success" | "failed"; price_pkr: string | null; compare_at_price_pkr: string | null;
  sale_unit: SaleUnit | null; availability: Availability; includes_delivery: boolean | null; source_url: string | null;
  source_kind: string; checked_at: string; failure_reason: string | null;
}
export interface LinkCheck { id: string; url: string; outcome: "ok" | "mismatch" | "unreachable"; http_status: number | null; note: string | null; checked_at: string }
export interface ProductImage {
  id: string; product_id: string; variant_id: string | null; original_format: string; width_px: number; height_px: number;
  role: ImageRole; view_angle: ViewAngle; depicts_variant: boolean | null; usable_for_3d: boolean; reviewed: boolean;
  source_url: string | null; sort_order: number; original_url: string; processed_url: string; thumbnail_url: string;
  filename: string | null; created_at: string;
}
export interface Engine {
  code: string; display_name: string; kind: string; license: string; is_open_source: boolean;
  commercial_use_note: string | null; supports_multi_image: boolean; max_input_images: number; required_views: string[];
  supports_texture: boolean; min_vram_gb: number | null; default_params: Record<string, unknown>; homepage_url: string | null;
  notes: string | null; is_enabled: boolean; online_workers: number;
}
export interface Worker { id: string; engines: string[]; hostname: string | null; gpu_name: string | null; gpu_vram_gb: number | null; version: string | null; last_seen_at: string }
export interface Job {
  id: string; variant_id: string; engine_code: string; engine_name: string; status: JobStatus; params: Record<string, unknown>;
  priority: number; worker_id: string | null; attempts: number; max_attempts: number; progress: number | null;
  error_message: string | null; result_asset_id: string | null; input_image_ids: string[]; runtime_meta: Record<string, unknown>;
  created_at: string; claimed_at: string | null; started_at: string | null; finished_at: string | null; heartbeat_at: string | null;
  log?: string; product_name?: string; variant_label?: string | null;
}
export interface AssetCheck { code: string; outcome: "pass" | "fail" | "warn" | "not_run"; message: string | null; measured: unknown; threshold: unknown; by_person: boolean; checked_at: string }
export interface Asset {
  id: string; variant_id: string; version: number; origin: "generated" | "manual_upload" | "corrected"; engine_code: string | null;
  generation_job_id: string | null; parent_asset_id: string | null; dimension_id: string | null;
  checked_against_current_dimensions: boolean; status: AssetStatus; is_selected: boolean;
  orientation: { rotation_deg: number[]; auto_yaw: boolean; auto_yaw_applied_deg?: number };
  native_extents: { x: number; y: number; z: number } | null;
  scaled_extents_m: { width: number; depth: number; height: number } | null;
  scale_factors: Record<string, number> | null; triangle_count: number | null; vertex_count: number | null;
  texture_count: number | null; glb_size_bytes: number | null; processing_error: string | null;
  glb_url: string | null; source_url: string | null; preview_url: string | null; qualified_at: string | null; created_at: string;
  checks: AssetCheck[]; reviews: { id: string; decision: string; checklist: Record<string, boolean>; comment: string | null; created_at: string }[];
}
export interface Condition { code: string; label: string; passed: boolean; required: boolean; detail: string; srs: string }
export interface VariantSummary {
  id: string; variant_key: string; variant_label: string | null; configuration: string; status: VariantStatus;
  status_reason: string | null; sale_unit: SaleUnit | null; dimension: Dimension | null; latest_price: PriceObservation | null;
  asset_ready: boolean; latest_asset_status: AssetStatus | null; latest_asset_preview_url: string | null;
}
export interface ProductSummary {
  id: string; name: string; brand: string | null; retailer: Retailer; category: Category | null; listing_url: string | null;
  source: string; external_ref: string | null; image_count: number; thumbnail_url: string | null;
  variants: VariantSummary[]; created_at: string; updated_at: string;
}
export interface VariantDetail extends VariantSummary {
  product: {
    id: string; name: string; brand: string | null; description: string | null; listing_url: string | null;
    retailer_product_ref: string | null; retailer: Retailer; category: Category | null; source: string; external_ref: string | null;
    variants: { id: string; variant_label: string | null; variant_key: string; status: VariantStatus }[];
  };
  listing_url: string | null; effective_listing_url: string | null; sale_unit_quantity: number | null;
  sale_unit_note: string | null; placement_type: string | null; notes: string | null; eligible_since: string | null;
  room_uses: { room_type: RoomType; use_tag: string }[];
  attributes: { key: string; value: string; colour_hex: string | null; source: string; verified: boolean; confidence: number | null }[];
  dimensions: Dimension[]; current_dimension_id: string | null; price_observations: PriceObservation[];
  link_checks: LinkCheck[]; set_components: SetComponent[]; images: ProductImage[]; jobs: Job[]; assets: Asset[];
  admission: { conditions: Condition[]; all_required_pass: boolean; reviews: { id: string; decision: string; comment: string | null; created_at: string }[] };
  created_at: string; updated_at: string;
}
export interface SetComponent { id?: string; name: string; category_id: number | null; quantity: number; width_m: number | null; depth_m: number | null; height_m: number | null; notes: string | null }
export interface Length { value: string; unit: LengthUnit; inches?: string }
