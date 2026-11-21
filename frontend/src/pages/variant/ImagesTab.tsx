import { useState } from "react";
import { api } from "../../api";
import { IMAGE_ROLES, ImageDrop, VIEW_ANGLES } from "../../components/forms";
import { ErrorBox } from "../../components/ui";
import type { ProductImage, VariantDetail, ViewAngle } from "../../types";
import { useVariantMutation } from "./useVariantMutation";

export default function ImagesTab({ v }: { v: VariantDetail }) {
  const [view, setView] = useState<ViewAngle>("unknown");
  const [shared, setShared] = useState(false);
  const upload = useVariantMutation(v.id, async (files: File[]) => {
    for (const f of files) {
      const form = new FormData();
      form.append("files", f);
      if (!shared) form.append("variant_id", v.id);
      form.append("view_angle", view);
      await api.upload(`/api/products/${v.product.id}/images`, form);
    }
  });
  const patch = useVariantMutation(v.id, ({ id, body }: { id: string; body: Partial<ProductImage> & { shared_with_all_variants?: boolean } }) =>
    api.patch(`/api/images/${id}`, body));
  const remove = useVariantMutation(v.id, (id: string) => api.del(`/api/images/${id}`));

  return (
    <div className="stack">
      <section className="card card-pad stack">
        <div className="row between">
          <h2>Upload images</h2>
          <div className="row">
            <label className="small">View of new uploads&nbsp;
              <select value={view} onChange={(e) => setView(e.target.value as ViewAngle)} style={{ width: "auto" }}>
                {VIEW_ANGLES.map((a) => <option key={a} value={a}>{a.replace("_", " ")}</option>)}
              </select>
            </label>
            <label className="check small"><input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />share with all variants</label>
          </div>
        </div>
        <ImageDrop onFiles={(f) => upload.mutate(f)} busy={upload.isPending} />
        <ErrorBox error={upload.error || patch.error || remove.error} />
        <div className="small muted">
          Each upload is decoded and checked before it is stored. SVGs are rasterised to PNG for the 3D engines.
          Untick “shows this variant” for images of a different colour or size: they cannot satisfy admission.
        </div>
      </section>
      <div className="image-grid">
        {v.images.map((img) => (
          <div className="image-tile" key={img.id}>
            <a href={img.original_url} target="_blank" rel="noreferrer"><img src={img.thumbnail_url} alt={img.filename ?? "product image"} /></a>
            <div className="meta">
              <div className="row between small">
                <span className="chip">{img.original_format.toUpperCase()} {img.width_px}×{img.height_px}</span>
                {!img.variant_id && <span className="chip">shared</span>}
              </div>
              <select value={img.view_angle} onChange={(e) => patch.mutate({ id: img.id, body: { view_angle: e.target.value as ViewAngle } })} aria-label="view angle">
                {VIEW_ANGLES.map((a) => <option key={a} value={a}>{a.replace("_", " ")}</option>)}
              </select>
              <select value={img.role} onChange={(e) => patch.mutate({ id: img.id, body: { role: e.target.value as ProductImage["role"] } })} aria-label="role">
                {IMAGE_ROLES.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
              </select>
              <label className="check small"><input type="checkbox" checked={!!img.depicts_variant}
                onChange={(e) => patch.mutate({ id: img.id, body: { depicts_variant: e.target.checked, reviewed: true } })} />shows this variant</label>
              <label className="check small"><input type="checkbox" checked={img.usable_for_3d}
                onChange={(e) => patch.mutate({ id: img.id, body: { usable_for_3d: e.target.checked } })} />use for 3D</label>
              <button className="btn small danger" onClick={() => remove.mutate(img.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
