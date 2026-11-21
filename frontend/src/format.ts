import type { AssetStatus, JobStatus, LengthUnit, VariantStatus } from "./types";

export function pkr(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  return `PKR ${n.toLocaleString("en-PK", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function metres(v: number | null | undefined, digits = 3): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(digits)} m`;
}

export function cm(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)} cm`;
}

export function dims(w?: number | null, d?: number | null, h?: number | null): string {
  if (w == null && d == null && h == null) return "No dimensions";
  const f = (x?: number | null) => (x == null ? "?" : (x * 100).toFixed(1));
  return `${f(w)} × ${f(d)} × ${f(h)} cm`;
}

export function date(s: string | null | undefined): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTime(s: string | null | undefined): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function ago(s: string | null | undefined): string {
  if (!s) return "never";
  const sec = Math.max(0, (Date.now() - new Date(s).getTime()) / 1000);
  if (sec < 60) return `${Math.round(sec)} s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  return `${Math.round(sec / 86400)} d ago`;
}

export function bytes(n: number | null | undefined): string {
  if (!n) return "—";
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const UNIT_LABELS: Record<LengthUnit, string> = { m: "m", cm: "cm", mm: "mm", in: "inches", ft: "feet", ft_in: "ft + in" };

export const VARIANT_STATUS: Record<VariantStatus, { label: string; tone: string }> = {
  draft: { label: "Draft", tone: "neutral" },
  in_review: { label: "In review", tone: "info" },
  eligible: { label: "In catalogue", tone: "good" },
  ineligible: { label: "Ineligible", tone: "bad" },
  reassessing: { label: "Reassessing", tone: "warn" },
  retired: { label: "Retired", tone: "muted" },
};

export const ASSET_STATUS: Record<AssetStatus, { label: string; tone: string }> = {
  processing: { label: "Checking", tone: "info" },
  in_review: { label: "Awaiting review", tone: "warn" },
  needs_correction: { label: "Needs correction", tone: "bad" },
  qualified: { label: "Qualified", tone: "good" },
  rejected: { label: "Rejected", tone: "muted" },
  stale: { label: "Stale (dims changed)", tone: "muted" },
};

export const JOB_STATUS: Record<JobStatus, { label: string; tone: string }> = {
  queued: { label: "Queued", tone: "neutral" },
  claimed: { label: "Claimed", tone: "info" },
  running: { label: "Generating", tone: "info" },
  uploaded: { label: "Uploaded", tone: "info" },
  postprocessing: { label: "Checking", tone: "info" },
  succeeded: { label: "Done", tone: "good" },
  failed: { label: "Failed", tone: "bad" },
  cancelled: { label: "Cancelled", tone: "muted" },
};

export const ACTIVE_JOBS: JobStatus[] = ["queued", "claimed", "running", "uploaded", "postprocessing"];

export const ROOM_LABELS: Record<string, string> = {
  bedroom: "Bedroom", living_room: "Drawing / living room", study: "Study", dining_room: "Dining room",
};

export const CHECK_LABELS: Record<string, string> = {
  file_readable: "File opens",
  geometry_finite: "Finite coordinates",
  geometry_non_degenerate: "Non-degenerate extents",
  dimensions_available: "Recorded W × D × H available",
  extent_width: "Width within tolerance",
  extent_depth: "Depth within tolerance",
  extent_height: "Height within tolerance",
  scale_distortion: "Proportions match product",
  glb_reload: "Exported GLB re-opens",
  embedded_resources: "Textures embedded (self-contained)",
  gltf_validator: "Khronos glTF validator",
  triangle_budget: "Triangle budget",
  visual_review: "Visual review by a person",
};
