import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import { formatMoney, formatOccurredAt } from "../lib/format";
import type { BillSummary, DedupLink } from "../types";

function BillCard({
  bill,
  role,
  clickable = true,
}: {
  bill: BillSummary | null;
  role: string;
  clickable?: boolean;
}) {
  if (!bill) return null;
  return (
    <div className="min-w-0 flex-1 space-y-1">
      <p className="text-xs uppercase tracking-wide text-ink-400">{role}</p>
      {clickable ? (
        <Link
          to={`/bills/${bill.id}`}
          className="font-medium text-ink-800 hover:underline"
        >
          {bill.merchant || `账单 #${bill.id}`}
        </Link>
      ) : (
        <p className="font-medium text-ink-800">
          {bill.merchant || `账单 #${bill.id}`}
        </p>
      )}
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink-500">
        <SourceLogo source={bill.source_type} className="h-5 w-5" />
        {SOURCE_LABELS[bill.source_type] || bill.source_type}
        <span>·</span>
        <span>{formatOccurredAt(bill.occurred_at)}</span>
      </p>
      <p className="tabular-nums text-ink-800">
        {formatMoney(bill.total_amount, bill.currency)}
      </p>
    </div>
  );
}

export function DedupPage() {
  const [links, setLinks] = useState<DedupLink[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await api<{ links: DedupLink[] }>("/api/v1/dedup/links");
    setLinks(data.links);
  }, []);

  useEffect(() => {
    setError("");
    load().catch((err) =>
      setError(err instanceof ApiError ? err.message : "加载失败"),
    );
  }, [load]);

  async function unlink(linkId: number) {
    if (!window.confirm("取消这对去重？CommBank 记录会重新出现在流水、概览与结算。")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/dedup/links/${linkId}/unlink`, {
        method: "POST",
        body: "{}",
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm text-ink-400">
          <Link to="/account" className="hover:text-ink-700">
            账户
          </Link>
          <span className="mx-1.5">/</span>
          去重账单
        </p>
        <h1 className="mt-2 font-display text-3xl text-ink-800">已去重账单对</h1>
        <p className="mt-2 max-w-xl text-ink-500">
          同步后按金额与时间自动配对（Coles / 手动 ↔ CommBank）。从记录只在此处显示，
          不会出现在流水、概览或 AA 结算中。
        </p>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <ul className="divide-y divide-ink-100 border-t border-ink-100">
        {links.map((link) => (
          <li key={link.id} className="space-y-4 py-5">
            <div className="flex flex-wrap gap-6">
              <BillCard bill={link.primary_bill} role="主记录" />
              <BillCard
                bill={link.secondary_bill}
                role="从记录"
                clickable={false}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-ink-500">
                {link.reason || "金额 + 时间自动匹配"}
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => unlink(link.id)}
                className="rounded-md px-3 py-1.5 text-red-700 hover:bg-red-50 disabled:opacity-50"
              >
                取消去重
              </button>
            </div>
          </li>
        ))}
      </ul>

      {links.length === 0 && (
        <p className="text-ink-400">
          还没有自动去重结果。同步 Coles 与 CommBank 后会按金额与时间配对。
        </p>
      )}
    </div>
  );
}
