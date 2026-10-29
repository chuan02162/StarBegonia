import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { SourceLogo } from "../components/SourceLogo";
import { formatMoney } from "../lib/format";
import type { Bill, CategoryItem, Vocabulary } from "../types";

export function BillsPage() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [source, setSource] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState<CategoryItem[]>([]);

  useEffect(() => {
    api<Vocabulary>("/api/v1/categories").then((v) => setCategories(v.categories || []));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (source) params.set("source_type", source);
    if (categoryId) params.set("category_id", categoryId);
    const q = params.toString() ? `?${params}` : "";
    api<{ bills: Bill[] }>(`/api/v1/bills${q}`).then((d) => setBills(d.bills));
  }, [source, categoryId]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-ink-800">流水</h1>
          <p className="mt-2 text-ink-500">点击账单查看明细</p>
        </div>
        <Link to="/bills/new" className="btn-primary">
          手动记账
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        {["", "manual", "coles", "commbank"].map((s) => (
          <button
            key={s || "all"}
            type="button"
            onClick={() => setSource(s)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              source === s
                ? "bg-ink-700 text-white"
                : "bg-white text-ink-600 ring-1 ring-ink-100"
            }`}
          >
            {s || "全部"}
          </button>
        ))}
        <select
          className="field max-w-[12rem] py-1.5"
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
        >
          <option value="">全部分类</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <ul className="divide-y divide-ink-100">
        {bills.map((b) => (
          <li key={b.id}>
            <Link
              to={`/bills/${b.id}`}
              className="flex items-center gap-4 py-5 transition-colors hover:bg-ink-50/60"
            >
              <SourceLogo source={b.source_type} className="h-9 w-9" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-lg text-ink-800">
                  {b.merchant || "未命名商户"}
                </p>
                <p className="text-sm text-ink-400">
                  {new Date(b.occurred_at).toLocaleString()}
                  {b.entries?.length ? ` · ${b.entries.length} 项` : ""}
                </p>
              </div>
              <p className="shrink-0 font-medium tabular-nums text-ink-700">
                {formatMoney(b.total_amount, b.currency)}
              </p>
            </Link>
          </li>
        ))}
      </ul>
      {bills.length === 0 && <p className="text-ink-400">暂无流水</p>}
    </div>
  );
}
