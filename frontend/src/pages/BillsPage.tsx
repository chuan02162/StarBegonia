import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import {
  billLooksLikeIncome,
  formatMoneySigned,
  formatOccurredAt,
  moneyClass,
} from "../lib/format";
import type {
  AccountOption,
  Bill,
  CategoryItem,
  HouseholdMember,
  Vocabulary,
} from "../types";

const PAGE_SIZE = 40;
const TAG_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#db2777",
  "#ea580c",
  "#16a34a",
  "#0891b2",
  "#ca8a04",
  "#dc2626",
];

export function BillsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [bills, setBills] = useState<Bill[]>([]);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [source, setSource] = useState(searchParams.get("source_type") || "");
  const [categoryId, setCategoryId] = useState(
    searchParams.get("category_id") || "",
  );
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [accountFilter, setAccountFilter] = useState(() => {
    const pid = searchParams.get("account_person_id");
    const acct = searchParams.get("account");
    return pid ? `${pid}|${acct || ""}` : "";
  });
  const [dateFrom, setDateFrom] = useState(searchParams.get("date_from") || "");
  const [dateTo, setDateTo] = useState(searchParams.get("date_to") || "");
  const [searchInput, setSearchInput] = useState(searchParams.get("q") || "");
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);

  // Keep filters in the URL so returning from a bill detail restores them.
  useEffect(() => {
    const params = new URLSearchParams();
    if (source) params.set("source_type", source);
    if (categoryId) params.set("category_id", categoryId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (search) params.set("q", search);
    if (accountFilter) {
      const [pid, ...rest] = accountFilter.split("|");
      if (pid) params.set("account_person_id", pid);
      if (rest.length) params.set("account", rest.join("|"));
    }
    setSearchParams(params, { replace: true });
  }, [
    source,
    categoryId,
    dateFrom,
    dateTo,
    search,
    accountFilter,
    setSearchParams,
  ]);

  useEffect(() => {
    api<Vocabulary>("/api/v1/categories").then((v) =>
      setCategories(v.categories || []),
    );
    api<{ household: { members?: HouseholdMember[] } | null }>(
      "/api/v1/households/me",
    ).then((d) => setMembers(d.household?.members || []));
  }, []);

  const personMap = useMemo(() => {
    const sorted = [...members].sort((a, b) => a.person_id - b.person_id);
    const map: Record<number, { name: string; color: string }> = {};
    sorted.forEach((member, index) => {
      map[member.person_id] = {
        name: member.display_name || `用户${index + 1}`,
        color: TAG_COLORS[index % TAG_COLORS.length],
      };
    });
    return map;
  }, [members]);

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
  }, [source, categoryId, dateFrom, dateTo, search, accountFilter]);

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
        if (accountFilter) {
          const [pid, ...rest] = accountFilter.split("|");
          if (pid) params.set("account_person_id", pid);
          if (rest.length) params.set("account", rest.join("|"));
        }
        const data = await api<{
          bills: Bill[];
          has_more: boolean;
          offset: number;
          accounts: AccountOption[];
        }>(`/api/v1/bills?${params}`);
        if (id !== requestId.current) return;
        setAccounts(data.accounts || []);
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
    [source, categoryId, dateFrom, dateTo, search, accountFilter],
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
          <p className="mt-2 text-ink-500">
            这里只显示家庭对外的收支；去重从记录和内部转账分别在专页查看。
          </p>
        </div>
        <Link to="/bills/new" className="btn-primary">
          手动记账
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        {["", "manual", "coles", "commbank", "wws"].map((s) => (
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
            {s ? SOURCE_LABELS[s] || s : "全部"}
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
          <span className="mb-1.5 block text-sm text-ink-600">账户来源</span>
          <select
            className="field py-1.5"
            value={accountFilter}
            onChange={(e) => setAccountFilter(e.target.value)}
          >
            <option value="">全部账户</option>
            {accounts.map((a) => {
              const person = a.account_person_id
                ? personMap[a.account_person_id]
                : undefined;
              const value = `${a.account_person_id ?? ""}|${a.account}`;
              return (
                <option key={value} value={value}>
                  {person?.name || "未知用户"} · {a.account}
                </option>
              );
            })}
          </select>
        </label>
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
        {bills.map((b) => {
          const person = personMap[b.account_person_id ?? b.person_id];
          const account = b.account?.trim();
          const tagLabel = person
            ? account
              ? `${person.name} · ${account}`
              : person.name
            : null;
          return (
            <li key={b.id}>
              <Link
                to={`/bills/${b.id}`}
                className="flex items-center gap-4 py-5 transition-colors hover:bg-ink-50/60"
              >
                <SourceLogo source={b.source_type} className="h-9 w-9" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {tagLabel && (
                      <span
                        className="max-w-[16rem] shrink-0 truncate rounded px-1.5 py-0.5 text-xs font-medium text-white"
                        style={{ backgroundColor: person?.color }}
                      >
                        {tagLabel}
                      </span>
                    )}
                    <p className="truncate text-lg text-ink-800">
                      {b.merchant || "未命名商户"}
                    </p>
                  </div>
                  <p className="text-sm text-ink-400">
                    {formatOccurredAt(b.occurred_at)}
                    {b.entries?.length ? ` · ${b.entries.length} 项` : ""}
                  </p>
                </div>
                <p
                  className={`shrink-0 font-medium tabular-nums ${moneyClass(
                    billLooksLikeIncome(b.entries, b.total_amount),
                  )}`}
                >
                  {formatMoneySigned(b.total_amount, b.currency, {
                    income: billLooksLikeIncome(b.entries, b.total_amount),
                  })}
                </p>
              </Link>
            </li>
          );
        })}
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
