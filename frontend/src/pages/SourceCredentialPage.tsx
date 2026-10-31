import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { JobProgressBar } from "../components/JobProgressBar";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import { pollJob, type JobProgress } from "../lib/jobs";
import {
  refreshSourceStatus,
  setSourceConnected,
  useSourceStatus,
} from "../lib/sourceStatus";

const SUPPORTED = new Set(["coles", "commbank", "wws"]);

const WWS_EXTENSION_ID = "knppbagkjkgnbfjikkfcadpdmpinkfic";
const MY_ACTIVITY_URL =
  "https://www.everyday.com.au/content/everyday/en/home/MyAccount/my-activity.html";

export function SourceCredentialPage() {
  const { sourceType = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const personId = user?.person?.id;
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState<JobProgress | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [showFullSync, setShowFullSync] = useState(false);
  const sourceStatus = useSourceStatus();

  const [refreshToken, setRefreshToken] = useState("");
  const [jwksUri, setJwksUri] = useState("");
  const [grantId, setGrantId] = useState<string | null>(null);
  const [appConfigured, setAppConfigured] = useState(true);

  const supported = SUPPORTED.has(sourceType);
  const label = SOURCE_LABELS[sourceType] || sourceType;
  const isCommBank = sourceType === "commbank";
  const isWws = sourceType === "wws";
  const connected = sourceStatus[sourceType];

  useEffect(() => {
    const connected = searchParams.get("connected");
    const err = searchParams.get("error");
    if (connected) {
      setMessage(
        searchParams.get("grant")
          ? "CommBank 已授权并完成数据同意"
          : "CommBank 已连接",
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
      setUpdatedAt(cred?.updated_at ?? null);
    });
    if (isCommBank) {
      api<{
        app_configured: boolean;
        connected: boolean;
        grant_id?: string | null;
        lookback_days?: number;
        jwks_uri?: string;
      }>("/api/v1/sources/commbank/status").then((s) => {
        setAppConfigured(s.app_configured);
        setGrantId(s.grant_id || null);
        if (s.jwks_uri) setJwksUri(s.jwks_uri);
      });
    }
    refreshSourceStatus().catch(() => undefined);
  }, [personId, sourceType, supported, isCommBank]);

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
      setSourceConnected("coles", true);
      setUpdatedAt(new Date().toISOString());
      setMessage("已保存");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  async function clearCred() {
    if (!personId) return;
    setError("");
    await api(
      isWws
        ? "/api/v1/sources/wws/credential"
        : `/api/v1/people/${personId}/credentials/${sourceType}`,
      {
      method: "DELETE",
      },
    );
    setSourceConnected(sourceType, false);
    setUpdatedAt(null);
    setGrantId(null);
    setMessage("已清除 credential");
  }

  async function pollWwsToken(
    timeoutMs: number,
  ): Promise<{ token: string; userAgent: string } | null> {
    const deadline = Date.now() + timeoutMs;
    const chromeRuntime = (window as unknown as {
      chrome?: { runtime?: { sendMessage?: (id: string, msg: unknown) => Promise<unknown> } };
    }).chrome?.runtime;
    if (!chromeRuntime?.sendMessage) return null;
    while (Date.now() < deadline) {
      try {
        const res = (await chromeRuntime.sendMessage(WWS_EXTENSION_ID, {
          type: "GET_REWARDS_TOKEN",
        })) as { token?: string; userAgent?: string } | undefined;
        if (res && typeof res.token === "string" && res.token) {
          return {
            token: res.token,
            userAgent:
              typeof res.userAgent === "string" && res.userAgent
                ? res.userAgent
                : navigator.userAgent,
          };
        }
      } catch {
        // Extension not installed or not ready yet; keep polling.
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    return null;
  }

  async function connectWws() {
    if (!personId) return;
    setError("");
    setMessage("");
    setConnecting(true);
    try {
      window.open(MY_ACTIVITY_URL, "_blank", "noopener");
      setMessage("已打开 Everyday Rewards「我的活动」，请在登录后等待页面加载…");
      const session = await pollWwsToken(180_000);
      if (!session) {
        setError(
          "没有读取到 Everyday Rewards 会话。请确认已安装扩展，并在打开的页面里登录 Everyday Rewards。",
        );
        return;
      }
      await api(`/api/v1/people/${personId}/credentials/wws`, {
        method: "PUT",
        body: JSON.stringify({
          label: "Woolworths",
          payload: {
            user_agent: session.userAgent,
            rewards_authorization: `Bearer ${session.token}`,
          },
        }),
      });
      setSourceConnected("wws", true);
      setUpdatedAt(new Date().toISOString());
      setMessage("Everyday Rewards 已连接");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "连接失败");
    } finally {
      setConnecting(false);
    }
  }

  async function connectCommBank() {
    setError("");
    setMessage("");
    setConnecting(true);
    try {
      const res = await api<{ authorize_url: string }>(
        "/api/v1/sources/commbank/connect",
      );
      window.location.href = res.authorize_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "无法开始 OpenFeed 授权");
      setConnecting(false);
    }
  }

  async function sync(fullSync = false) {
    if (!personId) return;
    setError("");
    setMessage("");
    setSyncing(true);
    setSyncProgress({
      percent: 0,
      message: fullSync ? "全量同步任务已排队…" : "增量同步任务已排队…",
    });
    try {
      const path =
        sourceType === "commbank"
          ? "/api/v1/sources/commbank/sync"
          : sourceType === "wws"
            ? "/api/v1/sources/wws/sync"
            : "/api/v1/sources/coles/sync";
      const body = {
        person_id: personId,
        async: true,
        full_sync: fullSync,
      };

      const started = await api<{
        job_id?: string;
        fetched?: number;
        imported?: number;
        updated?: number;
        skipped?: number;
        error?: string;
      }>(path, { method: "POST", body: JSON.stringify(body) });

      if (started.job_id) {
        setMessage("同步任务已排队…");
        const jobResult = await pollJob(started.job_id, {
          endpoint: "sources",
          onProgress: (p) => {
            setSyncProgress(p);
            setMessage(p.message || "同步中…");
          },
        });
        if (jobResult.error || jobResult.status === "failed") {
          setError(jobResult.error || "同步失败");
        } else {
          const r = jobResult.result || {};
          if (r.error) setError(String(r.error));
          else {
            setMessage(
              `同步完成：导入 ${r.imported ?? 0}，更新 ${r.updated ?? 0}，跳过 ${r.skipped ?? 0}`,
            );
            setSyncProgress({
              percent: 100,
              message: "同步完成",
            });
          }
        }
      } else if (started.error) {
        setError(started.error);
        setSyncProgress(null);
      } else {
        setMessage(
          `同步完成：导入 ${started.imported ?? 0}，跳过 ${started.skipped ?? 0}`,
        );
        setSyncProgress(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "同步失败");
      setSyncProgress(null);
    } finally {
      setSyncing(false);
    }
  }

  const dotClass =
    connected === true
      ? "bg-emerald-500"
      : connected === false
        ? "bg-red-500"
        : "bg-ink-200";

  const syncButtons = (
    <div className="relative inline-flex">
      <div className="inline-flex">
        <button
          type="button"
          className="btn-primary rounded-r-none"
          onClick={() => sync(false)}
          disabled={syncing}
        >
          {syncing ? "同步中…" : "增量同步"}
        </button>
        <button
          type="button"
          className="btn-primary rounded-l-none border-l border-ink-500 px-2.5"
          onClick={() => setShowFullSync((v) => !v)}
          disabled={syncing}
          aria-label="显示全量同步"
        >
          ▾
        </button>
      </div>
      {showFullSync && (
        <button
          type="button"
          className="btn-ghost absolute left-0 top-full mt-1 whitespace-nowrap"
          onClick={() => {
            setShowFullSync(false);
            sync(true);
          }}
          disabled={syncing}
        >
          全量同步
        </button>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-lg space-y-8">
      <div>
        <Link to="/account" className="text-sm text-ink-500 hover:text-ink-800">
          ← 账户
        </Link>
        <div className="mt-4 flex items-center gap-4">
          <SourceLogo source={sourceType} className="h-12 w-12" />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-3xl text-ink-800">{label}</h1>
              <span
                className={`h-2.5 w-2.5 rounded-full ${dotClass}`}
                title={
                  connected === true
                    ? "连接正常"
                    : connected === false
                      ? "未连接"
                      : ""
                }
              />
            </div>
            <p className="text-sm text-ink-400">
              {connected === true
                ? `已连接${updatedAt ? ` · ${new Date(updatedAt).toLocaleString()}` : ""}`
                : connected === false
                  ? "未连接"
                  : "检查中…"}
              {grantId ? ` · grant ${grantId.slice(0, 8)}…` : ""}
            </p>
          </div>
        </div>
      </div>

      {isCommBank ? (
        <div className="space-y-5">
          <p className="text-sm text-ink-600">
            通过 OpenFeed（CDR）授权 CommBank 银行账户。不再使用 BankSync。首次需在 OpenFeed
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
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          {(syncing || syncProgress) && (
            <JobProgressBar progress={syncProgress} active={syncing} />
          )}
          <div className="flex flex-wrap gap-3">
            {connected === false && (
              <button
                type="button"
                className="btn-primary"
                onClick={connectCommBank}
                disabled={connecting || !appConfigured}
              >
                {connecting ? "跳转中…" : "连接 CommBank"}
              </button>
            )}
            {connected === true && (
              <>
                {syncButtons}
                <button type="button" className="btn-ghost" onClick={clearCred}>
                  断开
                </button>
              </>
            )}
            {connected === undefined && (
              <p className="text-sm text-ink-400">检查连接中…</p>
            )}
          </div>
        </div>
      ) : isWws ? (
        <div className="space-y-5">
          <p className="text-sm text-ink-600">
            在 Chrome 安装 StarBegonia Everyday Rewards 扩展后，点击下方按钮会自动打开「我的活动」。登录（或已登录）后，扩展会读取 Everyday Rewards 会话并回传到 StarBegonia，无需复制绑定码。
          </p>
          <p className="text-xs text-ink-400">
            密码和验证码只在 Everyday Rewards 页面输入。凭证在后端加密保存；会话过期后重新点一下「连接」即可。
          </p>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          {(syncing || syncProgress) && (
            <JobProgressBar progress={syncProgress} active={syncing} />
          )}
          <div className="flex flex-wrap gap-3">
            {connected === false && (
              <button
                type="button"
                className="btn-primary"
                onClick={connectWws}
                disabled={connecting}
              >
                {connecting ? "连接中…" : "连接 Everyday Rewards"}
              </button>
            )}
            {connected === true && (
              <>
                {syncButtons}
                <button type="button" className="btn-ghost" onClick={clearCred}>
                  断开
                </button>
              </>
            )}
            {connected === undefined && (
              <p className="text-sm text-ink-400">检查连接中…</p>
            )}
          </div>
        </div>
      ) : connected === true ? (
        <div className="space-y-5">
          <p className="text-sm text-ink-600">Coles 已连接。</p>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          {(syncing || syncProgress) && (
            <JobProgressBar progress={syncProgress} active={syncing} />
          )}
          <div className="flex flex-wrap gap-3">
            {syncButtons}
            <button type="button" className="btn-ghost" onClick={clearCred}>
              断开
            </button>
          </div>
        </div>
      ) : connected === false ? (
        <form onSubmit={saveColes} className="space-y-5">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">Refresh token</span>
            <textarea
              className="field min-h-[5rem] font-mono text-sm"
              value={refreshToken}
              onChange={(e) => setRefreshToken(e.target.value)}
              required
            />
          </label>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          <div className="flex flex-wrap gap-3">
            <button type="submit" className="btn-primary">
              保存
            </button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-ink-400">检查连接中…</p>
      )}
    </div>
  );
}
