import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { CategoryIcon } from "../components/CategoryIcon";
import { SourceLogo } from "../components/SourceLogo";
import {
  billLooksLikeIncome,
  formatMoney,
  formatMoneySigned,
  formatOccurredAt,
  moneyClass,
} from "../lib/format";
import type { Bill } from "../types";

type Granularity = "week" | "month" | "quarter" | "year";

type OverviewData = {
  granularity: Granularity;
  currency: string;
  period: {
    start: string;
    end: string;
    expense: string;
    income: string;
    balance: string;
  };
  series: {
    start: string;
    label: string;
    expense: string;
    income: string;
    balance: string;
  }[];
  by_category: {
    id: string;
    label: string;
    amount: string;
    share: number;
  }[];
  by_source: { id: string; amount: string; share: number }[];
};

const PERIODS: { id: Granularity; label: string }[] = [
  { id: "week", label: "本周" },
  { id: "month", label: "本月" },
  { id: "quarter", label: "本季" },
  { id: "year", label: "本年" },
];

export function OverviewPage() {
  const { user } = useAuth();
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [bills, setBills] = useState<Bill[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api<OverviewData>(
      `/api/v1/analytics/overview?granularity=${granularity}&series_count=6`,
    )
      .then(setOverview)
      .catch(() => setError("汇总加载失败"));
  }, [granularity]);

  useEffect(() => {
    api<{ bills: Bill[] }>("/api/v1/bills?limit=6").then((d) => setBills(d.bills));
  }, []);

  const currency = overview?.currency || "AUD";
  const expense = Number(overview?.period.expense || 0);
  const income = Number(overview?.period.income || 0);

  return (
    <div className="space-y-14">
      <section className="space-y-6">
        <div>
          <h1 className="font-display text-3xl text-ink-800 sm:text-4xl">
            {user?.person?.display_name}
          </h1>
          <p className="mt-2 text-ink-500">本周期支出一眼看清</p>
        </div>

        <div className="flex flex-wrap gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setGranularity(p.id)}
              className={`rounded-md px-3 py-1.5 text-sm transition ${
                granularity === p.id
                  ? "bg-ink-700 text-white"
                  : "bg-white text-ink-600 ring-1 ring-ink-100 hover:bg-ink-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="grid gap-8 sm:grid-cols-[1.2fr_auto] sm:items-end">
          <div>
            <p className="text-sm text-ink-400">支出</p>
            <p className="mt-1 font-display text-5xl tracking-tight text-ink-700 tabular-nums animate-[fadeIn_0.35s_ease]">
              {formatMoney(expense, currency)}
            </p>
            {income > 0 && (
              <p className="mt-3 text-sm text-ink-500">
                收入{" "}
                <span className="font-medium text-emerald-700">
                  +{formatMoney(income, currency)}
                </span>
                <span className="mx-2 text-ink-300">·</span>
                结余 {formatMoney(income - expense, currency)}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-3">
            <Link to="/bills/new" className="btn-primary">
              记一笔
            </Link>
            <Link to="/bills" className="btn-ghost">
              流水
            </Link>
          </div>
        </div>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </section>

      <section className="grid gap-12 lg:grid-cols-2">
        <div>
          <h2 className="font-display text-xl text-ink-800">支出趋势</h2>
          <p className="mt-1 text-sm text-ink-400">近几个{periodUnit(granularity)}</p>
          <div className="mt-6">
            {overview ? (
              <TrendChart series={overview.series} currency={currency} />
            ) : (
              <div className="h-40 animate-pulse rounded-md bg-ink-50" />
            )}
          </div>
        </div>

        <div>
          <h2 className="font-display text-xl text-ink-800">分类构成</h2>
          <p className="mt-1 text-sm text-ink-400">当前周期</p>
          <div className="mt-6">
            {overview ? (
              <CategoryBars items={overview.by_category} currency={currency} />
            ) : (
              <div className="h-40 animate-pulse rounded-md bg-ink-50" />
            )}
          </div>
        </div>
      </section>

      {overview && overview.by_source.length > 0 && (
        <section>
          <h2 className="font-display text-xl text-ink-800">按来源</h2>
          <ul className="mt-4 flex flex-wrap gap-6">
            {overview.by_source.map((s) => (
              <li key={s.id} className="flex items-center gap-3">
                <SourceLogo source={s.id} className="h-8 w-8" />
                <div>
                  <p className="text-sm text-ink-500">{s.id}</p>
                  <p className="font-medium tabular-nums text-ink-800">
                    {formatMoney(s.amount, currency)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-xl text-ink-800">最近流水</h2>
          <Link to="/bills" className="text-sm text-ink-600 hover:text-ink-800">
            查看全部
          </Link>
        </div>
        {bills.length === 0 ? (
          <p className="text-ink-400">还没有账单。</p>
        ) : (
          <ul className="divide-y divide-ink-100">
            {bills.map((b) => (
              <li key={b.id}>
                <Link
                  to={`/bills/${b.id}`}
                  className="flex items-center gap-4 py-4 transition-colors hover:bg-ink-50/60"
                >
                  <SourceLogo source={b.source_type} className="h-8 w-8" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-ink-800">
                      {b.merchant || "未命名商户"}
                    </p>
                    <p className="text-sm text-ink-400">
                      {formatOccurredAt(b.occurred_at)}
                    </p>
                  </div>
                  <p
                    className={`shrink-0 font-medium tabular-nums ${moneyClass(
                      billLooksLikeIncome(b.entries, b.total_amount),
                    )}`}
                  >
                    {formatMoneySigned(b.total_amount, b.currency || "AUD", {
                      income: billLooksLikeIncome(b.entries, b.total_amount),
                    })}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function periodUnit(g: Granularity): string {
  return { week: "周", month: "月", quarter: "季", year: "年" }[g];
}

function TrendChart({
  series,
  currency,
}: {
  series: OverviewData["series"];
  currency: string;
}) {
  const values = series.map((s) => Number(s.expense));
  const max = Math.max(...values, 1);
  const w = 360;
  const h = 160;
  const padX = 8;
  const padTop = 12;
  const padBottom = 28;
  const barGap = 10;
  const barW = (w - padX * 2 - barGap * (series.length - 1)) / series.length;
  const chartH = h - padTop - padBottom;

  if (values.every((v) => v === 0)) {
    return <p className="text-ink-400">这个周期还没有支出数据</p>;
  }

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full max-w-lg" role="img">
        {series.map((s, i) => {
          const v = Number(s.expense);
          const bh = (v / max) * chartH;
          const x = padX + i * (barW + barGap);
          const y = padTop + chartH - bh;
          const active = i === series.length - 1;
          return (
            <g key={s.start}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(bh, v > 0 ? 2 : 0)}
                rx={3}
                className={active ? "fill-ink-600" : "fill-ink-200"}
              >
                <title>
                  {s.label}: {formatMoney(v, currency)}
                </title>
              </rect>
              <text
                x={x + barW / 2}
                y={h - 8}
                textAnchor="middle"
                className="fill-ink-400"
                style={{ fontSize: 11 }}
              >
                {s.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CategoryBars({
  items,
  currency,
}: {
  items: OverviewData["by_category"];
  currency: string;
}) {
  if (items.length === 0) {
    return <p className="text-ink-400">暂无分类支出</p>;
  }
  const top = items.slice(0, 6);
  return (
    <ul className="space-y-3">
      {top.map((c) => (
        <li key={c.id} className="flex items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-ink-50 text-ink-700 ring-1 ring-ink-100">
            <CategoryIcon id={c.id} className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <p className="truncate text-sm text-ink-700">{c.label}</p>
              <p className="shrink-0 text-sm tabular-nums text-ink-800">
                {formatMoney(c.amount, currency)}
              </p>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-100">
              <div
                className="h-full rounded-full bg-ink-500 transition-[width] duration-500"
                style={{ width: `${Math.max(c.share * 100, 2)}%` }}
              />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
