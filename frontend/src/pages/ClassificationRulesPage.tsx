import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { CategoryItem, Vocabulary } from "../types";

type Rule = {
  id: number;
  category_id: string;
  keywords: string[];
  match_field: string;
  enabled: boolean;
};

export function ClassificationRules() {
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [keywordsText, setKeywordsText] = useState("");
  const [matchField, setMatchField] = useState("name");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [applying, setApplying] = useState(false);
  const [previewCount, setPreviewCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    const [vocab, rulesData] = await Promise.all([
      api<Vocabulary>("/api/v1/categories"),
      api<{ rules: Rule[] }>("/api/v1/categories/rules"),
    ]);
    setCategories(vocab.categories || []);
    setRules(rulesData.rules || []);
  }, []);

  useEffect(() => {
    load().catch(() => setError("加载失败"));
  }, [load]);

  // Debounced match preview.
  useEffect(() => {
    const keywords = keywordsText
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (keywords.length === 0) {
      setPreviewCount(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api<{ matched: number }>("/api/v1/categories/rules/preview", {
        method: "POST",
        body: JSON.stringify({ keywords, match_field: matchField }),
      })
        .then((r) => setPreviewCount(r.matched))
        .catch(() => setPreviewCount(null));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [keywordsText, matchField]);

  async function addRule(e: FormEvent) {
    e.preventDefault();
    const keywords = keywordsText
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!categoryId || keywords.length === 0) {
      setError("请选择分类并输入至少一个关键字");
      return;
    }
    setError("");
    setMessage("");
    try {
      await api("/api/v1/categories/rules", {
        method: "POST",
        body: JSON.stringify({
          category_id: categoryId,
          keywords,
          match_field: matchField,
        }),
      });
      setKeywordsText("");
      setMessage("已添加规则");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "添加失败");
    }
  }

  async function toggleRule(rule: Rule) {
    setError("");
    try {
      await api(`/api/v1/categories/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function deleteRule(rule: Rule) {
    if (!confirm(`删除规则「${rule.keywords.join(", ")}」？`)) return;
    setError("");
    try {
      await api(`/api/v1/categories/rules/${rule.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function applyRules() {
    setApplying(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ matched: number; scanned: number }>(
        "/api/v1/categories/rules/apply",
        { method: "POST", body: JSON.stringify({ scope: "pending" }) },
      );
      setMessage(`已扫描 ${result.scanned} 条，命中并更新 ${result.matched} 条`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "应用失败");
    } finally {
      setApplying(false);
    }
  }

  async function mergeRules() {
    if (!confirm("把分类和匹配字段相同的规则合并成一条？")) return;
    setError("");
    setMessage("");
    try {
      await api("/api/v1/categories/rules/merge", { method: "POST", body: "{}" });
      setMessage("已整合同类规则");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "整合失败");
    }
  }

  const catLabel = (id: string) =>
    categories.find((c) => c.id === id)?.label || id;

  return (
    <div className="space-y-8">
      <form onSubmit={addRule} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[1fr_auto_auto]">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">分类</span>
            <select
              className="field"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              <option value="">选择分类</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">匹配字段</span>
            <select
              className="field"
              value={matchField}
              onChange={(e) => setMatchField(e.target.value)}
            >
              <option value="name">名称</option>
              <option value="merchant">商户</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink-600">关键字（逗号分隔）</span>
            <input
              className="field"
              value={keywordsText}
              onChange={(e) => setKeywordsText(e.target.value)}
              placeholder="牛奶, milk"
            />
            {previewCount !== null && (
              <p className="mt-1 text-xs text-ink-400">
                将命中 {previewCount} 条现有账单
              </p>
            )}
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary">
            添加规则
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={applyRules}
            disabled={applying || rules.length === 0}
          >
            {applying ? "应用中…" : "应用到已有条目"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={mergeRules}
            disabled={rules.length < 2}
          >
            整合同类规则
          </button>
        </div>
      </form>

      {error && <p className="text-sm text-red-700">{error}</p>}
      {message && <p className="text-sm text-ink-600">{message}</p>}

      <section>
        <h2 className="font-display text-xl text-ink-800">现有规则</h2>
        {rules.length === 0 ? (
          <p className="mt-3 text-sm text-ink-400">还没有规则</p>
        ) : (
          <ul className="mt-3 divide-y divide-ink-100">
            {rules.map((rule) => (
              <li key={rule.id} className="flex items-center gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-ink-800">
                    <span className="font-medium">{catLabel(rule.category_id)}</span>
                    <span className="mx-2 text-ink-300">←</span>
                    {rule.keywords.join(", ")}
                  </p>
                  <p className="text-xs text-ink-400">
                    {rule.match_field === "merchant" ? "匹配商户" : "匹配名称"}
                  </p>
                </div>
                <button
                  type="button"
                  className={`text-sm ${rule.enabled ? "text-emerald-700" : "text-ink-400"}`}
                  onClick={() => toggleRule(rule)}
                >
                  {rule.enabled ? "启用" : "停用"}
                </button>
                <button
                  type="button"
                  className="text-sm text-red-700"
                  onClick={() => deleteRule(rule)}
                >
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function ClassificationRulesPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <Link to="/account" className="text-sm text-ink-500 hover:text-ink-800">
          ← 账户
        </Link>
        <h1 className="mt-3 font-display text-3xl text-ink-800">分类规则</h1>
        <p className="mt-2 text-sm text-ink-500">
          名称或商户名包含某关键字时，直接分类到指定分类（最长关键字优先，先于 AI 生效）。
        </p>
      </div>
      <ClassificationRules />
    </div>
  );
}
