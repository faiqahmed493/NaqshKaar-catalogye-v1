import { useQuery } from "@tanstack/react-query";
import { api, qs } from "../../api";
import { ErrorBox } from "../../components/ui";
import { dateTime } from "../../format";
import type { VariantDetail } from "../../types";

interface Entry { id: number; action: string; entity_type: string; entity_id: string; details: Record<string, unknown> | null; actor_user_id: string | null; actor_api_key_id: string | null; created_at: string }

export default function HistoryTab({ v }: { v: VariantDetail }) {
  const q = useQuery({
    queryKey: ["audit", v.id],
    queryFn: async () => {
      const [variant, product] = await Promise.all([
        api.get<Entry[]>(`/api/audit${qs({ entity_type: "variant", entity_id: v.id })}`),
        api.get<Entry[]>(`/api/audit${qs({ entity_type: "product", entity_id: v.product.id })}`),
      ]);
      return [...variant, ...product].sort((a, b) => b.created_at.localeCompare(a.created_at));
    },
  });
  return (
    <div className="card">
      <ErrorBox error={q.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>When</th><th>Action</th><th>By</th><th>Details</th></tr></thead>
        <tbody>
          {q.data?.map((e) => (
            <tr key={e.id}>
              <td className="small">{dateTime(e.created_at)}</td>
              <td><code>{e.action}</code></td>
              <td className="small muted">{e.actor_api_key_id ? "API key" : e.actor_user_id ? "user" : "system"}</td>
              <td className="small mono" style={{ maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis" }}>{e.details ? JSON.stringify(e.details) : ""}</td>
            </tr>
          ))}
          {q.data?.length === 0 && <tr><td colSpan={4} className="muted">No history yet.</td></tr>}
        </tbody>
      </table></div>
    </div>
  );
}
