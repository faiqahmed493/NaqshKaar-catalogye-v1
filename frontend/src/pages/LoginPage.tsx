import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorBox, Field } from "../components/ui";

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={loc.state?.from ?? "/"} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      nav(loc.state?.from ?? "/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="card card-pad stack" onSubmit={submit}>
        <div>
          <div className="label">Naqshkaar</div>
          <h1>Catalogue Studio</h1>
          <p className="muted" style={{ margin: "6px 0 0" }}>Prepare buyable Pakistani products with verified prices, real dimensions and metric 3D models.</p>
        </div>
        <ErrorBox error={error} />
        <Field label="Email"><input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
        <Field label="Password"><input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
        <button className="btn primary" disabled={busy} type="submit">{busy ? "Signing in…" : "Sign in"}</button>
        <div className="small muted">First admin: set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD (see SETUP.md).</div>
      </form>
    </div>
  );
}
