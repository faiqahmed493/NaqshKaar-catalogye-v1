import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api";
import { DimensionEditor, PriceEditor, dimsPayload, emptyDims, emptyPrice, pricePayload } from "../../components/forms";
import { ErrorBox, Field } from "../../components/ui";
import { ROOM_LABELS, date, dateTime, dims, pkr } from "../../format";
import type { Category, RoomType, SaleUnit, SetComponent, VariantDetail } from "../../types";
import { useVariantMutation } from "./useVariantMutation";

export default function OverviewTab({ v }: { v: VariantDetail }) {
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api.get<Category[]>("/api/categories") });
  const [form, setForm] = useState({
    name: v.product.name, brand: v.product.brand ?? "", category_id: String(v.product.category?.id ?? ""),
    product_url: v.product.listing_url ?? "", variant_label: v.variant_label ?? "", variant_key: v.variant_key,
    listing_url: v.listing_url ?? "", sale_unit: (v.sale_unit ?? "single") as SaleUnit,
    sale_unit_quantity: v.sale_unit_quantity ?? 1, notes: v.notes ?? "",
  });
  const [rooms, setRooms] = useState<RoomType[]>(v.room_uses.map((r) => r.room_type));
  const [dimDraft, setDimDraft] = useState(emptyDims());
  const [priceDraft, setPriceDraft] = useState(emptyPrice());
  const [components, setComponents] = useState<SetComponent[]>(v.set_components);
  const [attrs, setAttrs] = useState(v.attributes.map((a) => ({ ...a })));

  const save = useVariantMutation(v.id, async () => {
    await api.patch(`/api/products/${v.product.id}`, {
      name: form.name, brand: form.brand || null, category_id: form.category_id ? Number(form.category_id) : null,
      listing_url: form.product_url || null,
    });
    await api.patch(`/api/variants/${v.id}`, {
      variant_label: form.variant_label || null, variant_key: form.variant_key || "default", listing_url: form.listing_url || null,
      sale_unit: form.sale_unit, sale_unit_quantity: form.sale_unit === "single" ? 1 : Number(form.sale_unit_quantity) || null,
      notes: form.notes || null,
    });
    await api.put(`/api/variants/${v.id}/room-uses`, rooms.map((room_type) => ({ room_type, use_tag: "general" })));
    await api.put(`/api/variants/${v.id}/attributes`, attrs.filter((a) => a.value.trim()).map((a) => ({
      key: a.key, value: a.value, colour_hex: a.colour_hex || null, source: a.source, verified: a.verified,
    })));
  });
  const addDims = useVariantMutation(v.id, async () => {
    const body = dimsPayload(dimDraft);
    if (!body) throw new Error("Enter at least one dimension");
    await api.post(`/api/variants/${v.id}/dimensions`, body);
    setDimDraft(emptyDims());
  });
  const addPrice = useVariantMutation(v.id, async () => {
    const body = pricePayload(priceDraft);
    if (!body) throw new Error("Enter a price, or record a failed check instead");
    await api.post(`/api/variants/${v.id}/price-observations`, body);
    setPriceDraft(emptyPrice());
  });
  const failedCheck = useVariantMutation(v.id, (reason: string) =>
    api.post(`/api/variants/${v.id}/price-observations`, { outcome: "failed", failure_reason: reason }));
  const saveComponents = useVariantMutation(v.id, () =>
    api.put(`/api/variants/${v.id}/set-components`, components.filter((c) => c.name.trim())));

  const current = v.dimensions.find((d) => d.is_current);
  const leaves = (categories.data ?? []).filter((c) => c.parent_id);
  return (
    <div className="split">
      <div className="stack">
        <section className="card card-pad stack">
          <div className="row between"><h2>Listing and variant</h2>
            <button className="btn primary" onClick={() => save.mutate(undefined)} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</button>
          </div>
          <ErrorBox error={save.error} />
          {v.status === "eligible" && <div className="notice">This variant is in the catalogue. Changing the link, sale unit or category sends it back for reassessment.</div>}
          <div className="grid-3">
            <Field label="Product name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Brand"><input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} /></Field>
            <Field label="Category">
              <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
                <option value="">Not set</option>
                {leaves.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.product_group})</option>)}
              </select>
            </Field>
            <Field label="Variant label"><input value={form.variant_label} onChange={(e) => setForm({ ...form, variant_label: e.target.value })} /></Field>
            <Field label="Variant code"><input value={form.variant_key} onChange={(e) => setForm({ ...form, variant_key: e.target.value })} /></Field>
            <Field label="Price buys">
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <select value={form.sale_unit} onChange={(e) => setForm({ ...form, sale_unit: e.target.value as SaleUnit })}>
                  <option value="single">One item</option><option value="set">A set</option><option value="pair">A pair</option><option value="pack">A pack</option>
                </select>
                {form.sale_unit !== "single" && <input style={{ width: 80 }} inputMode="numeric" value={form.sale_unit_quantity}
                  onChange={(e) => setForm({ ...form, sale_unit_quantity: Number(e.target.value) || 1 })} aria-label="items" />}
              </div>
            </Field>
          </div>
          <div className="grid-2">
            <Field label="Product listing URL"><input value={form.product_url} onChange={(e) => setForm({ ...form, product_url: e.target.value })} /></Field>
            <Field label="Variant-specific URL" hint="optional"><input value={form.listing_url} onChange={(e) => setForm({ ...form, listing_url: e.target.value })} /></Field>
          </div>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>Meant for</div>
            <div className="row">{(Object.keys(ROOM_LABELS) as RoomType[]).map((r) => (
              <label key={r} className="check"><input type="checkbox" checked={rooms.includes(r)}
                onChange={(e) => setRooms(e.target.checked ? [...rooms, r] : rooms.filter((x) => x !== r))} />{ROOM_LABELS[r]}</label>
            ))}</div>
          </div>
          <div>
            <div className="row between"><div className="label">Attributes</div>
              <button className="btn small" onClick={() => setAttrs([...attrs, { key: "style", value: "", colour_hex: null, source: "curator", verified: true, confidence: null }])}>Add attribute</button>
            </div>
            {attrs.length === 0 && <div className="small muted">None recorded. Unknown attributes stay unknown.</div>}
            {attrs.map((a, i) => (
              <div className="row" key={i} style={{ marginTop: 6, flexWrap: "nowrap" }}>
                <select style={{ width: 120 }} value={a.key} onChange={(e) => setAttrs(attrs.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}>
                  <option value="style">Style</option><option value="colour">Colour</option><option value="material">Material</option><option value="finish">Finish</option>
                </select>
                <input value={a.value} onChange={(e) => setAttrs(attrs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                <label className="check small" style={{ whiteSpace: "nowrap" }}><input type="checkbox" checked={a.verified}
                  onChange={(e) => setAttrs(attrs.map((x, j) => (j === i ? { ...x, verified: e.target.checked } : x)))} />verified</label>
                <button className="btn small ghost" onClick={() => setAttrs(attrs.filter((_, j) => j !== i))} aria-label="remove">✕</button>
              </div>
            ))}
          </div>
        </section>

        <section className="card card-pad stack">
          <h2>Add a dimension revision</h2>
          <p className="small muted" style={{ margin: 0 }}>A new revision makes existing 3D assets stale, because they were scaled to the old numbers.</p>
          <DimensionEditor value={dimDraft} onChange={setDimDraft} />
          <ErrorBox error={addDims.error} />
          <div><button className="btn" onClick={() => addDims.mutate(undefined)} disabled={addDims.isPending}>Record dimensions</button></div>
        </section>

        <section className="card card-pad stack">
          <h2>Record a price check</h2>
          <PriceEditor value={priceDraft} onChange={setPriceDraft} />
          <ErrorBox error={addPrice.error || failedCheck.error} />
          <div className="row">
            <button className="btn" onClick={() => addPrice.mutate(undefined)} disabled={addPrice.isPending}>Record price</button>
            <button className="btn ghost" onClick={() => { const r = window.prompt("Why did the check fail? (page down, price hidden…)"); if (r) failedCheck.mutate(r); }}>
              Record a failed check
            </button>
          </div>
        </section>

        {form.sale_unit !== "single" && (
          <section className="card card-pad stack">
            <div className="row between"><h2>Set contents</h2>
              <button className="btn small" onClick={() => setComponents([...components, { name: "", category_id: null, quantity: 1, width_m: null, depth_m: null, height_m: null, notes: null }])}>Add item</button>
            </div>
            {components.map((c, i) => (
              <div className="set-row" key={i}>
                <input placeholder="Dining chair" value={c.name} onChange={(e) => setComponents(components.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <input inputMode="numeric" value={c.quantity} onChange={(e) => setComponents(components.map((x, j) => (j === i ? { ...x, quantity: Number(e.target.value) || 1 } : x)))} aria-label="quantity" />
                {(["width_m", "depth_m", "height_m"] as const).map((k) => (
                  <input key={k} inputMode="decimal" placeholder={k.replace("_m", " (m)")} value={c[k] ?? ""}
                    onChange={(e) => setComponents(components.map((x, j) => (j === i ? { ...x, [k]: e.target.value ? Number(e.target.value) : null } : x)))} />
                ))}
                <button className="btn small ghost" onClick={() => setComponents(components.filter((_, j) => j !== i))} aria-label="remove">✕</button>
              </div>
            ))}
            <ErrorBox error={saveComponents.error} />
            <div><button className="btn" onClick={() => saveComponents.mutate(undefined)}>Save set contents</button></div>
          </section>
        )}
      </div>

      <div className="stack">
        <section className="card">
          <div className="card-head"><h3>Dimensions</h3><span className="chip">rev {current?.revision ?? "—"}</span></div>
          <div className="card-pad">
            <div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{dims(current?.width_m, current?.depth_m, current?.height_m)}</div>
            <div className="small muted">W × D × H · {current?.kind ?? "none recorded"}{current?.source_text ? ` · “${current.source_text}”` : ""}</div>
          </div>
          <div className="table-wrap"><table>
            <thead><tr><th>Rev</th><th>Kind</th><th>W × D × H</th><th>Recorded</th></tr></thead>
            <tbody>{v.dimensions.map((d) => (
              <tr key={d.id}><td className="num">{d.revision}{d.is_current ? " •" : ""}</td><td>{d.kind}</td>
                <td className="num small">{dims(d.width_m, d.depth_m, d.height_m)}</td><td className="small muted">{date(d.created_at)}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
        <section className="card">
          <div className="card-head"><h3>Price observations</h3></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Checked</th><th>Price</th><th>Stock</th><th>Result</th></tr></thead>
            <tbody>{v.price_observations.map((p) => (
              <tr key={p.id}><td className="small">{dateTime(p.checked_at)}</td><td className="num">{pkr(p.price_pkr)}</td>
                <td className="small">{p.availability.replace("_", " ")}</td>
                <td className="small">{p.outcome === "success" ? "ok" : <span style={{ color: "var(--bad)" }}>failed: {p.failure_reason}</span>}</td></tr>
            ))}
            {v.price_observations.length === 0 && <tr><td colSpan={4} className="muted">No observations yet.</td></tr>}</tbody>
          </table></div>
        </section>
      </div>
    </div>
  );
}
