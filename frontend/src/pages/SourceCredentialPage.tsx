import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";

const SUPPORTED = new Set(["coles", "openfeed"]);

export function SourceCredentialPage() {
  const { sourceType = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const personId = user?.person?.id;
  const [configured, setConfigured] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const [refreshToken, setRefreshToken] = useState("");
  const [lookbackDays, setLookbackDays] = useState("90");
  const LOOKBACK_MAX = 730;
  const [jwksUri, setJwksUri] = useState("");
  const [grantId, setGrantId] = useState<string | null>(null);
  const [appConfigured, setAppConfigured] = useState(true);

  const supported = SUPPORTED.has(sourceType);
  const label = SOURCE_LABELS[sourceType] || sourceType;
  const isOpenfeed = sourceType === "openfeed";

  useEffect(() => {
    const connected = searchParams.get("connected");
    const err = searchParams.get("error");
    if (connected) {
      setMessage(
        searchParams.get("grant")
          ? "OpenFeed 已授权并完成数据同意"
          : "OpenFeed 已连接",
      );
      setSearchParams({}, { replace: true });
    } else if (err) {
      setError(decodeURIComponent(err));
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!personId || !supported) return;
    api<{ person: { credentials?: { source_type: string; updated_at: string }[] } }>(
      `/api/v1/people/${personId}`,
    ).then((d) => {
      const cred = d.person.credentials?.find((c) => c.source_type === sourceType);
      setConfigured(Boolean(cred));
      setUpdatedAt(cred?.updated_at ?? null);
    });
    if (isOpenfeed) {
      api<{
        app_configured: boolean;
        connected: boolean;
        grant_id?: string | null;
        lookback_days?: number;
        jwks_uri?: string;
      }>("/api/v1/sources/openfeed/status").then((s) => {
        setAppConfigured(s.app_configured);
        setConfigured(s.connected);
        setGrantId(s.grant_id || null);
        if (s.lookback_days) setLookbackDays(String(s.lookback_days));
        if (s.jwks_uri) setJwksUri(s.jwks_uri);
      });
    }
  }, [personId, sourceType, supported, isOpenfeed]);

  if (!supported) {
    return <Navigate to="/account" replace />;
  }

  async function saveColes(e: FormEvent) {
    e.preventDefault();
    if (!personId) return;
    setError("");
    setMessage("");
    try {
      await api(`/api/v1/people/${personId}/credentials/coles`, {
        method: "PUT",
        body: JSON.stringify({
          label: "Coles",
          payload: { refresh_token: refreshToken.trim() },
        }),
      });
      setRefreshToken("");
      setConfigured(true);
      setUpdatedAt(new Date().toISOString());
      setMessage("已保存");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  async function clearCred() {
    if (!personId) return;
    setError("");
    await api(`/api/v1/people/${personId}/credentials/${sourceType}`, {
      method: "DELETE",
    });
    setConfigured(false);
    setUpdatedAt(null);
    setGrantId(null);
    setMessage("已清除 credential");
  }

  async function connectOpenfeed() {
    setError("");
    setMessage("");
    setConnecting(true);
    try {
      const res = await api<{ authorize_url: string }>(
        "/api/v1/sources/openfeed/connect",
      );
      window.location.href = res.authorize_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "无法开始 OpenFeed 授权");
      setConnecting(false);
    }
  }

  async function sync() {
    if (!personId) return;
    setError("");
    setMessage("");
    setSyncing(true);
    try {
      const path =
        sourceType === "openfeed"
          ? "/api/v1/sources/openfeed/sync"
          : "/api/v1/sources/coles/sync";
      const days = Math.min(
        Math.max(Number(lookbackDays) || 90, 1),
        LOOKBACK_MAX,
      );
      const body =
        sourceType === "openfeed"
          ? {
              person_id: personId,
              async: true,
              lookback_days: days,
            }
          : { person_id: personId, async: true };

      const started = await api<{
        job_id?: string;
        fetched?: number;
        imported?: number;
        skipped?: number;
        error?: string;
      }>(path, { method: "POST", body: JSON.stringify(body) });

      if (started.job_id) {
        setMessage("同步任务已排队…");
        const jobResult = await pollJob(started.job_id);
        if (jobResult.error) setError(jobResult.error);
        else {
          const r = jobResult.result || {};
          if (r.error) setError(String(r.error));
          else {
            setMessage(
              `同步完成：导入 ${r.imported ?? 0}，更新 ${r.updated ?? 0}，跳过 ${r.skipped ?? 0}`,
            );
          }
        }
      } else if (started.error) {
        setError(started.error);
      } else {
        setMessage(
          `同步完成：导入 ${started.imported ?? 0}，跳过 ${started.skipped ?? 0}`,
        );
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "同步失败");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <div>
        <Link to="/account" className="text-sm text-ink-500 hover:text-ink-800">
          ← 账户
        </Link>
        <div className="mt-4 flex items-center gap-4">
          <SourceLogo source={sourceType} className="h-12 w-12" />
          <div>
            <h1 className="font-display text-3xl text-ink-800">{label}</h1>
            <p className="text-sm text-ink-400">
              {configured
                ? `已连接${updatedAt ? ` · ${new Date(updatedAt).toLocaleString()}` : ""}`
                : "未连接"}
              {grantId ? ` · grant ${grantId.slice(0, 8)}…` : ""}
            </p>
          </div>
        </div>
      </div>

      {isOpenfeed ? (
        <div className="space-y-5">
          <p className="text-sm text-ink-600">
            通过 OpenFeed（CDR）授权银行账户。不再使用 BankSync。首次需在 OpenFeed
            登录并勾选要分享的账户。
          </p>
          {!appConfigured && (
            <p className="text-sm text-red-700">
              服务器尚未配置 OpenFeed（CLIENT_ID / 密钥 / APP_PUBLIC_URL）。见部署说明。
            </p>
          )}
          {jwksUri && (
            <p className="break-all text-xs text-ink-400">
              jwksUri：{jwksUri}
              <br />
              OpenFeed 文档要求 HTTPS；若注册拒绝 HTTP，可改用 Inline JWKS（同一公钥）。
            </p>
          )}
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">回溯天数</span>
            <input
              className="field"
              value={lookbackDays}
              onChange={(e) => setLookbackDays(e.target.value)}
              inputMode="numeric"
            />
            <p className="mt-1.5 text-xs text-ink-400">
              CDR 通常最多约 730 天。大范围按约 90 天一段拉取。
            </p>
          </label>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="btn-primary"
              onClick={connectOpenfeed}
              disabled={connecting || !appConfigured}
            >
              {connecting ? "跳转中…" : configured ? "重新授权" : "连接 OpenFeed"}
            </button>
            {configured && (
              <>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={sync}
                  disabled={syncing}
                >
                  {syncing ? "同步中…" : "同步账单"}
                </button>
                <button type="button" className="btn-ghost" onClick={clearCred}>
                  断开
                </button>
              </>
            )}
          </div>
        </div>
      ) : (
        <form onSubmit={saveColes} className="space-y-5">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">Refresh token</span>
            <textarea
              className="field min-h-[5rem] font-mono text-sm"
              value={refreshToken}
              onChange={(e) => setRefreshToken(e.target.value)}
              required={!configured}
              placeholder={configured ? "留空则不改" : ""}
            />
          </label>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          <div className="flex flex-wrap gap-3">
            <button type="submit" className="btn-primary">
              保存
            </button>
            {configured && (
              <>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={sync}
                  disabled={syncing}
                >
                  {syncing ? "同步中…" : "同步账单"}
                </button>
                <button type="button" className="btn-ghost" onClick={clearCred}>
                  清除
                </button>
              </>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

async function pollJob(jobId: string): Promise<{
  error?: string;
  result?: Record<string, unknown>;
}> {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const job = await api<{
      status: string;
      error?: string;
      result?: Record<string, unknown>;
    }>(`/api/v1/sources/jobs/${jobId}`);
    if (job.status === "finished" || job.status === "failed") {
      return { error: job.error, result: job.result };
    }
  }
  return { error: "同步超时，请稍后在流水页查看是否已导入" };
}
