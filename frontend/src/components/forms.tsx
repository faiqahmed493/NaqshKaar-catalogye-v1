// Reusable form pieces: dimension entry with explicit units, price entry, image upload.
import { useRef, useState, type DragEvent } from "react";
import { UNIT_LABELS } from "../format";
import type { Availability, ImageRole, Length, LengthUnit, SaleUnit, ViewAngle } from "../types";
import { Field } from "./ui";

export interface DimensionDraft {
  kind: "assembled" | "packaging" | "estimate";
  unit: LengthUnit;
  width: string; widthIn: string;
  depth: string; depthIn: string;
  height: string; heightIn: string;
  source_text: string;
  source_ref: string;
}

export const emptyDims = (): DimensionDraft => ({
  kind: "assembled", unit: "cm", width: "", widthIn: "", depth: "", depthIn: "", height: "", heightIn: "",
  source_text: "", source_ref: "",
});

function length(v: string, inches: string, unit: LengthUnit): Length | null {
  if (!v.trim()) return null;
  return unit === "ft_in" ? { value: v.trim(), unit, inches: inches.trim() || "0" } : { value: v.trim(), unit };
}

/** Body for POST /variants/{id}/dimensions, or null when nothing was entered. */
export function dimsPayload(d: DimensionDraft) {
  const width = length(d.width, d.widthIn, d.unit);
  const depth = length(d.depth, d.depthIn, d.unit);
  const height = length(d.height, d.heightIn, d.unit);
  if (!width && !depth && !height) return null;
  return { kind: d.kind, width, depth, height, source_text: d.source_text || null, source_ref: d.source_ref || null };
}

export function DimensionEditor({ value, onChange }: { value: DimensionDraft; onChange: (d: DimensionDraft) => void }) {
  const set = (k: keyof DimensionDraft, v: string) => onChange({ ...value, [k]: v });
  const ftin = value.unit === "ft_in";
  const axis = (label: string, k: "width" | "depth" | "height") => (
    <Field label={label}>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input inputMode="decimal" value={value[k]} onChange={(e) => set(k, e.target.value)} placeholder={ftin ? "ft" : value.unit} />
        {ftin && <input inputMode="decimal" value={value[`${k}In` as const]} onChange={(e) => set(`${k}In` as keyof DimensionDraft, e.target.value)} placeholder="in" />}
      </div>
    </Field>
  );
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="grid-4">
        {axis("Width (side to side)", "width")}
        {axis("Depth (front to back)", "depth")}
        {axis("Height", "height")}
        <Field label="Unit">
          <select value={value.unit} onChange={(e) => set("unit", e.target.value)}>
            {(Object.keys(UNIT_LABELS) as LengthUnit[]).map((u) => <option key={u} value={u}>{UNIT_LABELS[u]}</option>)}
          </select>
        </Field>
      </div>
      <div className="grid-3">
        <Field label="What the numbers describe">
          <select value={value.kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="assembled">Assembled product (required for the catalogue)</option>
            <option value="packaging">Packaging / box size</option>
            <option value="estimate">Estimate</option>
          </select>
        </Field>
        <Field label="Listing text" hint="copy exactly as printed">
          <input value={value.source_text} onChange={(e) => set("source_text", e.target.value)} placeholder="W 72 x D 36 x H 30 in" />
        </Field>
        <Field label="Source" hint="URL or page section">
          <input value={value.source_ref} onChange={(e) => set("source_ref", e.target.value)} placeholder="Specifications table" />
        </Field>
      </div>
    </div>
  );
}

export interface PriceDraft {
  price_pkr: string; sale_unit: SaleUnit | ""; availability: Availability; source_url: string; checked_at: string;
}

export const emptyPrice = (): PriceDraft => ({
  price_pkr: "", sale_unit: "", availability: "unknown", source_url: "", checked_at: new Date().toISOString().slice(0, 16),
});

export function pricePayload(p: PriceDraft) {
  if (!p.price_pkr.trim()) return null;
  return {
    price_pkr: p.price_pkr.replace(/,/g, "").trim(), sale_unit: p.sale_unit || null, availability: p.availability,
    source_url: p.source_url || null, checked_at: p.checked_at ? new Date(p.checked_at).toISOString() : null,
  };
}

export function PriceEditor({ value, onChange }: { value: PriceDraft; onChange: (p: PriceDraft) => void }) {
  const set = <K extends keyof PriceDraft>(k: K, v: PriceDraft[K]) => onChange({ ...value, [k]: v });
  return (
    <div className="grid-4">
      <Field label="Price (PKR)"><input inputMode="decimal" value={value.price_pkr} onChange={(e) => set("price_pkr", e.target.value)} placeholder="125000" /></Field>
      <Field label="Price buys">
        <select value={value.sale_unit} onChange={(e) => set("sale_unit", e.target.value as SaleUnit | "")}>
          <option value="">Same as variant</option><option value="single">One item</option><option value="set">A set</option>
          <option value="pair">A pair</option><option value="pack">A pack</option>
        </select>
      </Field>
      <Field label="Availability">
        <select value={value.availability} onChange={(e) => set("availability", e.target.value as Availability)}>
          <option value="unknown">Unknown</option><option value="in_stock">In stock</option><option value="preorder">Pre-order</option>
          <option value="out_of_stock">Out of stock</option><option value="discontinued">Discontinued</option>
        </select>
      </Field>
      <Field label="Checked at"><input type="datetime-local" value={value.checked_at} onChange={(e) => set("checked_at", e.target.value)} /></Field>
      <div style={{ gridColumn: "1 / -1" }}>
        <Field label="Price source URL" hint="defaults to the listing link">
          <input value={value.source_url} onChange={(e) => set("source_url", e.target.value)} placeholder="https://…" />
        </Field>
      </div>
    </div>
  );
}

export const VIEW_ANGLES: ViewAngle[] = ["front", "three_quarter", "left", "right", "back", "top", "unknown"];
export const IMAGE_ROLES: ImageRole[] = ["primary", "gallery", "detail", "dimension_diagram", "lifestyle"];

export function ImageDrop({ onFiles, busy }: { onFiles: (files: File[]) => void; busy?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const accept = (list: FileList | null) => {
    const files = Array.from(list ?? []).filter((f) => /\.(png|jpe?g|webp|svg)$/i.test(f.name) || f.type.startsWith("image/"));
    if (files.length) onFiles(files);
  };
  return (
    <div className={`dropzone ${over ? "over" : ""}`} role="button" tabIndex={0}
      onClick={() => ref.current?.click()} onKeyDown={(e) => e.key === "Enter" && ref.current?.click()}
      onDragOver={(e: DragEvent) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => { e.preventDefault(); setOver(false); accept(e.dataTransfer.files); }}>
      <b>{busy ? "Uploading…" : "Drop product images here, or click to choose"}</b>
      <div className="small muted">PNG, JPEG, WebP or SVG · several files at once · clean product shots on a plain background work best</div>
      <input ref={ref} type="file" hidden multiple accept=".png,.jpg,.jpeg,.webp,.svg,image/png,image/jpeg,image/webp,image/svg+xml"
        onChange={(e) => { accept(e.target.files); e.target.value = ""; }} />
    </div>
  );
}
