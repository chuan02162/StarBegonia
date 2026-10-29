import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import { formatMoney } from "../lib/format";
import type { SettlementLine } from "../types";

type LinesPayload = {
  settlement_id: number;
  currency: string;
  period_start: string;
  period_end: string;
  status: string;
  matched: SettlementLine[];
  unmatched: SettlementLine[];
  matched_count: number;
  unmatched_count: number;
};

type BillGroup = {
  bill_id: number;
  title: string;
  source_type: string;
  merchant: string | null;
  occurred_at: string;
  payer_display_name: string;
  currency: string;
  entries: SettlementLine[];
  total: number;
  matched_count: number;
  unmatched_count: number;
};

const REASON_LABEL: Record<string, string> = {
  no_rule: "无匹配 AA 规则",
  empty_shares: "规则成员比例为空",
};

function billTitle(lines: SettlementLine[]): string {
  const merchant = lines.find((l) => l.merchant)?.merchant?.trim();
  if (merchant) return merchant;
  if (lines.length === 1) return lines[0].name;
  return `账单 #${lines[0].bill_id}`;
}

function groupByBill(lines: SettlementLine[]): BillGroup[] {
  const map = new Map<number, SettlementLine[]>();
  for (const ln of lines) {
    const list = map.get(ln.bill_id) || [];
    list.push(ln);
    map.set(ln.bill_id, list);
  }
  const groups: BillGroup[] = [];
  for (const [bill_id, entries] of map) {
    const first = entries[0];
    const total = entries.reduce((s, e) => s + Number(e.amount || 0), 0);
    groups.push({
      bill_id,
      title: billTitle(entries),
      source_type: first.source_type,
      merchant: first.merchant,
      occurred_at: first.occurred_at,
      payer_display_name: first.payer_display_name,
      currency: first.currency,
      entries,
      total,
      matched_count: entries.filter((e) => e.matched).length,
      unmatched_count: entries.filter((e) => !e.matched).length,
    });
  }
  groups.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at) || b.bill_id - a.bill_id);
  return groups;
}

function filterEntries(
  entries: SettlementLine[],
  tab: "all" | "matched" | "unmatched",
): SettlementLine[] {
  if (tab === "matched") return entries.filter((e) => e.matched);
  if (tab === "unmatched") return entries.filter((e) => !e.matched);
  return entries;
}

function EntryRow({ ln, currency }: { ln: SettlementLine; currency: string }) {
  return (
    <li className="space-y-1.5 border-t border-ink-50 py-3 pl-2 sm:pl-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink-800">{ln.name}</p>
          <p className="mt-0.5 text-sm text-ink-400">
            {ln.category_id || "未分类"}
            {ln.matched
              ? ` · 规则 ${ln.rule_name || `#${ln.rule_id}`}`
              : ""}
          </p>
        </div>
        <p className="shrink-0 tabular-nums font-medium text-ink-800">
          {formatMoney(ln.amount, currency)}
        </p>
      </div>
      {ln.matched ? (
        <div className="text-sm text-ink-500">
          {Number(ln.residual_amount) > 0 && (
            <p className="text-ink-400">
              家庭补贴 {formatMoney(ln.residual_amount, currency)}
            </p>
          )}
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            {Object.entries(ln.member_shares || {}).map(([pid, s]) => (
              <li key={pid}>
                {s.display_name} {s.percent}% →{" "}
                <span className="tabular-nums text-ink-700">
                  {formatMoney(s.amount, currency)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-amber-700">
          {REASON_LABEL[ln.reason || ""] || ln.reason || "未匹配"}
        </p>
      )}
    </li>
  );
}

export function SettlementLinesPage() {
  const { settlementId } = useParams();
  const [data, setData] = useState<LinesPayload | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"all" | "matched" | "unmatched">("all");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!settlementId) return;
    api<LinesPayload>(`/api/v1/settlements/${settlementId}/lines`)
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "加载失败"),
      );
  }, [settlementId]);

  const allLines = useMemo(() => {
    if (!data) return [];
    return [...data.matched, ...data.unmatched];
  }, [data]);

  const bills = useMemo(() => groupByBill(allLines), [allLines]);

  const visibleBills = useMemo(() => {
    return bills
      .map((b) => ({
        ...b,
        visibleEntries: filterEntries(b.entries, tab),
      }))
      .filter((b) => b.visibleEntries.length > 0);
  }, [bills, tab]);

  function toggle(billId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(billId)) next.delete(billId);
      else next.add(billId);
      return next;
    });
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/settlements" className="text-sm text-ink-500 hover:text-ink-700">
          ← 结算中心
        </Link>
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  if (!data) {
    return <p className="text-ink-500">加载中…</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <Link to="/settlements" className="text-sm text-ink-500 hover:text-ink-700">
          ← 结算中心
        </Link>
        <h1 className="mt-2 font-display text-3xl text-ink-800">结算账单</h1>
        <p className="mt-2 text-ink-500">
          {data.period_start.slice(0, 10)} → {data.period_end.slice(0, 10)} ·{" "}
          {bills.length} 笔账单 · 已匹配 {data.matched_count} 条 · 未匹配{" "}
          {data.unmatched_count} 条
        </p>
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        {(
          [
            ["all", "全部"],
            ["matched", "已匹配"],
            ["unmatched", "未匹配"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded-md px-3 py-1.5 ${
              tab === id
                ? "bg-ink-800 text-white"
                : "text-ink-600 hover:bg-ink-50"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {visibleBills.length === 0 ? (
        <p className="text-ink-400">当前筛选下没有账单。</p>
      ) : (
        <ul className="divide-y divide-ink-100 border-t border-ink-100">
          {visibleBills.map((bill) => {
            const open = expanded.has(bill.bill_id);
            return (
              <li key={bill.bill_id} className="py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => toggle(bill.bill_id)}
                        className="rounded px-1.5 py-0.5 text-sm text-ink-500 hover:bg-ink-50"
                        aria-expanded={open}
                      >
                        {open ? "▾" : "▸"}
                      </button>
                      <Link
                        to={`/bills/${bill.bill_id}`}
                        className="font-medium text-ink-800 hover:underline"
                      >
                        {bill.title}
                      </Link>
                    </div>
                    <p className="mt-1 ml-7 flex flex-wrap items-center gap-2 text-sm text-ink-500">
                      <SourceLogo source={bill.source_type} className="h-5 w-5" />
                      {SOURCE_LABELS[bill.source_type] || bill.source_type}
                      <span>·</span>
                      <span>{bill.occurred_at.slice(0, 10)}</span>
                      <span>·</span>
                      <span>付款人 {bill.payer_display_name}</span>
                    </p>
                    <p className="ml-7 text-sm text-ink-400">
                      本筛选项下 {bill.visibleEntries.length} 条
                      {tab === "all" && (
                        <>
                          {" "}
                          （匹配 {bill.matched_count} / 未匹配 {bill.unmatched_count}）
                        </>
                      )}
                    </p>
                  </div>
                  <p className="shrink-0 tabular-nums font-medium text-ink-800">
                    {formatMoney(
                      bill.visibleEntries
                        .reduce((s, e) => s + Number(e.amount || 0), 0)
                        .toFixed(2),
                      data.currency,
                    )}
                  </p>
                </div>

                {open && (
                  <ul className="mt-2 ml-5 border-l border-ink-100 sm:ml-7">
                    {bill.visibleEntries.map((ln) => (
                      <EntryRow
                        key={ln.entry_id}
                        ln={ln}
                        currency={data.currency}
                      />
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
