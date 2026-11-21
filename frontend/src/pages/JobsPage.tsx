import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, qs } from "../api";
import { ErrorBox, JobBadge, Progress } from "../components/ui";
import { ACTIVE_JOBS, ago, JOB_STATUS } from "../format";
import type { Job, JobStatus } from "../types";

export default function JobsPage() {
  const nav = useNavigate();
  const [status, setStatus] = useState("");
  const q = useQuery({
    queryKey: ["jobs", status],
    queryFn: () => api.get<{ items: Job[]; counts: Record<string, number> }>(`/api/jobs${qs({ status, limit: 100 })}`),
    refetchInterval: 4000,
  });
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>3D generation jobs</h1><p>Every request to an image-to-3D engine. Workers pull jobs from this queue; a job whose worker goes silent is re-queued.</p></div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "auto" }}>
          <option value="">All</option>
          <option value={ACTIVE_JOBS.join(",")}>Active</option>
          {(Object.keys(JOB_STATUS) as JobStatus[]).map((s) => <option key={s} value={s}>{JOB_STATUS[s].label} ({q.data?.counts[s] ?? 0})</option>)}
        </select>
      </div>
      <ErrorBox error={q.error} />
      <div className="card"><div className="table-wrap"><table>
        <thead><tr><th>Product</th><th>Engine</th><th>Status</th><th>Progress</th><th>Worker</th><th>Created</th><th>Error</th></tr></thead>
        <tbody>
          {q.data?.items.map((j) => (
            <tr key={j.id} className="click" onClick={() => nav(`/variants/${j.variant_id}?tab=3d`)}>
              <td><b>{j.product_name}</b><div className="small muted">{j.variant_label}</div></td>
              <td>{j.engine_name}</td>
              <td><JobBadge status={j.status} /></td>
              <td style={{ width: 140 }}>{ACTIVE_JOBS.includes(j.status) ? <Progress value={j.progress} /> : <span className="small muted">{j.attempts} attempt(s)</span>}</td>
              <td className="small">{j.worker_id ?? "—"}</td>
              <td className="small muted">{ago(j.created_at)}</td>
              <td className="small" style={{ color: "var(--bad)", maxWidth: 320 }}>{j.error_message}</td>
            </tr>
          ))}
          {q.data?.items.length === 0 && <tr><td colSpan={7} className="muted">No jobs.</td></tr>}
        </tbody>
      </table></div></div>
    </div>
  );
}
