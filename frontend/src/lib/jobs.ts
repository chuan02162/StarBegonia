import { api } from "../api/client";

export type JobProgress = {
  stage?: string;
  current?: number;
  total?: number;
  percent?: number;
  message?: string;
};

export type JobStatus = {
  job_id: string;
  status: string;
  progress?: JobProgress;
  error?: string;
  result?: Record<string, unknown>;
};

export type PollJobOptions = {
  /** Prefer sources job endpoint; falls back to categories. */
  endpoint?: "sources" | "categories";
  intervalMs?: number;
  maxAttempts?: number;
  onProgress?: (progress: JobProgress, status: string) => void;
};

function jobPath(endpoint: "sources" | "categories", jobId: string) {
  return endpoint === "categories"
    ? `/api/v1/categories/jobs/${jobId}`
    : `/api/v1/sources/jobs/${jobId}`;
}

export async function pollJob(
  jobId: string,
  options: PollJobOptions = {},
): Promise<JobStatus> {
  const endpoint = options.endpoint || "sources";
  const intervalMs = options.intervalMs ?? 1000;
  const maxAttempts = options.maxAttempts ?? 3600;

  for (let i = 0; i < maxAttempts; i++) {
    const job = await api<JobStatus>(jobPath(endpoint, jobId));
    if (options.onProgress) {
      const progress =
        job.progress ||
        (job.status === "queued"
          ? { percent: 0, message: "排队中…" }
          : job.status === "started"
            ? { percent: 0, message: "运行中…" }
            : undefined);
      if (progress) options.onProgress(progress, job.status);
    }
    if (job.status === "finished" || job.status === "failed") {
      return job;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return {
    job_id: jobId,
    status: "timeout",
    error: "任务超时，请稍后刷新查看结果",
  };
}
