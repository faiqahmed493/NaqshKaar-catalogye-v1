import type { ReactNode } from "react";
import { ApiError } from "../api";
import { ASSET_STATUS, CHECK_LABELS, JOB_STATUS, VARIANT_STATUS } from "../format";
import type { AssetCheck, AssetStatus, Condition, JobStatus, VariantStatus } from "../types";

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge tone-${tone}`}>{children}</span>;
}

export function VariantBadge({ status }: { status: VariantStatus }) {
  const s = VARIANT_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function AssetBadge({ status }: { status: AssetStatus | null }) {
  if (!status) return <Badge tone="muted">No 3D yet</Badge>;
  const s = ASSET_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function JobBadge({ status }: { status: JobStatus }) {
  const s = JOB_STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error);
  return <div className="error" role="alert">{msg}</div>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label} {hint && <span className="hint">· {hint}</span>}</span>
      {children}
    </label>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card card-pad" style={{ textAlign: "center", padding: 32 }}>
      <h3>{title}</h3>
      {children && <div className="muted" style={{ marginTop: 6 }}>{children}</div>}
    </div>
  );
}

export function Progress({ value }: { value: number | null | undefined }) {
  return <div className="progress" aria-label="progress"><i style={{ width: `${Math.max(2, value ?? 0)}%` }} /></div>;
}

export function ConditionsList({ conditions }: { conditions: Condition[] }) {
  return (
    <div>
      {conditions.map((c) => (
        <div className="cond" key={c.code + c.label}>
          <span className={`mark ${c.passed ? "ok" : c.required ? "no" : "adv"}`}>{c.passed ? "✓" : c.required ? "✕" : "!"}</span>
          <div>
            <div className="row between">
              <b>{c.label}</b>
              <span className="chip">{c.srs}</span>
            </div>
            <div className={c.passed ? "muted small" : "small"}>{c.detail}{!c.required && !c.passed ? " (advisory)" : ""}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

const ORDER = ["file_readable", "geometry_finite", "geometry_non_degenerate", "dimensions_available", "extent_width",
  "extent_depth", "extent_height", "scale_distortion", "glb_reload", "embedded_resources", "gltf_validator",
  "triangle_budget", "visual_review"];

export function ChecksTable({ checks }: { checks: AssetCheck[] }) {
  const sorted = [...checks].sort((a, b) => ORDER.indexOf(a.code) - ORDER.indexOf(b.code));
  const tone = { pass: "good", fail: "bad", warn: "warn", not_run: "muted" } as const;
  const word = { pass: "Pass", fail: "Fail", warn: "Warning", not_run: "Not run" } as const;
  return (
    <div className="table-wrap">
      <table>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.code}>
              <td style={{ width: 110 }}><Badge tone={tone[c.outcome]}>{word[c.outcome]}</Badge></td>
              <td>
                <b>{CHECK_LABELS[c.code] ?? c.code}</b>
                {c.message && <div className="small muted">{c.message}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
