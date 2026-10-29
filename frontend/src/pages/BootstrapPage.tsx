import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell, Field } from "./LoginPage";

export function BootstrapPage() {
  const { user, loading, needsBootstrap, bootstrap } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;
  if (!loading && !needsBootstrap) return <Navigate to="/login" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await bootstrap(email, password, displayName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "初始化失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="创建家庭账本" subtitle="首次使用：建立第一个成员账号">
      <form onSubmit={onSubmit} className="space-y-5">
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
          {submitting ? "创建中…" : "开始使用"}
        </button>
      </form>
    </AuthShell>
  );
}
