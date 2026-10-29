import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { SOURCE_LABELS, SourceLogo } from "../components/SourceLogo";
import type {
  AaResidual,
  AaRule,
  CategoryItem,
  Household,
  HouseholdMember,
  Vocabulary,
} from "../types";

type SourceInfo = { source_type: string };

function residualOf(shares: Record<string, string>): number {
  const total = Object.values(shares).reduce((s, v) => s + (Number(v) || 0), 0);
  return Math.max(0, Math.round((100 - total) * 1000) / 1000);
}

export function AaRulesPage() {
  const [rules, setRules] = useState<AaRule[]>([]);
  const [residualMeta, setResidualMeta] = useState<AaResidual | null>(null);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [household, setHousehold] = useState<Household | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<AaRule | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [shares, setShares] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [hhRes, rulesRes, srcRes, vocab] = await Promise.all([
      api<{ household: Household | null }>("/api/v1/households/me"),
      api<{ rules: AaRule[]; aa_residual: AaResidual }>("/api/v1/aa-rules"),
      api<{ sources: SourceInfo[] }>("/api/v1/sources"),
      api<Vocabulary>("/api/v1/categories"),
    ]);
    setHousehold(hhRes.household);
    setMembers(hhRes.household?.members || []);
    setRules(rulesRes.rules);
    setResidualMeta(rulesRes.aa_residual);
    setSources(srcRes.sources.map((s) => s.source_type));
    setCategories(vocab.categories || []);
  }, []);

  useEffect(() => {
    load().catch((err) =>
      setError(err instanceof ApiError ? err.message : "加载失败"),
    );
  }, [load]);

  function openCreate() {
    setCreating(true);
    setEditing(null);
    setName("");
    setSelectedSources([]);
    setSelectedCategories([]);
    setEnabled(true);
    const init: Record<string, string> = {};
    for (const m of members) init[String(m.person_id)] = "";
    setShares(init);
    setError("");
  }

  function openEdit(rule: AaRule) {
    setCreating(false);
    setEditing(rule);
    setName(rule.name || "");
    setSelectedSources([...rule.source_types]);
    setSelectedCategories([...(rule.category_ids || [])]);
    setEnabled(rule.enabled);
    const init: Record<string, string> = {};
    for (const m of members) {
      init[String(m.person_id)] = rule.shares[String(m.person_id)] || "";
    }
    setShares(init);
    setError("");
  }

  function closeForm() {
    setCreating(false);
    setEditing(null);
  }

  function toggleSource(st: string) {
    setSelectedSources((prev) =>
      prev.includes(st) ? prev.filter((x) => x !== st) : [...prev, st].sort(),
    );
  }

  function toggleCategory(id: string) {
    setSelectedCategories((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].sort(),
    );
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      name: name.trim() || undefined,
      source_types: selectedSources,
      category_ids: selectedCategories,
      enabled,
      shares: Object.fromEntries(
        Object.entries(shares).filter(([, v]) => v !== "" && Number(v) !== 0),
      ),
    };
    try {
      if (editing) {
        await api(`/api/v1/aa-rules/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await api("/api/v1/aa-rules", {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      closeForm();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function remove(rule: AaRule) {
    if (!confirm(`删除规则「${rule.name || rule.source_types.join("+")}」？`)) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/aa-rules/${rule.id}`, { method: "DELETE" });
      if (editing?.id === rule.id) closeForm();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  const catLabel = (id: string) =>
    categories.find((c) => c.id === id)?.label || id;

  const formResidual = residualOf(shares);
  const residualLabel = residualMeta?.label || "家庭补贴";
  const showForm = creating || editing;

  if (!household) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-ink-400">
          <Link to="/account" className="hover:text-ink-700">
            ← 账户 / 家庭
          </Link>
        </p>
        <h1 className="font-display text-3xl text-ink-800">AA 规则</h1>
        <p className="text-ink-500">需要先加入家庭才能配置 AA。</p>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-ink-400">
            <Link to="/account" className="hover:text-ink-700">
              ← 账户 / 家庭
            </Link>
          </p>
          <h1 className="mt-2 font-display text-3xl text-ink-800">AA 规则</h1>
          <p className="mt-2 max-w-xl text-ink-500">
            按数据源组合分摊；可选限定分类（不选=该源下全部分类）。未满 100% 归入
            {residualLabel}。去{" "}
            <Link to="/settlements" className="text-ink-700 underline">
              结算中心
            </Link>{" "}
            生成应付关系。
          </p>
        </div>
        {!showForm && (
          <button
            type="button"
            onClick={openCreate}
            className="rounded-md bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-700"
          >
            新建规则
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      {showForm && (
        <form
          onSubmit={save}
          className="space-y-5 border border-ink-100 bg-white/60 p-5"
        >
          <h2 className="font-display text-xl text-ink-800">
            {editing ? "编辑规则" : "新建规则"}
          </h2>

          <label className="block space-y-1 text-sm">
            <span className="text-ink-600">名称（可选）</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full max-w-md border border-ink-200 bg-white px-3 py-2"
              placeholder="默认用数据源 / 分类命名"
            />
          </label>

          <fieldset className="space-y-2">
            <legend className="text-sm text-ink-600">数据源（可多选）</legend>
            <div className="flex flex-wrap gap-3">
              {sources.map((st) => {
                const checked = selectedSources.includes(st);
                return (
                  <label
                    key={st}
                    className={`flex cursor-pointer items-center gap-2 border px-3 py-2 text-sm ${
                      checked
                        ? "border-ink-700 bg-ink-50 text-ink-800"
                        : "border-ink-200 text-ink-600"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggleSource(st)}
                    />
                    <SourceLogo source={st} className="h-6 w-6" />
                    {SOURCE_LABELS[st] || st}
                  </label>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm text-ink-600">
              分类（可选；不选表示上述数据源的全部分类）
            </legend>
            <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto">
              {categories.map((c) => {
                const checked = selectedCategories.includes(c.id);
                return (
                  <label
                    key={c.id}
                    className={`cursor-pointer border px-2.5 py-1 text-xs ${
                      checked
                        ? "border-ink-700 bg-ink-50 text-ink-800"
                        : "border-ink-200 text-ink-600"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggleCategory(c.id)}
                    />
                    {c.label}
                  </label>
                );
              })}
            </div>
          </fieldset>

          <label className="flex items-center gap-2 text-sm text-ink-700">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            启用
          </label>

          <fieldset className="space-y-3">
            <legend className="text-sm text-ink-600">成员比例 %</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {members.map((m) => (
                <label key={m.person_id} className="flex items-center gap-3 text-sm">
                  <span className="w-28 truncate text-ink-700">
                    {m.display_name || m.email || `#${m.person_id}`}
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.1"
                    value={shares[String(m.person_id)] ?? ""}
                    onChange={(e) =>
                      setShares((prev) => ({
                        ...prev,
                        [String(m.person_id)]: e.target.value,
                      }))
                    }
                    className="w-24 border border-ink-200 px-2 py-1.5 tabular-nums"
                    placeholder="0"
                  />
                  <span className="text-ink-400">%</span>
                </label>
              ))}
            </div>
            <p className="text-sm text-ink-500">
              剩余{" "}
              <span className="font-medium tabular-nums text-ink-700">
                {formResidual}%
              </span>{" "}
              → {residualLabel}
            </p>
          </fieldset>

          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={busy || selectedSources.length === 0}
              className="rounded-md bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-700 disabled:opacity-50"
            >
              {busy ? "保存中…" : "保存"}
            </button>
            <button
              type="button"
              onClick={closeForm}
              className="rounded-md px-4 py-2 text-sm text-ink-600 hover:bg-ink-50"
            >
              取消
            </button>
          </div>
        </form>
      )}

      <ul className="divide-y divide-ink-100 border-t border-ink-100">
        {rules.map((rule) => (
          <li
            key={rule.id}
            className="flex flex-wrap items-start justify-between gap-4 py-4"
          >
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-ink-800">
                  {rule.name || rule.source_types.join(" + ")}
                </p>
                {!rule.enabled && (
                  <span className="text-xs text-amber-700">已停用</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {rule.source_types.map((st) => (
                  <span
                    key={st}
                    className="inline-flex items-center gap-1.5 text-sm text-ink-600"
                  >
                    <SourceLogo source={st} className="h-5 w-5" />
                    {SOURCE_LABELS[st] || st}
                  </span>
                ))}
              </div>
              <p className="text-sm text-ink-500">
                分类：
                {(rule.category_ids || []).length === 0
                  ? "全部"
                  : (rule.category_ids || []).map(catLabel).join("、")}
              </p>
              <ul className="text-sm text-ink-600">
                {members.map((m) => {
                  const pct = rule.shares[String(m.person_id)];
                  if (!pct) return null;
                  return (
                    <li key={m.person_id}>
                      {m.display_name || m.email || `#${m.person_id}`} · {pct}%
                    </li>
                  );
                })}
                {Number(rule.residual_percent) > 0 && (
                  <li className="text-ink-500">
                    {rule.aa_residual?.label || residualLabel} ·{" "}
                    {rule.residual_percent}%
                  </li>
                )}
              </ul>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => openEdit(rule)}
                className="rounded-md px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-50"
              >
                编辑
              </button>
              <button
                type="button"
                onClick={() => remove(rule)}
                disabled={busy}
                className="rounded-md px-3 py-1.5 text-sm text-red-700 hover:bg-red-50"
              >
                删除
              </button>
            </div>
          </li>
        ))}
      </ul>

      {rules.length === 0 && !showForm && (
        <p className="text-ink-400">
          还没有 AA 规则。例如：Coles 食材 各 50%，或 CommBank 房租指定分类比例。
        </p>
      )}
    </div>
  );
}
