import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { JobProgressBar } from "../components/JobProgressBar";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import { pollJob, type JobProgress } from "../lib/jobs";

const SUPPORTED = new Set(["coles", "commbank", "wws"]);

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
  const [syncProgress, setSyncProgress] = useState<JobProgress | null>(null);
  const [connecting, setConnecting] = useState(false);

  const [refreshToken, setRefreshToken] = useState("");
  const [lookbackDays, setLookbackDays] = useState("90");
  const LOOKBACK_MAX = 730;
  const [jwksUri, setJwksUri] = useState("");
  const [grantId, setGrantId] = useState<string | null>(null);
  const [appConfigured, setAppConfigured] = useState(true);
  const [pairingLink, setPairingLink] = useState("");
  const [pairingExpiresAt, setPairingExpiresAt] = useState<string | null>(null);

  const supported = SUPPORTED.has(sourceType);
  const label = SOURCE_LABELS[sourceType] || sourceType;
  const isCommBank = sourceType === "commbank";
  const isWws = sourceType === "wws";

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
      setConfigured(Boolean(cred));
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
        setConfigured(s.connected);
        setGrantId(s.grant_id || null);
        if (s.lookback_days) setLookbackDays(String(s.lookback_days));
        if (s.jwks_uri) setJwksUri(s.jwks_uri);
      });
    }
    if (isWws) {
      api<{ connected: boolean; updated_at?: string | null }>(
        "/api/v1/sources/wws/status",
      ).then((s) => {
        setConfigured(s.connected);
        setUpdatedAt(s.updated_at || null);
      });
    }
  }, [personId, sourceType, supported, isCommBank, isWws]);

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
    await api(
      isWws
        ? "/api/v1/sources/wws/credential"
        : `/api/v1/people/${personId}/credentials/${sourceType}`,
      {
      method: "DELETE",
      },
    );
    setConfigured(false);
    setUpdatedAt(null);
    setGrantId(null);
    setPairingLink("");
    setMessage("已清除 credential");
  }

  async function createWwsPairing() {
    setError("");
    setMessage("");
    try {
      const pairing = await api<{
        pairing_link: string;
        expires_at: string;
      }>("/api/v1/sources/wws/pairing", { method: "POST", body: "{}" });
      setPairingLink(pairing.pairing_link);
      setPairingExpiresAt(pairing.expires_at);
      setMessage("绑定码已生成，10 分钟内有效");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "无法生成绑定码");
    }
  }

  async function copyWwsPairing() {
    if (!pairingLink) return;
    try {
      await navigator.clipboard.writeText(pairingLink);
      setMessage("绑定链接已复制；扩展只需临时使用");
    } catch {
      setError("复制失败，请手动复制绑定链接");
    }
  }

  async function refreshWwsStatus() {
    setError("");
    try {
      const status = await api<{
        connected: boolean;
        updated_at?: string | null;
      }>("/api/v1/sources/wws/status");
      setConfigured(status.connected);
      setUpdatedAt(status.updated_at || null);
      setMessage(status.connected ? "Woolworths 凭证已保存" : "尚未绑定");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "状态刷新失败");
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

  async function sync() {
    if (!personId) return;
    setError("");
    setMessage("");
    setSyncing(true);
    setSyncProgress({ percent: 0, message: "同步任务已排队…" });
    try {
      const path =
        sourceType === "commbank"
          ? "/api/v1/sources/commbank/sync"
          : "/api/v1/sources/coles/sync";
      const days = Math.min(
        Math.max(Number(lookbackDays) || 90, 1),
        LOOKBACK_MAX,
      );
      const body =
        sourceType === "commbank"
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
                ? `${isWws ? "凭证已保存" : "已连接"}${updatedAt ? ` · ${new Date(updatedAt).toLocaleString()}` : ""}`
                : "未连接"}
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
          {(syncing || syncProgress) && (
            <JobProgressBar progress={syncProgress} active={syncing} />
          )}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="btn-primary"
              onClick={connectCommBank}
              disabled={connecting || !appConfigured}
            >
              {connecting ? "跳转中…" : configured ? "重新授权" : "连接 CommBank"}
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
      ) : isWws ? (
        <div className="space-y-5">
          <p className="text-sm text-ink-600">
            在 Chrome 安装 StarBegonia Woolworths 扩展。从扩展打开 Woolworths 并手动登录，然后生成绑定链接，粘贴到扩展完成绑定。密码只在 Woolworths 页面输入。
          </p>
          <p className="text-xs text-ink-400">
            扩展只读取 pastshops 请求范围内的会话 Cookie；后端加密保存。当前只完成凭证保存，尚未验证拉取订单。绑定链接只在本页内存中保留，刷新页面后需重新生成。
          </p>
          {pairingLink && (
            <label className="block">
              <span className="mb-1.5 block text-sm text-ink-600">一次性绑定链接</span>
              <textarea
                className="field min-h-[5rem] font-mono text-xs"
                value={pairingLink}
                readOnly
                onFocus={(event) => event.currentTarget.select()}
              />
              <span className="mt-1 block text-xs text-ink-400">
                到期时间：
                {pairingExpiresAt
                  ? new Date(pairingExpiresAt).toLocaleTimeString()
                  : ""}
              </span>
            </label>
          )}
          {error && <p className="text-sm text-red-700">{error}</p>}
          {message && <p className="text-sm text-ink-600">{message}</p>}
          <div className="flex flex-wrap gap-3">
            <button type="button" className="btn-primary" onClick={createWwsPairing}>
              生成绑定链接
            </button>
            {pairingLink && (
              <button type="button" className="btn-ghost" onClick={copyWwsPairing}>
                复制链接
              </button>
            )}
            <button type="button" className="btn-ghost" onClick={refreshWwsStatus}>
              刷新状态
            </button>
            {configured && (
              <button type="button" className="btn-ghost" onClick={clearCred}>
                断开
              </button>
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
          {(syncing || syncProgress) && (
            <JobProgressBar progress={syncProgress} active={syncing} />
          )}
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
