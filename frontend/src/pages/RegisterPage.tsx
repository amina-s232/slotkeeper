import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../auth/AuthContext";
import { ErrorBanner, fieldError } from "../components/ErrorBanner";

export function RegisterPage() {
  const { register, user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await register(form);
      navigate(homeFor(created.role), { replace: true });
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  const fields = [
    { key: "full_name", label: "Full name", type: "text", auto: "name", required: true },
    { key: "email", label: "Email", type: "email", auto: "email", required: true },
    { key: "phone", label: "Phone (optional)", type: "tel", auto: "tel", required: false },
    { key: "password", label: "Password", type: "password", auto: "new-password", required: true },
  ] as const;

  return (
    <section className="narrow">
      <h1>Create an account</h1>
      <form onSubmit={submit} className="form">
        {fields.map((f) => (
          <label key={f.key}>
            {f.label}
            <input type={f.type} value={form[f.key]} onChange={set(f.key)} autoComplete={f.auto} required={f.required} />
            {fieldError(error, f.key) && <span className="field-error">{fieldError(error, f.key)}</span>}
          </label>
        ))}
        <ErrorBanner error={error} />
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p>
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </section>
  );
}
