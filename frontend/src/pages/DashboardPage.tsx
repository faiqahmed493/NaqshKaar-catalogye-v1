import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorBox } from "../components/ui";

interface Stats {
  products: number; retailers: number; eligible_and_asset_ready: number;
  variants_by_status: Record<string, number>; assets_by_status: Record<string, number>; jobs_by_status: Record<string, number>;
  by_group: { product_group: string; variants: number; eligible: number; ready: number }[];
}

export default function DashboardPage() {
  const q = useQuery({ queryKey: ["stats"], queryFn: () => api.get<Stats>("/api/stats"), refetchInterval: 15_000 });
  const s = q.data;
  const v = s?.variants_by_status ?? {};
  const a = s?.assets_by_status ?? {};
  const j = s?.jobs_by_status ?? {};
  const active = (j.queued ?? 0) + (j.claimed ?? 0) + (j.running ?? 0) + (j.uploaded ?? 0) + (j.postprocessing ?? 0);
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Catalogue status</h1>
          <p>A variant reaches the Naqshkaar planner when a curator admits it and its 3D asset is qualified against its current dimensions.</p>
        </div>
        <Link to="/products/new" className="btn primary">Add product</Link>
      </div>
      <ErrorBox error={q.error} />
      <div className="grid-4">
        <div className="card stat"><div className="label">Ready for the planner</div><div className="v">{s?.eligible_and_asset_ready ?? "—"}</div><div className="s">eligible and asset-ready variants</div></div>
        <div className="card stat"><div className="label">In catalogue</div><div className="v">{v.eligible ?? 0}</div><div className="s">{v.reassessing ?? 0} reassessing after a change</div></div>
        <div className="card stat"><div className="label">Awaiting review</div><div className="v">{(v.in_review ?? 0) + (a.in_review ?? 0)}</div><div className="s">{v.in_review ?? 0} variants · {a.in_review ?? 0} 3D assets</div></div>
        <div className="card stat"><div className="label">3D jobs running</div><div className="v">{active}</div><div className="s">{j.failed ?? 0} failed in total</div></div>
      </div>
      <div className="grid-2">
        <div className="card">
          <div className="card-head"><h2>By product group</h2></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Group</th><th>Variants</th><th>Eligible</th><th>Ready</th></tr></thead>
            <tbody>
              {(s?.by_group ?? []).map((g) => (
                <tr key={g.product_group}><td style={{ textTransform: "capitalize" }}>{g.product_group}</td>
                  <td className="num">{g.variants}</td><td className="num">{g.eligible}</td><td className="num">{g.ready}</td></tr>
              ))}
              {!s?.by_group?.length && <tr><td colSpan={4} className="muted">No products yet.</td></tr>}
            </tbody>
          </table></div>
        </div>
        <div className="card card-pad stack" style={{ gap: 10 }}>
          <h2>How a product gets in</h2>
          <ol style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            <li><b>Record the listing</b>: retailer, variant, PKR price with its check date, and assembled W × D × H with the source text.</li>
            <li><b>Upload images</b> of this exact variant; tag front / side views for multi-view engines.</li>
            <li><b>Generate 3D</b> with one or more engines and compare the results.</li>
            <li><b>Review</b> the scaled model against the magenta dimension box and the six-point visual checklist.</li>
            <li><b>Add to catalogue</b> once every admission condition passes.</li>
          </ol>
          <div className="small muted">{s?.products ?? 0} products from {s?.retailers ?? 0} retailers.</div>
        </div>
      </div>
    </div>
  );
}
