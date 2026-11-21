import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, qs } from "../api";
import { AssetBadge, Empty, ErrorBox, VariantBadge } from "../components/ui";
import { date, dims, pkr } from "../format";
import type { Category, ProductSummary, Retailer } from "../types";

export default function ProductsPage() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [retailer, setRetailer] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [asset, setAsset] = useState("");
  const [page, setPage] = useState(1);
  const retailers = useQuery({ queryKey: ["retailers"], queryFn: () => api.get<Retailer[]>("/api/retailers") });
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api.get<Category[]>("/api/categories") });
  const list = useQuery({
    queryKey: ["products", q, retailer, category, status, asset, page],
    queryFn: () => api.get<{ items: ProductSummary[]; total: number; page_size: number }>(
      `/api/products${qs({ q, retailer_id: retailer, category_id: category, status, asset, page })}`),
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;

  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Products</h1><p>Every retailer listing and its purchasable variants.</p></div>
        <Link to="/products/new" className="btn primary">Add product</Link>
      </div>
      <div className="card card-pad">
        <div className="filters">
          <input placeholder="Search name, brand, SKU, external id" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <select value={retailer} onChange={(e) => { setRetailer(e.target.value); setPage(1); }}>
            <option value="">All retailers</option>
            {retailers.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
            <option value="">All categories</option>
            {categories.data?.filter((c) => c.parent_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">Any status</option><option value="draft">Draft</option><option value="in_review">In review</option>
            <option value="eligible">In catalogue</option><option value="reassessing">Reassessing</option>
            <option value="ineligible">Ineligible</option><option value="retired">Retired</option>
          </select>
          <select value={asset} onChange={(e) => { setAsset(e.target.value); setPage(1); }}>
            <option value="">Any 3D state</option><option value="ready">3D ready</option><option value="missing">3D missing</option>
          </select>
        </div>
      </div>
      <ErrorBox error={list.error} />
      {list.data && list.data.items.length === 0 ? (
        <Empty title="No products match">Add one by hand or push listings through the ingest API.</Empty>
      ) : (
        <div className="card">
          <div className="table-wrap"><table>
            <thead><tr><th></th><th>Product</th><th>Variant</th><th>Status</th><th>3D</th><th>Dimensions</th><th>Latest price</th><th>Checked</th></tr></thead>
            <tbody>
              {list.data?.items.flatMap((p) => p.variants.map((v, i) => (
                <tr key={v.id} className="click" onClick={() => nav(`/variants/${v.id}`)}>
                  <td>{i === 0 && (p.thumbnail_url ? <img className="thumb" src={p.thumbnail_url} alt="" /> : <div className="thumb" />)}</td>
                  <td>{i === 0 && <><b>{p.name}</b><div className="small muted">{p.retailer.name}{p.category ? ` · ${p.category.name}` : ""}</div></>}</td>
                  <td>{v.variant_label || v.variant_key}{v.configuration !== "standard" && <span className="chip" style={{ marginLeft: 6 }}>{v.configuration}</span>}</td>
                  <td><VariantBadge status={v.status} /></td>
                  <td>{v.asset_ready ? <AssetBadge status="qualified" /> : <AssetBadge status={v.latest_asset_status} />}</td>
                  <td className="num small">{dims(v.dimension?.width_m, v.dimension?.depth_m, v.dimension?.height_m)}</td>
                  <td className="num">{pkr(v.latest_price?.price_pkr)}</td>
                  <td className="small muted">{date(v.latest_price?.checked_at)}</td>
                </tr>
              )))}
            </tbody>
          </table></div>
        </div>
      )}
      <div className="row between">
        <span className="muted small">{list.data?.total ?? 0} products</span>
        <div className="row">
          <button className="btn small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="small">Page {page} of {pages}</span>
          <button className="btn small" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}
