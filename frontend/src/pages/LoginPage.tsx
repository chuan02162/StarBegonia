import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { user, loading, needsBootstrap, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && needsBootstrap) return <Navigate to="/bootstrap" replace />;
  if (!loading && user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="登录" subtitle="进入家庭账本">
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="邮箱">
          <input
            className="field"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </Field>
        <Field label="密码">
          <input
            className="field"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </Field>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? "登录中…" : "登录"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-500">
        有邀请码？{" "}
        <Link to="/register" className="text-ink-700 underline-offset-2 hover:underline">
          注册加入
        </Link>
      </p>
    </AuthShell>
  );
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-16">
      <div className="w-full max-w-md">
        <p className="font-display text-3xl font-semibold text-ink-700">StarBegonia</p>
        <h1 className="mt-8 font-display text-2xl text-ink-800">{title}</h1>
        <p className="mt-2 text-ink-500">{subtitle}</p>
        <div className="mt-8">{children}</div>
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm text-ink-600">{label}</span>
      {children}
    </label>
  );
}
