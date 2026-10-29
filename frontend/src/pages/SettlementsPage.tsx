import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { formatMoney } from "../lib/format";
import type { Settlement } from "../types";

const GRANULARITIES = [
  { id: "week", label: "本周" },
  { id: "month", label: "本月" },
  { id: "quarter", label: "本季" },
  { id: "year", label: "今年" },
] as const;

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  confirmed: "已确认",
  settled: "已结清",
};

export function SettlementsPage() {
  const [rows, setRows] = useState<Settlement[]>([]);
  const [selected, setSelected] = useState<Settlement | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [granularity, setGranularity] = useState<string>("month");

  const load = useCallback(async () => {
    const data = await api<{ settlements: Settlement[] }>("/api/v1/settlements");
    setRows(data.settlements);
  }, []);

  useEffect(() => {
    load().catch((err) =>
      setError(err instanceof ApiError ? err.message : "加载失败"),
    );
  }, [load]);

  async function createOne() {
    setBusy(true);
    setError("");
    try {
      const res = await api<{ settlement: Settlement }>("/api/v1/settlements", {
        method: "POST",
        body: JSON.stringify({ granularity }),
      });
      setSelected(res.settlement);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function act(path: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const res = await api<{ settlement: Settlement }>(
        `/api/v1/settlements/${selected.id}/${path}`,
        { method: "POST", body: "{}" },
      );
      setSelected(res.settlement);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: Settlement) {
    if (!confirm("删除该结算草稿？")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/settlements/${row.id}`, { method: "DELETE" });
      if (selected?.id === row.id) setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  const result = selected?.result;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl text-ink-800">结算中心</h1>
        <p className="mt-2 max-w-xl text-ink-500">
          按周期套用{" "}
          <Link to="/aa" className="text-ink-700 underline">
            AA 规则
          </Link>
          ，算出成员间应付；确认后可标记结清。收入与转账不计分摊。
        </p>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-ink-600">
          周期
          <select
            className="ml-2 border border-ink-200 bg-white px-3 py-2"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value)}
          >
            {GRANULARITIES.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={createOne}
          className="rounded-md bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-700 disabled:opacity-50"
        >
          生成结算
        </button>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <ul className="divide-y divide-ink-100 border-t border-ink-100">
          {rows.map((row) => (
            <li key={row.id} className="flex items-start justify-between gap-3 py-3">
              <button
                type="button"
                className={`min-w-0 text-left ${
                  selected?.id === row.id ? "text-ink-900" : "text-ink-700"
                }`}
                onClick={() => setSelected(row)}
              >
                <p className="font-medium">
                  {row.period_start.slice(0, 10)} → {row.period_end.slice(0, 10)}
                </p>
                <p className="text-sm text-ink-500">
                  {STATUS_LABEL[row.status] || row.status}
                  {row.granularity ? ` · ${row.granularity}` : ""}
                </p>
              </button>
              {row.status !== "settled" && (
                <button
                  type="button"
                  className="text-sm text-red-700 hover:underline"
                  disabled={busy}
                  onClick={() => remove(row)}
                >
                  删除
                </button>
              )}
            </li>
          ))}
          {rows.length === 0 && (
            <li className="py-6 text-ink-400">还没有结算记录。</li>
          )}
        </ul>

        {selected && result && (
          <div className="space-y-5 border border-ink-100 bg-white/60 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-display text-xl text-ink-800">
                  {STATUS_LABEL[selected.status] || selected.status}
                </p>
                <p className="text-sm text-ink-500">
                  {selected.period_start.slice(0, 10)} →{" "}
                  {selected.period_end.slice(0, 10)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {selected.status === "draft" && (
                  <>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => act("recompute")}
                      className="rounded-md px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-50"
                    >
                      重算
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => act("confirm")}
                      className="rounded-md bg-ink-800 px-3 py-1.5 text-sm text-white"
                    >
                      确认
                    </button>
                  </>
                )}
                {selected.status !== "settled" && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => act("settle")}
                    className="rounded-md border border-ink-300 px-3 py-1.5 text-sm text-ink-800"
                  >
                    标记结清
                  </button>
                )}
                <Link
                  to={`/settlements/${selected.id}/entries`}
                  className="rounded-md bg-ink-800 px-3 py-1.5 text-sm text-white hover:bg-ink-700"
                >
                  查看条目详情
                </Link>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-ink-400">已匹配支出</dt>
                <dd className="tabular-nums text-ink-800">
                  {formatMoney(result.matched_amount, result.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-ink-400">未匹配支出</dt>
                <dd className="tabular-nums text-ink-800">
                  {formatMoney(result.unmatched_amount, result.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-ink-400">
                  {result.aa_residual?.label || "家庭补贴"}
                </dt>
                <dd className="tabular-nums text-ink-800">
                  {formatMoney(result.residual_total, result.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-ink-400">条目</dt>
                <dd className="tabular-nums text-ink-800">
                  {result.entry_count_matched} 匹配 / {result.entry_count_unmatched}{" "}
                  跳过
                </dd>
              </div>
            </dl>

            <div>
              <h3 className="text-sm font-medium text-ink-700">应付关系</h3>
              {result.transfers.length === 0 ? (
                <p className="mt-2 text-sm text-ink-400">本期无需互转</p>
              ) : (
                <ul className="mt-2 space-y-2 text-sm text-ink-700">
                  {result.transfers.map((t, i) => (
                    <li key={i}>
                      {t.from_display_name} → {t.to_display_name}{" "}
                      <span className="tabular-nums font-medium">
                        {formatMoney(t.amount, result.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {result.balances.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-ink-700">净额</h3>
                <ul className="mt-2 space-y-1 text-sm text-ink-600">
                  {result.balances.map((b) => (
                    <li key={b.person_id}>
                      {b.display_name}{" "}
                      <span className="tabular-nums">
                        {Number(b.net) >= 0 ? "+" : ""}
                        {formatMoney(b.net, result.currency)}
                      </span>
                      <span className="text-ink-400">
                        {Number(b.net) > 0
                          ? "（应收）"
                          : Number(b.net) < 0
                            ? "（应付）"
                            : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
