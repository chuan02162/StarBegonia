import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { CategoryChip, CategoryPicker } from "../components/CategoryPicker";
import { JobProgressBar } from "../components/JobProgressBar";
import { SourceLogo } from "../components/SourceLogo";
import { formatMoney, formatOccurredAt } from "../lib/format";
import { pollJob, type JobProgress } from "../lib/jobs";
import type {
  AccountOption,
  CategoryItem,
  HouseholdMember,
  PendingEntry,
  Vocabulary,
} from "../types";

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

export function CategoriesPage() {
  const [pending, setPending] = useState<PendingEntry[]>([]);
  const [vocab, setVocab] = useState<Vocabulary | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [pickerEntry, setPickerEntry] = useState<PendingEntry | null>(null);
  const [batchMsg, setBatchMsg] = useState("");
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState<JobProgress | null>(null);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [accountFilter, setAccountFilter] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (accountFilter) {
      const [pid, ...rest] = accountFilter.split("|");
      const acct = rest.join("|");
      if (pid) params.set("account_person_id", pid);
      if (acct) params.set("account", acct);
    }
    return Promise.all([
      api<{ entries: PendingEntry[]; accounts: AccountOption[] }>(
        `/api/v1/categories/pending${params.toString() ? `?${params}` : ""}`,
      ),
      api<Vocabulary>("/api/v1/categories"),
      api<{ household: { members?: HouseholdMember[] } | null }>(
        "/api/v1/households/me",
      ),
    ]).then(([p, v, h]) => {
      setPending(p.entries);
      setVocab(v);
      setAccounts(p.accounts || []);
      setMembers(h.household?.members || []);
    });
  }, [accountFilter]);

  useEffect(() => {
    load().catch(() => setError("加载失败"));
  }, [load]);

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

  async function selectCategory(categoryId: string | null) {
    if (!pickerEntry) return;
    setBusyId(pickerEntry.id);
    setError("");
    try {
      await api(`/api/v1/entries/${pickerEntry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          category_id: categoryId,
          confirm: Boolean(categoryId),
        }),
      });
      setPickerEntry(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "确认失败");
    } finally {
      setBusyId(null);
    }
  }

  async function confirmSuggested(entry: PendingEntry) {
    if (!entry.category_id) {
      setError("这条还没有建议分类，请先点分类选择");
      return;
    }
    setBusyId(entry.id);
    setError("");
    try {
      await api(`/api/v1/entries/${entry.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          category_id: entry.category_id,
          confirm: true,
        }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "确认失败");
    } finally {
      setBusyId(null);
    }
  }

  async function runBatch() {
    setBatchMsg("排队分类中…");
    setError("");
    setBatchRunning(true);
    setBatchProgress({ percent: 0, message: "排队分类中…" });
    try {
      const res = await api<{ job_id?: string; classified?: number; status?: string }>(
        "/api/v1/categories/classify",
        {
          method: "POST",
          body: JSON.stringify({
            entry_ids: pending.map((e) => e.id),
            only_unclassified: false,
            limit: Math.max(pending.length, 40),
            async: true,
          }),
        },
      );
      if (res.job_id) {
        const job = await pollJob(res.job_id, {
          endpoint: "categories",
          onProgress: (p) => {
            setBatchProgress(p);
            setBatchMsg(p.message || "分类中…");
          },
        });
        if (job.error || job.status === "failed") {
          setError(job.error || "批量分类失败");
          setBatchMsg("");
        } else {
          const classified = Number(job.result?.classified ?? 0);
          setBatchMsg(`已分类 ${classified} 条`);
          setBatchProgress({
            percent: 100,
            message: "分类完成",
            current: classified,
            total: Number(job.result?.requested ?? classified) || 1,
          });
          await load();
        }
      } else {
        setBatchMsg(`已分类 ${res.classified ?? 0} 条`);
        setBatchProgress(null);
        await load();
      }
    } catch (err) {
      setBatchMsg("");
      setBatchProgress(null);
      setError(err instanceof ApiError ? err.message : "批量分类失败");
    } finally {
      setBatchRunning(false);
    }
  }

  const catLabel = (id: string | null | undefined) =>
    vocab?.categories.find((c) => c.id === id)?.label || id || "未分类";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-ink-800">分类待确认</h1>
          <p className="mt-2 text-ink-500">
            Jev 低置信度建议；点分类可改选，右侧绿色对号确认当前建议
          </p>
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
                const name = person?.name || "未知用户";
                const value = `${a.account_person_id ?? ""}|${a.account}`;
                return (
                  <option key={value} value={value}>
                    {name} · {a.account}
                  </option>
                );
              })}
            </select>
          </label>
          <button
            type="button"
            className="btn-ghost"
            onClick={runBatch}
            disabled={batchRunning || pending.length === 0}
          >
            {batchRunning ? "分类中…" : "对未分类条目跑 Jev"}
          </button>
        </div>
      </div>

      {batchMsg && <p className="text-sm text-ink-500">{batchMsg}</p>}
      {(batchRunning || batchProgress) && (
        <JobProgressBar progress={batchProgress} active={batchRunning} />
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <ul className="divide-y divide-ink-100">
        {pending.map((e) => (
          <PendingRow
            key={e.id}
            entry={e}
            label={catLabel(e.category_id)}
            busy={busyId === e.id}
            personMap={personMap}
            onOpenPicker={() => setPickerEntry(e)}
            onConfirm={() => confirmSuggested(e)}
          />
        ))}
      </ul>
      {pending.length === 0 && !error && (
        <p className="text-ink-400">没有待确认的分类</p>
      )}

      <CategoryPicker
        open={Boolean(pickerEntry)}
        onClose={() => setPickerEntry(null)}
        categories={(vocab?.categories || []) as CategoryItem[]}
        value={pickerEntry?.category_id}
        onSelect={selectCategory}
        busy={busyId === pickerEntry?.id}
      />
    </div>
  );
}

