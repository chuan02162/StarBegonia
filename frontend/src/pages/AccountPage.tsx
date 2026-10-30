import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import type { Household, Invite, Person } from "../types";

type SourceInfo = {
  source_type: string;
  supports_sync: boolean;
  implemented: boolean;
};

const CONNECTABLE = ["coles", "commbank"];

export function AccountPage() {
  const { user, refresh } = useAuth();
  const personId = user?.person?.id;
  const [displayName, setDisplayName] = useState(user?.person?.display_name || "");
  const [nameMsg, setNameMsg] = useState("");
  const [household, setHousehold] = useState<Household | null>(null);
  const [pendingInvites, setPendingInvites] = useState<Invite[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [hhName, setHhName] = useState("");
  const [hint, setHint] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [person, setPerson] = useState<Person | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [jevMsg, setJevMsg] = useState("");
  const [jevContext, setJevContext] = useState("");
  const [jevContextMsg, setJevContextMsg] = useState("");
  const [showJevContext, setShowJevContext] = useState(false);

  const loadHousehold = useCallback(async () => {
    const data = await api<{
      household: Household | null;
      pending_invites: Invite[];
    }>("/api/v1/households/me");
    setHousehold(data.household);
    setJevContext(data.household?.jev_context || "");
    setPendingInvites(data.pending_invites || []);
    if (data.household?.my_role === "owner") {
      const inv = await api<{ invites: Invite[] }>("/api/v1/households/invites");
      setInvites(inv.invites);
    } else {
      setInvites([]);
    }
  }, []);

  useEffect(() => {
    setDisplayName(user?.person?.display_name || "");
  }, [user?.person?.display_name]);

  useEffect(() => {
    if (!personId) return;
    Promise.all([
      loadHousehold(),
      api<{ sources: SourceInfo[] }>("/api/v1/sources"),
      api<{ person: Person }>(`/api/v1/people/${personId}`),
    ])
      .then(([, src, p]) => {
        setSources(src.sources);
        setPerson(p.person);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载账户失败"),
      );
  }, [personId, loadHousehold]);

  async function saveName(e: FormEvent) {
    e.preventDefault();
    if (!personId) return;
    setNameMsg("");
    setError("");
    try {
      await api(`/api/v1/people/${personId}`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: displayName }),
      });
      await refresh();
      setNameMsg("已更新显示名");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  async function createHousehold(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/households", {
        method: "POST",
        body: JSON.stringify({ name: hhName }),
      });
      setHhName("");
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function leaveHousehold() {
    if (!confirm("退出后仍可查看此前共享的旧账单，但看不到家庭之后的新账单。确定退出？")) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/households/leave", { method: "POST", body: "{}" });
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "退出失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveJevContext(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setJevContextMsg("");
    try {
      const data = await api<{ household: Household }>("/api/v1/households/me", {
        method: "PATCH",
        body: JSON.stringify({ jev_context: jevContext }),
      });
      setHousehold(data.household);
      setJevContext(data.household.jev_context || "");
      setJevContextMsg("已保存 Jev 提示词");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function runFullJev() {
    if (
      !confirm(
        "将对家庭可见的全部条目重新跑 Jev（覆盖现有自动分类），并清理已删除的分类。确定？",
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setJevMsg("排队全量 Jev…");
    try {
      const res = await api<{
        job_id?: string;
        status?: string;
        classified?: number;
        requested?: number;
      }>("/api/v1/categories/classify", {
        method: "POST",
        body: JSON.stringify({
          full: true,
          scope: "household",
          only_unclassified: false,
          limit: 5000,
          async: true,
        }),
      });
      if (res.job_id) {
        setJevMsg(`已排队 job ${res.job_id}，后台跑完后分类会更新`);
      } else {
        setJevMsg(`已分类 ${res.classified ?? 0}/${res.requested ?? 0} 条`);
      }
    } catch (err) {
      setJevMsg("");
      setError(err instanceof ApiError ? err.message : "全量 Jev 失败");
    } finally {
      setBusy(false);
    }
  }

  async function createCodeInvite(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/v1/households/invites", {
        method: "POST",
        body: JSON.stringify({ display_name_hint: hint || null }),
      });
      setHint("");
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "生成邀请失败");
    }
  }

  async function inviteEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/api/v1/households/invites", {
        method: "POST",
        body: JSON.stringify({ email: inviteEmail }),
      });
      setInviteEmail("");
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "邀请失败");
    }
  }

  async function joinWithCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/households/join", {
        method: "POST",
        body: JSON.stringify({ code: joinCode }),
      });
      setJoinCode("");
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加入失败");
    } finally {
      setBusy(false);
    }
  }

  async function acceptPending(invite: Invite) {
    setBusy(true);
    setError("");
    try {
      await api("/api/v1/households/join", {
        method: "POST",
        body: JSON.stringify({ invite_id: invite.id }),
      });
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "接受失败");
    } finally {
      setBusy(false);
    }
  }

  async function declinePending(invite: Invite) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/households/invites/${invite.id}/decline`, {
        method: "POST",
        body: "{}",
      });
      await loadHousehold();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "拒绝失败");
    } finally {
      setBusy(false);
    }
  }

  const platforms = CONNECTABLE.map((type) => {
    const meta = sources.find((s) => s.source_type === type);
    const cred = person?.credentials?.find((c) => c.source_type === type);
    return {
      type,
      label: SOURCE_LABELS[type] || type,
      configured: Boolean(cred),
      implemented: meta?.implemented ?? true,
    };
  });

  const isOwner = household?.my_role === "owner";

  return (
    <div className="space-y-14">
      <div>
        <h1 className="font-display text-3xl text-ink-800">账户</h1>
        <p className="mt-2 text-ink-500">{user?.email}</p>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <section className="max-w-md space-y-4">
        <h2 className="font-display text-xl text-ink-800">个人资料</h2>
        <form onSubmit={saveName} className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">显示名</span>
            <input
              className="field"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </label>
          {nameMsg && <p className="text-sm text-ink-600">{nameMsg}</p>}
          <button type="submit" className="btn-primary">
            保存名字
          </button>
        </form>
      </section>

      <section className="space-y-5">
        <div>
          <h2 className="font-display text-xl text-ink-800">家庭</h2>
          <p className="mt-1 text-sm text-ink-500">
            同一家庭共享账单；退出后仍可看旧账，看不到之后的新账
          </p>
        </div>

        {pendingInvites.length > 0 && (
          <div className="space-y-3 rounded-lg bg-ink-50/80 p-4 ring-1 ring-ink-100">
            <p className="text-sm font-medium text-ink-700">待处理邀请</p>
            {pendingInvites.map((inv) => (
              <div
                key={inv.id}
                className="flex flex-wrap items-center justify-between gap-3"
              >
                <p className="text-sm text-ink-600">
                  加入「{inv.household_name || "家庭"}」
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="btn-primary text-sm"
                    disabled={busy}
                    onClick={() => acceptPending(inv)}
                  >
                    接受
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-sm"
                    disabled={busy}
                    onClick={() => declinePending(inv)}
                  >
                    拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {household ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="font-display text-2xl text-ink-800">{household.name}</p>
                <p className="text-sm text-ink-400">
                  {isOwner ? "你是创建者" : "成员"} · {(household.members || []).length}{" "}
                  人
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to="/dedup" className="btn-ghost text-sm">
                  查看去重账单
                </Link>
                <Link to="/transfers" className="btn-ghost text-sm">
                  查看内部账单
                </Link>
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  disabled={busy}
                  onClick={() => setShowJevContext((v) => !v)}
                >
                  编辑 Jev 提示词
                </button>
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  disabled={busy}
                  onClick={runFullJev}
                >
                  全量跑 Jev
                </button>
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  disabled={busy}
                  onClick={leaveHousehold}
                >
                  退出家庭
                </button>
              </div>
            </div>
            {jevMsg && <p className="text-sm text-ink-500">{jevMsg}</p>}

            {showJevContext && (
              <form
                onSubmit={saveJevContext}
                className="space-y-3 rounded-lg bg-ink-50/80 p-4 ring-1 ring-ink-100"
              >
                <p className="text-sm font-medium text-ink-700">发给 Jev 的家庭背景</p>
                <p className="text-sm text-ink-500">
                  例如：我在 Neo Networks 工作，工资常显示为 PAY FOR…；Origin
                  是电费不是房租。会附加到每次自动分类请求里。
                </p>
                <textarea
                  className="field min-h-[7rem]"
                  value={jevContext}
                  onChange={(e) => setJevContext(e.target.value)}
                  maxLength={4000}
                  placeholder="我在 xx 公司工作…"
                />
                <div className="flex flex-wrap items-center gap-3">
                  <button type="submit" className="btn-primary text-sm" disabled={busy}>
                    保存提示词
                  </button>
                  {jevContextMsg && (
                    <p className="text-sm text-ink-500">{jevContextMsg}</p>
                  )}
                </div>
              </form>
            )}

            <ul className="divide-y divide-ink-100">
              {(household.members || []).map((m) => (
                <li key={m.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-ink-800">{m.display_name}</p>
                    <p className="text-sm text-ink-400">{m.email}</p>
                  </div>
                  <span className="text-xs text-ink-400">
                    {m.role === "owner" ? "创建者" : "成员"}
                  </span>
                </li>
              ))}
            </ul>

            <div className="flex flex-wrap gap-3 border-t border-ink-100 pt-4">
              <Link
                to="/aa"
                className="rounded-md bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-700"
              >
                AA 规则
              </Link>
              <Link
                to="/settlements"
                className="rounded-md border border-ink-300 px-4 py-2 text-sm text-ink-800 hover:bg-ink-50"
              >
                结算中心
              </Link>
            </div>

            {isOwner && (
              <div className="space-y-6 pt-2">
                <form
                  onSubmit={createCodeInvite}
                  className="flex max-w-md flex-wrap items-end gap-3"
                >
                  <label className="block flex-1">
                    <span className="mb-1.5 block text-sm text-ink-600">
                      邀请码备注（可选）
                    </span>
                    <input
                      className="field"
                      value={hint}
                      onChange={(e) => setHint(e.target.value)}
                    />
                  </label>
                  <button type="submit" className="btn-primary">
                    生成邀请码
                  </button>
                </form>

                <form
                  onSubmit={inviteEmailSubmit}
                  className="flex max-w-md flex-wrap items-end gap-3"
                >
                  <label className="block flex-1">
                    <span className="mb-1.5 block text-sm text-ink-600">
                      用邮箱邀请（已有账号直接收到；新用户可用同一码注册）
                    </span>
                    <input
                      className="field"
                      type="email"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      required
                      placeholder="friend@example.com"
                    />
                  </label>
                  <button type="submit" className="btn-primary">
                    发送邀请
                  </button>
                </form>

                <ul className="divide-y divide-ink-100">
                  {invites.map((inv) => (
                    <li
                      key={inv.id}
                      className="flex flex-wrap items-center justify-between gap-3 py-4"
                    >
                      <div>
                        <p className="font-mono text-sm text-ink-800">{inv.code}</p>
                        <p className="text-sm text-ink-400">
                          {inv.target_email
                            ? `邮箱 ${inv.target_email}`
                            : inv.display_name_hint || "邀请码"}
                          {" · "}
                          {inv.status || (inv.used ? "已使用" : "待使用")}
                        </p>
                      </div>
                      {inv.status === "pending" && !inv.used && (
                        <button
                          type="button"
                          className="btn-ghost text-sm"
                          onClick={() =>
                            navigator.clipboard.writeText(
                              `${window.location.origin}/register?code=${inv.code}`,
                            )
                          }
                        >
                          复制注册链接
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="grid max-w-lg gap-8 sm:grid-cols-2">
            <form onSubmit={createHousehold} className="space-y-3">
              <p className="text-sm font-medium text-ink-700">组建家庭</p>
              <input
                className="field"
                placeholder="家庭名称"
                value={hhName}
                onChange={(e) => setHhName(e.target.value)}
                required
              />
              <button type="submit" className="btn-primary" disabled={busy}>
                创建
              </button>
            </form>
            <form onSubmit={joinWithCode} className="space-y-3">
              <p className="text-sm font-medium text-ink-700">加入别人的家庭</p>
              <input
                className="field"
                placeholder="邀请码"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                required
              />
              <button type="submit" className="btn-ghost" disabled={busy}>
                加入
              </button>
            </form>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="font-display text-xl text-ink-800">数据源</h2>
        <p className="text-sm text-ink-500">连接超市 / 银行等平台，用于同步账单</p>
        <ul className="divide-y divide-ink-100">
          {platforms.map((p) => (
            <li key={p.type}>
              <Link
                to={`/account/sources/${p.type}`}
                className="flex items-center gap-4 py-4 transition-colors hover:bg-ink-50/60"
              >
                <SourceLogo source={p.type} />
                <div className="min-w-0 flex-1">
                  <p className="text-ink-800">{p.label}</p>
                  <p className="text-sm text-ink-400">
                    {p.configured ? "已连接" : "未配置"}
                  </p>
                </div>
                <span className="text-sm text-ink-500">配置 →</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
