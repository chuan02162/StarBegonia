import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

export type SourceStatusMap = Record<string, boolean>;

let cache: SourceStatusMap = {};
const listeners = new Set<(next: SourceStatusMap) => void>();

function notify() {
  for (const listener of listeners) listener({ ...cache });
}

export function setSourceConnected(sourceType: string, connected: boolean) {
  cache = { ...cache, [sourceType]: connected };
  notify();
}

export async function refreshSourceStatus(): Promise<SourceStatusMap> {
  const data = await api<{
    sources: { source_type: string; connected: boolean }[];
  }>("/api/v1/sources/status");
  const next: SourceStatusMap = {};
  for (const s of data.sources) next[s.source_type] = s.connected;
  cache = { ...cache, ...next };
  notify();
  return { ...cache };
}

export function useSourceStatus(): SourceStatusMap {
  const [status, setStatus] = useState<SourceStatusMap>(cache);
  useEffect(() => {
    const listener = (next: SourceStatusMap) => setStatus(next);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return status;
}

export function useRefreshSourceStatus() {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async () => {
    setBusy(true);
    try {
      return await refreshSourceStatus();
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, run };
}
