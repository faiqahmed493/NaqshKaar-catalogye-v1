import { useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { AssetBadge, ConditionsList, ErrorBox, VariantBadge } from "../../components/ui";
import { date, dateTime, dims, pkr } from "../../format";
import type { VariantDetail } from "../../types";
import { useVariantMutation } from "./useVariantMutation";

export default function CatalogueTab({ v }: { v: VariantDetail }) {
  const { can } = useAuth();
  const [comment, setComment] = useState("");
  const listing = v.effective_listing_url;
  const lastCheck = v.link_checks[0];
  const linkCurrent = lastCheck && lastCheck.url === listing;

  const decide = useVariantMutation(v.id, (decision: string) =>
    api.post(`/api/variants/${v.id}/admission-reviews`, { decision, comment: comment || null }));
  const submit = useVariantMutation(v.id, () => api.post(`/api/variants/${v.id}/submit`));
  const link = useVariantMutation(v.id, (outcome: string) =>
    api.post(`/api/variants/${v.id}/link-checks`, { outcome, url: listing }));
  const retire = useVariantMutation(v.id, () => api.post(`/api/variants/${v.id}/retire`, { reason: comment || null }));

  const price = v.latest_price;
  const editor = can("curator");
  const err = decide.error || submit.error || link.error || retire.error;
  return (
    <div className="split">
      <div className="stack">
        <section className="card">
          <div className="card-head"><h2>Admission conditions</h2>
            {v.admission.all_required_pass ? <span className="badge tone-good">All required pass</span>
              : <span className="badge tone-bad">{v.admission.conditions.filter((c) => c.required && !c.passed).length} open</span>}
          </div>
          <div className="card-pad"><ConditionsList conditions={v.admission.conditions} /></div>
        </section>
        <section className="card card-pad stack">
          <h2>Purchase link check</h2>
          <p className="small muted" style={{ margin: 0 }}>Open the listing and confirm the page sells exactly this variant at the recorded price. Matching is a human judgement (FR-CAT-008).</p>
          {listing ? <a href={listing} target="_blank" rel="noreferrer" className="mono" style={{ wordBreak: "break-all" }}>{listing}</a>
            : <div className="error">No listing URL recorded.</div>}
          {lastCheck && <div className="small">Last check: <b>{lastCheck.outcome}</b> · {dateTime(lastCheck.checked_at)}{linkCurrent ? "" : " (for a different URL)"}</div>}
          {editor && listing && (
            <div className="row">
              <button className="btn" onClick={() => link.mutate("ok")}>Page matches this variant</button>
              <button className="btn" onClick={() => link.mutate("mismatch")}>Shows a different item</button>
              <button className="btn" onClick={() => link.mutate("unreachable")}>Page doesn’t load</button>
            </div>
          )}
        </section>
      </div>
      <div className="stack">
        <section className="card card-pad stack">
          <div className="row between"><h2>Decision</h2><VariantBadge status={v.status} /></div>
          <div className="grid-2 small">
            <div><div className="label">Price</div><div className="num">{pkr(price?.price_pkr)}</div><div className="muted">checked {date(price?.checked_at)}</div></div>
            <div><div className="label">Dimensions</div><div className="num">{dims(v.dimension?.width_m, v.dimension?.depth_m, v.dimension?.height_m)}</div></div>
            <div><div className="label">3D asset</div>{v.asset_ready ? <AssetBadge status="qualified" /> : <AssetBadge status={v.assets[0]?.status ?? null} />}</div>
            <div><div className="label">In catalogue since</div>{date(v.eligible_since)}</div>
          </div>
          {!v.asset_ready && <div className="notice small">Eligibility and 3D qualification are separate. An eligible variant without a qualified asset can be shortlisted, but the planner cannot finalise a design that uses it (FR-3D-006).</div>}
          <ErrorBox error={err} />
          {editor && v.status !== "retired" && <>
            <textarea placeholder="Review comment" value={comment} onChange={(e) => setComment(e.target.value)} />
            <div className="row">
              {["draft", "ineligible", "reassessing"].includes(v.status) && <button className="btn" onClick={() => submit.mutate(undefined)}>Submit for review</button>}
              <button className="btn good" disabled={!v.admission.all_required_pass || v.status === "eligible"} onClick={() => decide.mutate("approve")}>Admit to catalogue</button>
              <button className="btn" onClick={() => decide.mutate("request_changes")}>Request changes</button>
              <button className="btn danger" onClick={() => decide.mutate("reject")}>Reject</button>
            </div>
            {v.status === "eligible" && <button className="btn danger small" onClick={() => retire.mutate(undefined)}>Retire from catalogue</button>}
          </>}
        </section>
        <section className="card">
          <div className="card-head"><h3>Review history</h3></div>
          <div className="card-pad stack" style={{ gap: 8 }}>
            {v.admission.reviews.length === 0 && <div className="muted small">No reviews yet.</div>}
            {v.admission.reviews.map((r) => (
              <div key={r.id} className="small"><b style={{ textTransform: "capitalize" }}>{r.decision.replace("_", " ")}</b> · {dateTime(r.created_at)}{r.comment ? ` · ${r.comment}` : ""}</div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
