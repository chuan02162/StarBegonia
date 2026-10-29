import { useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell, Field } from "./LoginPage";

export function RegisterPage() {
  const { user, loading, needsBootstrap, register } = useAuth();
  const [params] = useSearchParams();
  const [inviteCode, setInviteCode] = useState(params.get("code") || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && needsBootstrap) return <Navigate to="/bootstrap" replace />;
  if (!loading && user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(inviteCode, email, password, displayName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="接受邀请" subtitle="用邀请码加入家庭账本">
      <form onSubmit={onSubmit} className="space-y-5">
        <Field label="邀请码">
          <input
            className="field"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            required
          />
        </Field>
        <Field label="显示名（AA 身份）">
          <input
            className="field"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
          />
        </Field>
        <Field label="邮箱">
          <input
            className="field"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field label="密码">
          <input
            className="field"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </Field>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? "注册中…" : "加入"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink-500">
        已有账号？{" "}
        <Link to="/login" className="text-ink-700 underline-offset-2 hover:underline">
          去登录
        </Link>
      </p>
    </AuthShell>
  );
}
