import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";
import { date } from "../format";
import type { Retailer, Role, User } from "../types";

interface Key { id: string; name: string; prefix: string; scopes: string[]; created_at: string; last_used_at: string | null; revoked_at: string | null }

export default function SettingsPage() {
  const { can } = useAuth();
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Settings</h1><p>Retailers, team accounts and machine keys.</p></div></div>
      <Retailers />
      {can() && <Users />}
      {can() && <ApiKeys />}
    </div>
  );
}

function Retailers() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["retailers"], queryFn: () => api.get<Retailer[]>("/api/retailers") });
  const [f, setF] = useState({ name: "", slug: "", website_url: "", city: "", usage_terms: "" });
  const [err, setErr] = useState<unknown>(null);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/api/retailers", { ...f, slug: f.slug || f.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        website_url: f.website_url || null, city: f.city || null, usage_terms: f.usage_terms || null });
      setF({ name: "", slug: "", website_url: "", city: "", usage_terms: "" });
      qc.invalidateQueries({ queryKey: ["retailers"] });
    } catch (x) { setErr(x); }
  };
  return (
    <section className="card">
      <div className="card-head"><h2>Retailers</h2></div>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Slug</th><th>Website</th><th>City</th><th>Usage terms</th></tr></thead>
        <tbody>{q.data?.map((r) => (
          <tr key={r.id}><td><b>{r.name}</b></td><td className="mono">{r.slug}</td>
            <td className="small">{r.website_url && <a href={r.website_url} target="_blank" rel="noreferrer">{r.website_url}</a>}</td>
            <td>{r.city}</td><td className="small muted">{r.usage_terms}</td></tr>
        ))}</tbody>
      </table></div>
      {can("curator") && (
        <form className="card-pad stack" onSubmit={add} style={{ borderTop: "1px solid var(--rule)" }}>
          <ErrorBox error={err} />
          <div className="grid-4">
            <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
            <Field label="Slug" hint="used by the ingest API"><input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} placeholder="auto" pattern="[a-z0-9][a-z0-9-]*" /></Field>
            <Field label="Website"><input value={f.website_url} onChange={(e) => setF({ ...f, website_url: e.target.value })} /></Field>
            <Field label="City"><input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field>
          </div>
          <Field label="Usage terms" hint="permission to use their images and listing data"><input value={f.usage_terms} onChange={(e) => setF({ ...f, usage_terms: e.target.value })} /></Field>
          <div><button className="btn" type="submit">Add retailer</button></div>
        </form>
      )}
    </section>
  );
}

function Users() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/api/users") });
  const [f, setF] = useState({ email: "", display_name: "", password: "", role: "curator" as Role });
  const [err, setErr] = useState<unknown>(null);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.post("/api/users", f); setF({ email: "", display_name: "", password: "", role: "curator" }); qc.invalidateQueries({ queryKey: ["users"] }); }
    catch (x) { setErr(x); }
  };
  const update = async (u: User, body: Partial<User>) => {
    try { await api.patch(`/api/users/${u.id}`, body); qc.invalidateQueries({ queryKey: ["users"] }); } catch (x) { setErr(x); }
  };
  return (
    <section className="card">
      <div className="card-head"><h2>Team</h2><span className="small muted">admin · curator · asset reviewer · viewer</span></div>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Active</th><th>Last sign-in</th></tr></thead>
        <tbody>{q.data?.map((u) => (
          <tr key={u.id}><td>{u.display_name}</td><td>{u.email}</td>
            <td><select value={u.role} onChange={(e) => update(u, { role: e.target.value as Role })} style={{ width: "auto" }}>
              <option value="admin">admin</option><option value="curator">curator</option><option value="asset_reviewer">asset reviewer</option><option value="viewer">viewer</option>
            </select></td>
            <td><input type="checkbox" checked={u.is_active} onChange={(e) => update(u, { is_active: e.target.checked })} /></td>
            <td className="small muted">{date(u.last_login_at)}</td></tr>
        ))}</tbody>
      </table></div>
      <form className="card-pad stack" onSubmit={add} style={{ borderTop: "1px solid var(--rule)" }}>
        <ErrorBox error={err} />
        <div className="grid-4">
          <Field label="Name"><input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} required /></Field>
          <Field label="Email"><input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></Field>
          <Field label="Temporary password" hint="10+ characters"><input type="password" minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required /></Field>
          <Field label="Role"><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            <option value="curator">curator</option><option value="asset_reviewer">asset reviewer</option><option value="viewer">viewer</option><option value="admin">admin</option>
          </select></Field>
        </div>
        <div><button className="btn" type="submit">Add team member</button></div>
      </form>
    </section>
  );
}

function ApiKeys() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["api-keys"], queryFn: () => api.get<Key[]>("/api/api-keys") });
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["worker"]);
  const [created, setCreated] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const r = await api.post<{ key: string }>("/api/api-keys", { name, scopes });
      setCreated(r.key); setName("");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    } catch (x) { setErr(x); }
  };
  const revoke = async (k: Key) => { await api.post(`/api/api-keys/${k.id}/revoke`); qc.invalidateQueries({ queryKey: ["api-keys"] }); };
  const copy = async () => { if (!created) return; try { await navigator.clipboard.writeText(created); } catch { /* select manually */ } };
  return (
    <section className="card">
      <div className="card-head"><h2>API keys</h2><span className="small muted">worker = GPU machines · ingest = your collector software · catalogue_read = the planner</span></div>
      {created && (
        <div className="card-pad"><div className="okbox stack" style={{ gap: 6 }}>
          <b>Copy this key now. It is shown only once.</b>
          <code style={{ wordBreak: "break-all", userSelect: "all" }}>{created}</code>
          <div className="row"><button className="btn small" onClick={copy}>Copy</button><button className="btn small ghost" onClick={() => setCreated(null)}>Done</button></div>
        </div></div>
      )}
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Prefix</th><th>Scopes</th><th>Created</th><th>Last used</th><th></th></tr></thead>
        <tbody>{q.data?.map((k) => (
          <tr key={k.id} style={{ opacity: k.revoked_at ? 0.5 : 1 }}><td>{k.name}</td><td className="mono">nqk_{k.prefix}_…</td>
            <td>{k.scopes.map((s) => <span key={s} className="chip" style={{ marginRight: 4 }}>{s}</span>)}</td>
            <td className="small">{date(k.created_at)}</td><td className="small">{date(k.last_used_at)}</td>
            <td>{k.revoked_at ? <span className="small muted">revoked</span> : <button className="btn small danger" onClick={() => revoke(k)}>Revoke</button>}</td></tr>
        ))}</tbody>
      </table></div>
      <form className="card-pad row" onSubmit={add} style={{ borderTop: "1px solid var(--rule)" }}>
        <ErrorBox error={err} />
        <input style={{ maxWidth: 260 }} placeholder="e.g. lab-gpu-trellis" value={name} onChange={(e) => setName(e.target.value)} required />
        {["worker", "ingest", "catalogue_read"].map((s) => (
          <label key={s} className="check"><input type="checkbox" checked={scopes.includes(s)} onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))} />{s}</label>
        ))}
        <button className="btn" type="submit" disabled={!scopes.length}>Create key</button>
      </form>
    </section>
  );
}
