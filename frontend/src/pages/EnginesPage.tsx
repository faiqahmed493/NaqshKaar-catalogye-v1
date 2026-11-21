import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { Badge, ErrorBox } from "../components/ui";
import { ago } from "../format";
import type { Engine, Worker } from "../types";

export default function EnginesPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["engines"], queryFn: () => api.get<{ engines: Engine[]; workers: Worker[] }>("/api/engines"), refetchInterval: 10_000 });
  const toggle = async (e: Engine) => {
    await api.patch(`/api/engines/${e.code}`, { is_enabled: !e.is_enabled });
    qc.invalidateQueries({ queryKey: ["engines"] });
  };
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Engines and workers</h1>
          <p>Engines are image-to-3D models. A worker is a machine running <code>python -m naqshkaar_generator</code> with one or more engines installed. See generator/README.md.</p></div>
      </div>
      <ErrorBox error={q.error} />
      <section className="card">
        <div className="card-head"><h2>Workers online</h2><span className="small muted">heartbeat within 90 s</span></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Worker</th><th>Engines</th><th>GPU</th><th>Version</th><th>Last seen</th></tr></thead>
          <tbody>
            {q.data?.workers.map((w) => (
              <tr key={w.id}><td><b>{w.id}</b><div className="small muted">{w.hostname}</div></td>
                <td>{w.engines.map((e) => <span key={e} className="chip" style={{ marginRight: 4 }}>{e}</span>)}</td>
                <td className="small">{w.gpu_name ? `${w.gpu_name} · ${w.gpu_vram_gb} GB` : "CPU"}</td>
                <td className="small mono">{w.version}</td><td className="small muted">{ago(w.last_seen_at)}</td></tr>
            ))}
            {q.data?.workers.length === 0 && <tr><td colSpan={5} className="muted">No worker connected. Start one with a worker API key (Settings → API keys).</td></tr>}
          </tbody>
        </table></div>
      </section>
      <section className="card">
        <div className="card-head"><h2>Engine registry</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Engine</th><th>Inputs</th><th>GPU</th><th>Licence</th><th>Workers</th><th>Enabled</th></tr></thead>
          <tbody>
            {q.data?.engines.map((e) => (
              <tr key={e.code}>
                <td><b>{e.display_name}</b> <code className="muted">{e.code}</code>
                  <div className="small muted" style={{ maxWidth: 420 }}>{e.notes}</div>
                  {e.homepage_url && <a className="small" href={e.homepage_url} target="_blank" rel="noreferrer">{e.homepage_url.replace("https://", "")}</a>}</td>
                <td className="small">{e.supports_multi_image ? `1–${e.max_input_images} images` : "1 image"}{e.required_views.length ? ` · needs ${e.required_views.join(", ")}` : ""}</td>
                <td className="small">{e.min_vram_gb ? `${e.min_vram_gb} GB+` : e.kind === "external_api" ? "none (API)" : "none"}</td>
                <td className="small">{e.license}{!e.is_open_source && <div><Badge tone="warn">not open source</Badge></div>}
                  {e.commercial_use_note && <div className="muted">{e.commercial_use_note}</div>}</td>
                <td><Badge tone={e.online_workers ? "good" : "muted"}>{e.online_workers}</Badge></td>
                <td>{can() ? <button className="btn small" onClick={() => toggle(e)}>{e.is_enabled ? "Disable" : "Enable"}</button>
                  : (e.is_enabled ? "yes" : "no")}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </section>
    </div>
  );
}
