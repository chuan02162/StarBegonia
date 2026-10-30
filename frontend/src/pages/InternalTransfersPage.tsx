import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import { formatMoney, formatOccurredAt } from "../lib/format";
import type { BillSummary, InternalTransferLink } from "../types";

function BillCard({
  bill,
  role,
}: {
  bill: BillSummary | null;
  role: string;
}) {
  if (!bill) return null;
  return (
    <div className="min-w-0 flex-1 space-y-1">
      <p className="text-xs uppercase tracking-wide text-ink-400">{role}</p>
      <Link
        to={`/bills/${bill.id}`}
        className="font-medium text-ink-800 hover:underline"
      >
        {bill.merchant || `账单 #${bill.id}`}
      </Link>
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

export function InternalTransfersPage() {
  const [links, setLinks] = useState<InternalTransferLink[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const data = await api<{ links: InternalTransferLink[] }>(
      "/api/v1/transfers/links",
    );
    setLinks(data.links);
  }, []);

  useEffect(() => {
    setError("");
    load().catch((err) =>
      setError(err instanceof ApiError ? err.message : "加载失败"),
    );
  }, [load]);

  async function scan() {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const res = await api<{ created: number; considered_pairs: number }>(
        "/api/v1/transfers/scan",
        { method: "POST", body: "{}" },
      );
      setMsg(
        `扫描完成：新建 ${res.created} 对（比较 ${res.considered_pairs} 对）`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "扫描失败");
    } finally {
      setBusy(false);
    }
  }

  async function unlink(linkId: number) {
    if (!window.confirm("取消这对内部转账？双方会恢复原分类并重新计入概览与结算。"))
      return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/transfers/links/${linkId}/unlink`, {
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
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-ink-400">
            <Link to="/account" className="hover:text-ink-700">
              账户
            </Link>
            <span className="mx-1.5">/</span>
            内部账单
          </p>
          <h1 className="mt-2 font-display text-3xl text-ink-800">内部转账</h1>
          <p className="mt-2 max-w-xl text-ink-500">
            按银行 reference、金额与时间自动配对家庭成员之间的 PayID / 转账，标为「转账不计收支」。
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={scan}
          className="rounded-md bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-700 disabled:opacity-50"
        >
          {busy ? "处理中…" : "扫描内部转账"}
        </button>
      </div>

      {msg && <p className="text-sm text-ink-600">{msg}</p>}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <ul className="divide-y divide-ink-100 border-t border-ink-100">
        {links.map((link) => (
          <li key={link.id} className="space-y-4 py-5">
            <div className="flex flex-wrap gap-6">
              <BillCard bill={link.outgoing_bill} role="转出" />
              <BillCard bill={link.incoming_bill} role="转入" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <p className="text-ink-500">
                ref{" "}
                <span className="font-mono tabular-nums text-ink-700">
                  {link.reference}
                </span>
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => unlink(link.id)}
                className="rounded-md px-3 py-1.5 text-red-700 hover:bg-red-50 disabled:opacity-50"
              >
                取消配对
              </button>
            </div>
          </li>
        ))}
      </ul>

      {links.length === 0 && (
        <p className="text-ink-400">
          还没有内部转账配对。同步各成员 CommBank 后点「扫描内部转账」。
        </p>
      )}
    </div>
  );
}
