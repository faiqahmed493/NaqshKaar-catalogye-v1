import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { DimensionEditor, ImageDrop, PriceEditor, VIEW_ANGLES, dimsPayload, emptyDims, emptyPrice, pricePayload } from "../components/forms";
import { ErrorBox, Field } from "../components/ui";
import { ROOM_LABELS } from "../format";
import type { Category, Retailer, RoomType, SaleUnit, ViewAngle } from "../types";

interface PendingImage { file: File; url: string; view: ViewAngle }

export default function NewProductPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const retailers = useQuery({ queryKey: ["retailers"], queryFn: () => api.get<Retailer[]>("/api/retailers") });
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api.get<Category[]>("/api/categories") });

  const [retailerId, setRetailerId] = useState("");
  const [newRetailer, setNewRetailer] = useState({ name: "", website_url: "" });
  const [categoryId, setCategoryId] = useState("");
  const [p, setP] = useState({ name: "", brand: "", listing_url: "", retailer_product_ref: "", description: "" });
  const [v, setV] = useState({ variant_label: "", variant_key: "", configuration: "standard", sale_unit: "single" as SaleUnit, sale_unit_quantity: "" });
  const [rooms, setRooms] = useState<RoomType[]>([]);
  const [attrs, setAttrs] = useState({ style: "", colour: "", colour_hex: "", material: "" });
  const [dims, setDims] = useState(emptyDims());
  const [price, setPrice] = useState(emptyPrice());
  const [images, setImages] = useState<PendingImage[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");

  const grouped = useMemo(() => {
    const leaves = (categories.data ?? []).filter((c) => c.parent_id);
    return ["furniture", "lighting", "planter", "decor"].map((g) => ({ g, items: leaves.filter((c) => c.product_group === g) }));
  }, [categories.data]);

  const addFiles = (files: File[]) =>
    setImages((cur) => [...cur, ...files.map((file, i) => ({ file, url: URL.createObjectURL(file), view: (cur.length + i === 0 ? "front" : "unknown") as ViewAngle }))]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      let rid = retailerId;
      if (rid === "__new") {
        setBusy("Creating retailer…");
        const slug = newRetailer.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        const r = await api.post<Retailer>("/api/retailers", { name: newRetailer.name, slug, website_url: newRetailer.website_url || null });
        rid = r.id;
        qc.invalidateQueries({ queryKey: ["retailers"] });
      }
      setBusy("Saving product…");
      const attributes = [
        attrs.style && { key: "style", value: attrs.style, source: "curator", verified: true },
        attrs.colour && { key: "colour", value: attrs.colour, colour_hex: attrs.colour_hex || null, source: "curator", verified: true },
        attrs.material && { key: "material", value: attrs.material, source: "listing", verified: true },
      ].filter(Boolean);
      const res = await api.post<{ product: { id: string }; variant_id: string }>("/api/products", {
        retailer_id: rid, name: p.name, brand: p.brand || null, category_id: categoryId ? Number(categoryId) : null,
        description: p.description || null, listing_url: p.listing_url || null, retailer_product_ref: p.retailer_product_ref || null,
        variant: {
          variant_key: v.variant_key.trim() || "default", variant_label: v.variant_label || null, configuration: v.configuration || "standard",
          sale_unit: v.sale_unit, sale_unit_quantity: v.sale_unit === "single" ? 1 : (Number(v.sale_unit_quantity) || null),
          dimensions: dimsPayload(dims), price: pricePayload(price), attributes,
          room_uses: rooms.map((room_type) => ({ room_type, use_tag: "general" })),
        },
      });
      for (const [n, img] of images.entries()) {
        setBusy(`Uploading image ${n + 1} of ${images.length}…`);
        const form = new FormData();
        form.append("files", img.file);
        form.append("variant_id", res.variant_id);
        form.append("view_angle", img.view);
        form.append("role", n === 0 ? "primary" : "gallery");
        await api.upload(`/api/products/${res.product.id}/images`, form);
      }
      qc.invalidateQueries({ queryKey: ["products"] });
      nav(`/variants/${res.variant_id}?tab=${images.length ? "3d" : "images"}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy("");
    }
  };

  return (
    <form className="stack" onSubmit={submit}>
      <div className="page-head">
        <div>
          <h1>Add product</h1>
          <p>Record one buyable variant from a Pakistani retailer. Leave anything you don't know empty: unknown stays unknown, never zero.</p>
        </div>
      </div>
      <ErrorBox error={error} />

      <section className="card card-pad stack">
        <h2>Listing</h2>
        <div className="grid-3">
          <Field label="Retailer">
            <select value={retailerId} onChange={(e) => setRetailerId(e.target.value)} required>
              <option value="" disabled>Choose…</option>
              {retailers.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              <option value="__new">+ New retailer</option>
            </select>
          </Field>
          {retailerId === "__new" && <>
            <Field label="Retailer name"><input value={newRetailer.name} onChange={(e) => setNewRetailer({ ...newRetailer, name: e.target.value })} required /></Field>
            <Field label="Website"><input value={newRetailer.website_url} onChange={(e) => setNewRetailer({ ...newRetailer, website_url: e.target.value })} placeholder="https://" /></Field>
          </>}
        </div>
        <div className="grid-3">
          <Field label="Product name"><input value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} required /></Field>
          <Field label="Category">
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Not set yet</option>
              {grouped.map(({ g, items }) => (
                <optgroup key={g} label={g[0].toUpperCase() + g.slice(1)}>
                  {items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </optgroup>
              ))}
            </select>
          </Field>
          <Field label="Brand"><input value={p.brand} onChange={(e) => setP({ ...p, brand: e.target.value })} /></Field>
        </div>
        <div className="grid-2">
          <Field label="Listing URL" hint="the purchase page"><input type="url" value={p.listing_url} onChange={(e) => setP({ ...p, listing_url: e.target.value })} placeholder="https://" /></Field>
          <Field label="Retailer SKU / code"><input value={p.retailer_product_ref} onChange={(e) => setP({ ...p, retailer_product_ref: e.target.value })} /></Field>
        </div>
        <Field label="Description"><textarea value={p.description} onChange={(e) => setP({ ...p, description: e.target.value })} /></Field>
      </section>

      <section className="card card-pad stack">
        <h2>Variant</h2>
        <div className="grid-4">
          <Field label="Variant label" hint="size, colour, finish"><input value={v.variant_label} onChange={(e) => setV({ ...v, variant_label: e.target.value })} placeholder="3-seater · grey velvet" /></Field>
          <Field label="Variant code" hint="retailer's, if any"><input value={v.variant_key} onChange={(e) => setV({ ...v, variant_key: e.target.value })} placeholder="default" /></Field>
          <Field label="Price buys">
            <select value={v.sale_unit} onChange={(e) => setV({ ...v, sale_unit: e.target.value as SaleUnit })}>
              <option value="single">One item</option><option value="set">A set</option><option value="pair">A pair</option><option value="pack">A pack</option>
            </select>
          </Field>
          {v.sale_unit !== "single" && <Field label="Items in the set"><input inputMode="numeric" value={v.sale_unit_quantity} onChange={(e) => setV({ ...v, sale_unit_quantity: e.target.value })} /></Field>}
        </div>
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Meant for</div>
          <div className="row">
            {(Object.keys(ROOM_LABELS) as RoomType[]).map((r) => (
              <label key={r} className="check"><input type="checkbox" checked={rooms.includes(r)}
                onChange={(e) => setRooms(e.target.checked ? [...rooms, r] : rooms.filter((x) => x !== r))} />{ROOM_LABELS[r]}</label>
            ))}
          </div>
        </div>
        <div className="grid-4">
          <Field label="Style"><input value={attrs.style} onChange={(e) => setAttrs({ ...attrs, style: e.target.value })} placeholder="modern, traditional…" /></Field>
          <Field label="Colour"><input value={attrs.colour} onChange={(e) => setAttrs({ ...attrs, colour: e.target.value })} placeholder="grey" /></Field>
          <Field label="Colour swatch"><input type="color" value={attrs.colour_hex || "#888888"} onChange={(e) => setAttrs({ ...attrs, colour_hex: e.target.value })} style={{ height: 38, padding: 2 }} /></Field>
          <Field label="Material" hint="as the listing states"><input value={attrs.material} onChange={(e) => setAttrs({ ...attrs, material: e.target.value })} placeholder="sheesham wood" /></Field>
        </div>
      </section>

      <section className="card card-pad stack">
        <h2>Assembled dimensions</h2>
        <DimensionEditor value={dims} onChange={setDims} />
      </section>

      <section className="card card-pad stack">
        <h2>Price observation</h2>
        <PriceEditor value={price} onChange={setPrice} />
      </section>

      <section className="card card-pad stack">
        <h2>Images</h2>
        <ImageDrop onFiles={addFiles} />
        {images.length > 0 && (
          <div className="image-grid">
            {images.map((img, i) => (
              <div className="image-tile" key={img.url}>
                <img src={img.url} alt={img.file.name} />
                <div className="meta">
                  <span className="small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{img.file.name}</span>
                  <select value={img.view} onChange={(e) => setImages(images.map((x, j) => (j === i ? { ...x, view: e.target.value as ViewAngle } : x)))}>
                    {VIEW_ANGLES.map((a) => <option key={a} value={a}>{a.replace("_", " ")}</option>)}
                  </select>
                  <button type="button" className="btn small danger" onClick={() => setImages(images.filter((_, j) => j !== i))}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="row">
        <button className="btn primary" type="submit" disabled={!!busy}>{busy || "Save and continue to 3D"}</button>
        <span className="muted small">Saved as a draft. It reaches the catalogue only after review.</span>
      </div>
    </form>
  );
}
