import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useParams, Link } from "react-router-dom";
import { api } from "../api";
import { AssetBadge, ErrorBox, VariantBadge } from "../components/ui";
import { ACTIVE_JOBS } from "../format";
import type { VariantDetail } from "../types";
import CatalogueTab from "./variant/CatalogueTab";
import HistoryTab from "./variant/HistoryTab";
import ImagesTab from "./variant/ImagesTab";
import OverviewTab from "./variant/OverviewTab";
import ThreeDTab from "./variant/ThreeDTab";

const TABS = [
  { key: "overview", label: "Details" },
  { key: "images", label: "Images" },
  { key: "3d", label: "3D model" },
  { key: "catalogue", label: "Review & publish" },
  { key: "history", label: "History" },
] as const;

export default function VariantPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const q = useQuery({
    queryKey: ["variant", id],
    queryFn: () => api.get<VariantDetail>(`/api/variants/${id}`),
    refetchInterval: (query) => {
      const v = query.state.data;
      const busy = v && (v.jobs.some((j) => ACTIVE_JOBS.includes(j.status)) || v.assets.some((a) => a.status === "processing"));
      return busy ? 3000 : false;
    },
  });
  const v = q.data;
  if (q.error) return <ErrorBox error={q.error} />;
  if (!v) return <div className="muted">Loading…</div>;

  const counts: Record<string, number> = { images: v.images.length, "3d": v.assets.length };
  const failing = v.admission.conditions.filter((c) => c.required && !c.passed).length;
  const latestAsset = v.assets[0];
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="row small muted">
            <Link to="/products">Products</Link><span>/</span><span>{v.product.retailer.name}</span>
          </div>
          <h1>{v.product.name}{v.variant_label ? ` · ${v.variant_label}` : ""}</h1>
          <div className="row" style={{ marginTop: 8 }}>
            <VariantBadge status={v.status} />
            {v.asset_ready ? <AssetBadge status="qualified" /> : <AssetBadge status={latestAsset?.status ?? null} />}
            {v.product.category && <span className="chip">{v.product.category.name}</span>}
            {failing > 0 && v.status !== "eligible" && <span className="small muted">{failing} admission condition(s) open</span>}
            {v.status_reason && <span className="small" style={{ color: "var(--warn)" }}>{v.status_reason}</span>}
          </div>
        </div>
        {v.product.variants.length > 1 && (
          <select value={v.id} onChange={(e) => (window.location.href = `/variants/${e.target.value}?tab=${tab}`)} style={{ width: "auto" }}>
            {v.product.variants.map((x) => <option key={x.id} value={x.id}>{x.variant_label || x.variant_key}</option>)}
          </select>
        )}
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""}
            onClick={() => setParams({ tab: t.key }, { replace: true })}>
            {t.label}{counts[t.key] !== undefined && <span className="count">{counts[t.key]}</span>}
          </button>
        ))}
      </div>
      {tab === "overview" && <OverviewTab v={v} />}
      {tab === "images" && <ImagesTab v={v} />}
      {tab === "3d" && <ThreeDTab v={v} />}
      {tab === "catalogue" && <CatalogueTab v={v} />}
      {tab === "history" && <HistoryTab v={v} />}
    </div>
  );
}
