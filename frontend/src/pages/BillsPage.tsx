import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { SourceLogo } from "../components/SourceLogo";
import {
  billLooksLikeIncome,
  formatMoneySigned,
  formatOccurredAt,
  moneyClass,
} from "../lib/format";
import type { Bill, CategoryItem, Vocabulary } from "../types";

const PAGE_SIZE = 40;

export function BillsPage() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [source, setSource] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    api<Vocabulary>("/api/v1/categories").then((v) =>
      setCategories(v.categories || []),
    );
  }, []);

  // Debounce search
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // Reset list when filters change
  useEffect(() => {
    setBills([]);
    setOffset(0);
    setHasMore(false);
  }, [source, categoryId, dateFrom, dateTo, search]);

  const loadPage = useCallback(
    async (pageOffset: number, append: boolean) => {
      const id = ++requestId.current;
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const params = new URLSearchParams();
        params.set("limit", String(PAGE_SIZE));
        params.set("offset", String(pageOffset));
        if (source) params.set("source_type", source);
        if (categoryId) params.set("category_id", categoryId);
        if (dateFrom) params.set("date_from", dateFrom);
        if (dateTo) params.set("date_to", dateTo);
        if (search) params.set("q", search);
        const data = await api<{
          bills: Bill[];
          has_more: boolean;
          offset: number;
        }>(`/api/v1/bills?${params}`);
        if (id !== requestId.current) return;
        setBills((prev) => (append ? [...prev, ...data.bills] : data.bills));
        setHasMore(Boolean(data.has_more));
        setOffset(pageOffset + data.bills.length);
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [source, categoryId, dateFrom, dateTo, search],
  );

  useEffect(() => {
    loadPage(0, false);
  }, [loadPage]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        if (!hasMore || loading || loadingMore) return;
        loadPage(offset, true);
      },
      { rootMargin: "240px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, loading, loadingMore, loadPage, offset]);

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
        {["", "manual", "coles", "openfeed", "commbank"].map((s) => (
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

      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="mb-1.5 block text-sm text-ink-600">从</span>
          <input
            type="date"
            className="field py-1.5"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm text-ink-600">到</span>
          <input
            type="date"
            className="field py-1.5"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
        <label className="block min-w-[12rem] flex-1">
          <span className="mb-1.5 block text-sm text-ink-600">搜索</span>
          <input
            className="field py-1.5"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="商户 / 备注 / 条目名"
          />
        </label>
        {(dateFrom || dateTo || searchInput) && (
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={() => {
              setDateFrom("");
              setDateTo("");
              setSearchInput("");
              setSearch("");
            }}
          >
            清除筛选
          </button>
        )}
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
                  {formatOccurredAt(b.occurred_at)}
                  {b.entries?.length ? ` · ${b.entries.length} 项` : ""}
                </p>
              </div>
              <p
                className={`shrink-0 font-medium tabular-nums ${moneyClass(
                  billLooksLikeIncome(b.entries),
                )}`}
              >
                {formatMoneySigned(b.total_amount, b.currency, {
                  income: billLooksLikeIncome(b.entries),
                })}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {loading && bills.length === 0 && (
        <p className="text-ink-400">加载中…</p>
      )}
      {!loading && bills.length === 0 && (
        <p className="text-ink-400">暂无流水</p>
      )}
      {loadingMore && <p className="text-sm text-ink-400">加载更多…</p>}
      <div ref={sentinelRef} className="h-8" aria-hidden />
      {!hasMore && bills.length > 0 && (
        <p className="text-center text-sm text-ink-300">已经到底了</p>
      )}
    </div>
  );
}