function PendingRow({
  entry,
  label,
  busy,
  personMap,
  onOpenPicker,
  onConfirm,
}: {
  entry: PendingEntry;
  label: string;
  busy: boolean;
  personMap: Record<number, { name: string; color: string }>;
  onOpenPicker: () => void;
  onConfirm: () => void;
}) {
  const conf = entry.category_confidence
    ? `${(Number(entry.category_confidence) * 100).toFixed(0)}%`
    : "—";
  const canConfirm = Boolean(entry.category_id) && entry.category_id !== "review";

  return (
    <li className="py-6">
      <div className="flex flex-wrap items-start gap-4">
        {entry.bill && (
          <SourceLogo source={entry.bill.source_type} className="mt-1 h-8 w-8" />
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="font-medium text-ink-800">{entry.name}</p>
            <p className="mt-1 text-sm text-ink-400">
              {entry.bill ? (
                <>
                  {(() => {
                    const pid = entry.bill.account_person_id ?? entry.bill.person_id;
                    const person = pid ? personMap[pid] : undefined;
                    const account = entry.bill.account?.trim();
                    const tagLabel = person
                      ? account
                        ? `${person.name} · ${account}`
                        : person.name
                      : null;
                    return tagLabel ? (
                      <span
                        className="mr-2 inline-flex max-w-[16rem] truncate rounded px-1.5 py-0.5 align-middle text-xs font-medium text-white"
                        style={{ backgroundColor: person?.color }}
                      >
                        {tagLabel}
                      </span>
                    ) : null;
                  })()}
                  <Link
                    to={`/bills/${entry.bill.id}`}
                    className="text-ink-600 hover:text-ink-800"
                  >
                    {entry.bill.display_name || entry.bill.merchant || "账单"}
                  </Link>
                  {" · "}
                  {formatOccurredAt(entry.bill.occurred_at)}
                  {" · "}
                  {formatMoney(entry.amount, entry.bill.currency)}
                </>
              ) : (
                formatMoney(entry.amount, entry.currency)
              )}
            </p>
            <p className="mt-1 text-sm text-ink-400">置信度 {conf}</p>
          </div>
          <CategoryChip
            categoryId={entry.category_id}
            label={label}
            pending
            onClick={onOpenPicker}
          />
        </div>
        <button
          type="button"
          title={canConfirm ? "确认当前分类" : "先选择分类"}
          aria-label="确认当前分类"
          disabled={busy || !canConfirm}
          onClick={onConfirm}
          className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-emerald-600 ring-1 ring-emerald-200 transition hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.25"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </button>
      </div>
    </li>
  );
}
