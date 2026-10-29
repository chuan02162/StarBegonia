import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";

const SUPPORTED = new Set(["coles", "commbank"]);

export function SourceCredentialPage() {
  const { sourceType = "" } = useParams();
  const { user } = useAuth();
  const personId = user?.person?.id;
  const [configured, setConfigured] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);

  const [refreshToken, setRefreshToken] = useState("");
  const [lookbackDays, setLookbackDays] = useState("90");
  /** One account number per line — never loads other people's full account list. */
  const [accountNumbersText, setAccountNumbersText] = useState("");
  const [verifyHint, setVerifyHint] = useState("");

  const supported = SUPPORTED.has(sourceType);
  const label = SOURCE_LABELS[sourceType] || sourceType;

  useEffect(() => {
    if (!personId || !supported) return;
    api<{ person: { credentials?: { source_type: string; updated_at: string }[] } }>(
      `/api/v1/people/${personId}`,
    ).then((d) => {
      const cred = d.person.credentials?.find((c) => c.source_type === sourceType);
      setConfigured(Boolean(cred));
      setUpdatedAt(cred?.updated_at ?? null);
    });
  }, [personId, sourceType, supported]);

  if (!supported) {
    return <Navigate to="/account" replace />;
  }

  function parseAccountNumbers(): string[] {
    return accountNumbersText
      .split(/[\n,]+/)
      .map((s) => s.replace(/\D/g, ""))
      .filter(Boolean);
  }

  async function verifyAccounts() {
    setError("");
    setVerifyHint("");
    const nums = parseAccountNumbers();
    if (!nums.length) {
      setError("请先填写账户号");
      return;
    }
    try {
      const res = await api<{
        matched: { account_number: string; account_name: string | null }[];
        unmatched: string[];
      }>("/api/v1/sources/commbank/verify-accounts", {
        method: "POST",
        body: JSON.stringify({ account_numbers: nums }),
      });
      const ok = (res.matched || [])
        .map((m) => `${m.account_name || "账户"} · ${m.account_number}`)
        .join("；");
      const bad = (res.unmatched || []).join("、");
      setVerifyHint(
        [
          ok ? `已匹配：${ok}` : "",
          bad ? `未找到：${bad}` : "",
        ]
          .filter(Boolean)
          .join("。") || "无结果",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "校验失败");
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!personId) return;
    setError("");
    setMessage("");
    try {
      const nums = parseAccountNumbers();
      if (sourceType === "commbank" && nums.length === 0) {
        setError("请填写你自己的 CommBank 账户号（不会列出他人账户）");
        return;
      }
      const payload =
        sourceType === "coles"
          ? { refresh_token: refreshToken.trim() }
          : {
              account_numbers: nums,
              lookback_days: Number(lookbackDays) || 90,
              skip_pending: true,
            };
      await api(`/api/v1/people/${personId}/credentials/${sourceType}`, {
        method: "PUT",
        body: JSON.stringify({ label, payload }),
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
    if (!personId || !configured) return;
    await api(`/api/v1/people/${personId}/credentials/${sourceType}`, {
      method: "DELETE",
    });
    setConfigured(false);
    setUpdatedAt(null);
    setAccountNumbersText("");
    setMessage("已清除 credential");
  }

  async function sync() {
    if (!personId) return;
    setError("");
    setMessage("");
    setSyncing(true);
    try {
      const path =
        sourceType === "commbank"
          ? "/api/v1/sources/commbank/sync"
          : "/api/v1/sources/coles/sync";
      const body =
        sourceType === "commbank"
          ? {
              person_id: personId,
              async: true,
              lookback_days: Number(lookbackDays) || 90,
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
          setMessage(
            `同步完成：拉取 ${r.fetched ?? "?"}，新增 ${r.imported ?? "?"}，跳过 ${r.skipped ?? "?"}`,
          );
        }
      } else if (started.error) {
        setError(started.error);
      } else {
        setMessage(
          `同步完成：拉取 ${started.fetched ?? "?"}，新增 ${started.imported ?? "?"}，跳过 ${started.skipped ?? "?"}`,
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
        <Link to="/account" className="text-sm text-ink-600 hover:text-ink-800">
          ← 返回账户
        </Link>
        <div className="mt-4 flex items-center gap-4">
          <SourceLogo source={sourceType} className="h-12 w-12" />
          <div>
            <h1 className="font-display text-3xl text-ink-800">{label}</h1>
            <p className="mt-1 text-sm text-ink-400">
              {configured
                ? `已连接${updatedAt ? ` · ${new Date(updatedAt).toLocaleString()}` : ""}`
                : "未配置"}
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={save} className="space-y-5">
        {sourceType === "coles" ? (
          <>
            <label className="block">
              <span className="mb-1.5 block text-sm text-ink-600">refreshToken</span>
              <textarea
                className="field min-h-[7rem] font-mono text-xs"
                value={refreshToken}
                onChange={(e) => setRefreshToken(e.target.value)}
                required
                autoComplete="off"
                placeholder="从浏览器 Cookie 复制 refreshToken"
              />
            </label>
            <p className="text-sm text-ink-400">
              登录 Coles 网站后，在开发者工具 Application → Cookies 中复制即可。
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-ink-500">
              项目共用 BankSync Key。请只填写<strong className="font-medium text-ink-700">你自己的</strong>
              账户号（NetBank 里可见，如 11070639），每行一个。不会向你展示家庭其他成员的账户列表。
            </p>
            <label className="block">
              <span className="mb-1.5 block text-sm text-ink-600">账户号</span>
              <textarea
                className="field min-h-[5rem] font-mono text-sm"
                value={accountNumbersText}
                onChange={(e) => setAccountNumbersText(e.target.value)}
                placeholder={"11070639\n28721148"}
                required
              />
            </label>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={verifyAccounts}
              >
                校验账户号
              </button>
            </div>
            {verifyHint && <p className="text-sm text-ink-600">{verifyHint}</p>}
            <label className="block">
              <span className="mb-1.5 block text-sm text-ink-600">回溯天数</span>
              <input
                className="field"
                value={lookbackDays}
                onChange={(e) => setLookbackDays(e.target.value)}
                inputMode="numeric"
              />
            </label>
          </>
        )}

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
    </div>
  );
}

async function pollJob(jobId: string): Promise<{
  result?: { fetched?: number; imported?: number; skipped?: number };
  error?: string;
}> {
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const job = await api<{
      status: string;
      result?: {
        fetched?: number;
        imported?: number;
        skipped?: number;
        error?: string;
      };
      error?: string;
    }>(`/api/v1/sources/jobs/${jobId}`);
    if (job.status === "finished") {
      if (job.result?.error) return { error: job.result.error };
      return { result: job.result };
    }
    if (job.status === "failed") {
      return { error: job.error || "job failed" };
    }
  }
  return { error: "同步超时，请稍后在流水中查看" };
}
