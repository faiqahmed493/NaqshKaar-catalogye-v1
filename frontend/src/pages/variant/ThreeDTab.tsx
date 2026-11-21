import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import ModelViewer from "../../components/ModelViewer";
import { AssetBadge, Badge, ChecksTable, ErrorBox, JobBadge, Progress } from "../../components/ui";
import { ACTIVE_JOBS, ago, bytes, dims } from "../../format";
import { useAuth } from "../../auth";
import type { Asset, Engine, VariantDetail, Worker } from "../../types";
import { useVariantMutation } from "./useVariantMutation";

const CHECKLIST: { key: string; label: string }[] = [
  { key: "correct_item", label: "Right product and configuration" },
  { key: "silhouette", label: "Silhouette matches the photos" },
  { key: "components", label: "Visible parts present (legs, arms, shelves, shade)" },
  { key: "no_staging_objects", label: "No staging props fused in (rugs, plants, cushions not sold with it)" },
  { key: "no_missing_parts", label: "No gross missing or broken parts" },
  { key: "no_scale_distortion", label: "No severe stretching or squashing" },
];

export default function ThreeDTab({ v }: { v: VariantDetail }) {
  const { can } = useAuth();
  const engines = useQuery({ queryKey: ["engines"], queryFn: () => api.get<{ engines: Engine[]; workers: Worker[] }>("/api/engines"), refetchInterval: 20_000 });
  const usable = v.images.filter((i) => i.usable_for_3d);
  const [imageIds, setImageIds] = useState<string[]>(() => usable.slice(0, 1).map((i) => i.id));
  const [engineCodes, setEngineCodes] = useState<string[]>([]);
  const [paramsText, setParamsText] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(v.assets[0]?.id ?? null);
  const [openLog, setOpenLog] = useState<string | null>(null);
  const known = useRef(new Set(v.assets.map((a) => a.id)));

  // Jump to a newly finished asset so the reviewer sees it right away.
  useEffect(() => {
    const fresh = v.assets.find((a) => !known.current.has(a.id));
    v.assets.forEach((a) => known.current.add(a.id));
    if (fresh) setSelectedId(fresh.id);
    if (!selectedId && v.assets[0]) setSelectedId(v.assets[0].id);
  }, [v.assets, selectedId]);

  const selected = v.assets.find((a) => a.id === selectedId) ?? null;
  const current = v.dimensions.find((d) => d.is_current);
  const target = current ? { width: current.width_m, depth: current.depth_m, height: current.height_m } : undefined;
  const capture = useCapture(v.id, selected);

  const generate = useVariantMutation(v.id, async () => {
    let params: Record<string, Record<string, unknown>> | null = null;
    if (paramsText.trim()) {
      const parsed = JSON.parse(paramsText);
      params = Object.fromEntries(engineCodes.map((c) => [c, parsed[c] ?? parsed]));
    }
    return api.post(`/api/variants/${v.id}/generation-jobs`, { engine_codes: engineCodes, image_ids: imageIds, params });
  });
  const cancel = useVariantMutation(v.id, (id: string) => api.post(`/api/jobs/${id}/cancel`));
  const retry = useVariantMutation(v.id, (id: string) => api.post(`/api/jobs/${id}/retry`));

  const engineList = engines.data?.engines.filter((e) => e.is_enabled) ?? [];
  const toggleEngine = (code: string) => setEngineCodes((c) => (c.includes(code) ? c.filter((x) => x !== code) : [...c, code]));
  const toggleImage = (id: string) => setImageIds((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const views = new Set(usable.filter((i) => imageIds.includes(i.id)).map((i) => i.view_angle));
  const activeJobs = v.jobs.filter((j) => ACTIVE_JOBS.includes(j.status));

  return (
    <div className="split">
      <div className="stack">
        <section className="card card-pad stack">
          <div className="row between">
            <h2>{selected ? `Asset v${selected.version}` : "Preview"}</h2>
            {selected && <div className="row"><AssetBadge status={selected.status} />{selected.is_selected && <Badge tone="good">Served to planner</Badge>}</div>}
          </div>
          <ModelViewer url={selected?.glb_url ?? null} target={target} onCapture={capture} />
          {selected && <AssetFacts a={selected} />}
        </section>
        {selected && <ReviewPanel v={v} a={selected} canReview={can("asset_reviewer", "curator")} />}
        <section className="card">
          <div className="card-head"><h3>All 3D versions</h3><span className="small muted">current dims {dims(current?.width_m, current?.depth_m, current?.height_m)}</span></div>
          <div className="card-pad asset-list">
            {v.assets.length === 0 && <div className="muted">No assets yet. Generate one on the right, or upload a GLB you made.</div>}
            {v.assets.map((a) => (
              <button key={a.id} className={`asset-item ${a.id === selectedId ? "on" : ""}`} onClick={() => setSelectedId(a.id)}>
                {a.preview_url ? <img src={a.preview_url} alt="" /> : <div className="ph" />}
                <div>
                  <b>v{a.version} · {a.engine_code ?? a.origin.replace("_", " ")}</b>
                  <div className="small muted">{ago(a.created_at)} · {a.triangle_count?.toLocaleString() ?? "—"} triangles
                    {!a.checked_against_current_dimensions && a.status !== "processing" ? " · not checked against current dims" : ""}</div>
                </div>
                <AssetBadge status={a.status} />
              </button>
            ))}
          </div>
          {can("asset_reviewer", "curator") && <UploadGlb v={v} parent={selected} />}
        </section>
      </div>

      <div className="stack">
        <section className="card card-pad stack">
          <h2>Generate a 3D model</h2>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>1 · Input images ({imageIds.length} selected)</div>
            {usable.length === 0 && <div className="notice">Upload images on the Images tab first.</div>}
            <div className="image-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(84px, 1fr))", gap: 8 }}>
              {usable.map((img) => (
                <button key={img.id} className={`image-tile ${imageIds.includes(img.id) ? "selected" : ""}`} style={{ padding: 0, cursor: "pointer" }}
                  onClick={() => toggleImage(img.id)} aria-pressed={imageIds.includes(img.id)} title={img.view_angle}>
                  <img src={img.thumbnail_url} alt={img.view_angle} />
                  <span className="small" style={{ padding: 4 }}>{img.view_angle.replace("_", " ")}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>2 · Engines (each makes its own version to compare)</div>
            <div className="engine-grid">
              {engineList.map((e) => {
                const missing = e.required_views.filter((rv) => !views.has(rv as never));
                const off = missing.length > 0;
                return (
                  <div key={e.code} className={`engine ${engineCodes.includes(e.code) ? "on" : ""} ${off ? "off" : ""}`}
                    onClick={() => !off && toggleEngine(e.code)} role="checkbox" aria-checked={engineCodes.includes(e.code)} tabIndex={0}
                    onKeyDown={(k) => k.key === " " && !off && toggleEngine(e.code)}>
                    <div className="row between"><h4>{e.display_name}</h4>
                      <Badge tone={e.online_workers ? "good" : "muted"}>{e.online_workers ? `${e.online_workers} online` : "no worker"}</Badge></div>
                    <div className="row small">
                      {e.min_vram_gb && <span className="chip">{e.min_vram_gb} GB+</span>}
                      <span className="chip">{e.supports_multi_image ? `≤${e.max_input_images} images` : "1 image"}</span>
                      {!e.is_open_source && <span className="chip">paid API</span>}
                    </div>
                    <div className="small muted">{off ? `Needs an image tagged: ${missing.join(", ")}` : e.notes}</div>
                    {e.commercial_use_note && <div className="small" style={{ color: "var(--warn)" }}>{e.license}: {e.commercial_use_note}</div>}
                  </div>
                );
              })}
            </div>
          </div>
          <details>
            <summary className="small">Advanced: engine parameters (JSON)</summary>
            <textarea className="mono" placeholder='{"seed": 7}  or per engine: {"trellis": {"seed": 7}, "triposr": {"mc_resolution": 320}}'
              value={paramsText} onChange={(e) => setParamsText(e.target.value)} />
          </details>
          <ErrorBox error={generate.error} />
          <button className="btn primary" disabled={!engineCodes.length || !imageIds.length || generate.isPending || !can("curator", "asset_reviewer")}
            onClick={() => generate.mutate(undefined)}>
            {generate.isPending ? "Queuing…" : `Generate with ${engineCodes.length || "no"} engine${engineCodes.length === 1 ? "" : "s"}`}
          </button>
          {engineCodes.some((c) => !engineList.find((e) => e.code === c)?.online_workers) && (
            <div className="small muted">A selected engine has no worker online. The job waits in the queue until one connects.</div>
          )}
        </section>

        <section className="card">
          <div className="card-head"><h3>Jobs</h3>{activeJobs.length > 0 && <span className="small muted">refreshing every 3 s</span>}</div>
          <div className="card-pad stack" style={{ gap: 10 }}>
            {v.jobs.length === 0 && <div className="muted">No jobs yet.</div>}
            {v.jobs.map((j) => (
              <div key={j.id} style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 10 }}>
                <div className="row between">
                  <b>{j.engine_name}</b>
                  <JobBadge status={j.status} />
                </div>
                {ACTIVE_JOBS.includes(j.status) && <div style={{ margin: "6px 0" }}><Progress value={j.progress} /></div>}
                <div className="small muted">
                  {j.worker_id ? `on ${j.worker_id} · ` : ""}{ago(j.created_at)} · attempt {j.attempts}/{j.max_attempts}
                  {typeof j.runtime_meta?.seconds === "number" ? ` · ${j.runtime_meta.seconds as number}s` : ""}
                  {typeof j.runtime_meta?.peak_vram_gb === "number" ? ` · ${j.runtime_meta.peak_vram_gb as number} GB peak` : ""}
                </div>
                {j.error_message && <div className="small" style={{ color: "var(--bad)" }}>{j.error_message}</div>}
                <div className="row" style={{ marginTop: 6 }}>
                  {j.result_asset_id && <button className="btn small" onClick={() => setSelectedId(j.result_asset_id)}>View result</button>}
                  {["queued", "claimed", "running"].includes(j.status) && <button className="btn small danger" onClick={() => cancel.mutate(j.id)}>Cancel</button>}
                  {["failed", "cancelled", "succeeded"].includes(j.status) && <button className="btn small" onClick={() => retry.mutate(j.id)}>Run again</button>}
                  <button className="btn small ghost" onClick={() => setOpenLog(openLog === j.id ? null : j.id)}>{openLog === j.id ? "Hide log" : "Log"}</button>
                </div>
                {openLog === j.id && <JobLog id={j.id} live={ACTIVE_JOBS.includes(j.status)} />}
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function useCapture(variantId: string, a: Asset | null) {
  const sent = useRef(new Set<string>());
  const upload = useVariantMutation(variantId, ({ id, blob }: { id: string; blob: Blob }) => {
    const form = new FormData();
    form.append("file", blob, "preview.png");
    return api.upload(`/api/assets/${id}/preview`, form);
  });
  const id = a && !a.preview_url && a.glb_url ? a.id : null;
  const cb = useCallback((blob: Blob) => {
    if (!id || sent.current.has(id)) return;
    sent.current.add(id);
    upload.mutate({ id, blob });
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  return id ? cb : undefined;
}

function JobLog({ id, live }: { id: string; live: boolean }) {
  const q = useQuery({ queryKey: ["job", id], queryFn: () => api.get<{ log: string }>(`/api/jobs/${id}`), refetchInterval: live ? 3000 : false });
  return <pre className="log" style={{ marginTop: 8 }}>{q.data?.log || "No log lines yet."}</pre>;
}

function AssetFacts({ a }: { a: Asset }) {
  const s = a.scaled_extents_m;
  return (
    <div className="grid-4 small">
      <div><div className="label">Scaled extents</div><div className="num">{s ? dims(s.width, s.depth, s.height) : "—"}</div></div>
      <div><div className="label">Proportion change</div><div className="num">{a.scale_factors?.distortion ? `×${a.scale_factors.distortion.toFixed(2)}` : "—"}</div></div>
      <div><div className="label">Geometry</div><div className="num">{a.triangle_count?.toLocaleString() ?? "—"} tris · {a.texture_count ?? 0} tex</div></div>
      <div><div className="label">File</div><div className="num">{bytes(a.glb_size_bytes)}{a.glb_url && <> · <a href={`${a.glb_url}&download=true`}>download</a></>}</div></div>
    </div>
  );
}

function ReviewPanel({ v, a, canReview }: { v: VariantDetail; a: Asset; canReview: boolean }) {
  const [checklist, setChecklist] = useState<Record<string, boolean>>({});
  const [comment, setComment] = useState("");
  const [rot, setRot] = useState<number[]>(a.orientation?.rotation_deg ?? [0, 0, 0]);
  useEffect(() => { setChecklist({}); setComment(""); setRot(a.orientation?.rotation_deg ?? [0, 0, 0]); }, [a.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const review = useVariantMutation(v.id, (decision: string) =>
    api.post(`/api/assets/${a.id}/review`, { decision, checklist, comment: comment || null, select_for_catalogue: true }));
  const publish = useVariantMutation(v.id, () =>
    api.post(`/api/variants/${v.id}/publish`, { asset_id: a.id, checklist, comment: comment || null }));
  const reprocess = useVariantMutation(v.id, (body: { rotation_deg?: number[]; auto_yaw?: boolean }) =>
    api.post(`/api/assets/${a.id}/reprocess`, body));
  const select = useVariantMutation(v.id, () => api.post(`/api/assets/${a.id}/select`));

  const allTicked = CHECKLIST.every((c) => checklist[c.key]);
  const failed = a.checks.filter((c) => c.outcome === "fail" && c.code !== "visual_review");
  const reviewable = a.status === "in_review" || a.status === "needs_correction";
  const turn = (axis: number) => setRot(rot.map((r, i) => (i === axis ? (r + 90) % 360 : r)));
  const conditionsOk = v.admission.all_required_pass;

  return (
    <section className="card">
      <div className="card-head"><h3>Qualification</h3>
        {a.processing_error && a.status !== "processing" && <span className="small" style={{ color: "var(--bad)" }}>{a.processing_error.split("\n")[0].slice(0, 120)}</span>}
      </div>
      {a.status === "processing" ? <div className="card-pad muted">Running automated checks…</div> : <ChecksTable checks={a.checks} />}
      {canReview && a.status !== "processing" && a.status !== "qualified" && (
        <div className="card-pad stack" style={{ borderTop: "1px solid var(--rule)" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>Orientation</div>
            <div className="row">
              {["X", "Y", "Z"].map((ax, i) => <button key={ax} className="btn small" onClick={() => turn(i)}>Turn {ax} +90° ({rot[i]}°)</button>)}
              <button className="btn small primary" onClick={() => reprocess.mutate({ rotation_deg: rot })} disabled={reprocess.isPending}>Re-run checks</button>
            </div>
            <div className="small muted" style={{ marginTop: 4 }}>The front of the product should face the “front” label. Width and depth are swapped automatically when that fits the recorded footprint better.</div>
          </div>
          {reviewable && <>
            <div>
              <div className="label" style={{ marginBottom: 6 }}>Visual review (§6.2): tick all to approve</div>
              <div className="stack" style={{ gap: 6 }}>
                {CHECKLIST.map((c) => (
                  <label key={c.key} className="check"><input type="checkbox" checked={!!checklist[c.key]}
                    onChange={(e) => setChecklist({ ...checklist, [c.key]: e.target.checked })} />{c.label}</label>
                ))}
              </div>
            </div>
            <textarea placeholder="Comment (what is wrong, what was fixed)" value={comment} onChange={(e) => setComment(e.target.value)} />
            <ErrorBox error={review.error || publish.error || reprocess.error} />
            {failed.length > 0 && <div className="error">Automated checks failed: {failed.map((f) => f.code).join(", ")}. Fix the orientation or dimensions and re-run, upload a corrected GLB, or try another engine.</div>}
            <div className="row">
              <button className="btn good" disabled={!allTicked || failed.length > 0 || publish.isPending || !conditionsOk}
                onClick={() => publish.mutate(undefined)} title={conditionsOk ? "" : "Open admission conditions remain (see Review & publish)"}>
                Approve and add to catalogue
              </button>
              <button className="btn" disabled={!allTicked || failed.length > 0} onClick={() => review.mutate("approve")}>Approve asset only</button>
              <button className="btn" onClick={() => review.mutate("needs_correction")}>Needs correction</button>
              <button className="btn danger" onClick={() => review.mutate("reject")}>Reject</button>
            </div>
            {!conditionsOk && <div className="small muted">“Add to catalogue” unlocks when every admission condition passes. You can approve the asset now and publish later.</div>}
          </>}
        </div>
      )}
      {a.status === "qualified" && !a.is_selected && canReview && (
        <div className="card-pad"><button className="btn" onClick={() => select.mutate(undefined)}>Serve this version to the planner</button></div>
      )}
    </section>
  );
}

function UploadGlb({ v, parent }: { v: VariantDetail; parent: Asset | null }) {
  const input = useRef<HTMLInputElement>(null);
  const [asCorrection, setAsCorrection] = useState(true);
  const upload = useVariantMutation(v.id, (file: File) => {
    const form = new FormData();
    form.append("file", file);
    if (asCorrection && parent) form.append("parent_asset_id", parent.id);
    return api.upload(`/api/variants/${v.id}/assets`, form);
  });
  const label = useMemo(() => (parent && asCorrection ? `Upload corrected GLB for v${parent.version}` : "Upload a GLB"), [parent, asCorrection]);
  return (
    <div className="card-pad stack" style={{ borderTop: "1px solid var(--rule)", gap: 8 }}>
      <div className="row">
        <button className="btn" onClick={() => input.current?.click()} disabled={upload.isPending}>{upload.isPending ? "Uploading…" : label}</button>
        {parent && <label className="check small"><input type="checkbox" checked={asCorrection} onChange={(e) => setAsCorrection(e.target.checked)} />as a correction of the selected version</label>}
      </div>
      <div className="small muted">Fixed it in Blender? Export glTF Binary (.glb) with textures embedded. Uploaded files repeat every check.</div>
      <ErrorBox error={upload.error} />
      <input ref={input} type="file" accept=".glb,model/gltf-binary" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
    </div>
  );
}
