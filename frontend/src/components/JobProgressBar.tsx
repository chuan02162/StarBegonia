import type { JobProgress } from "../lib/jobs";

type Props = {
  progress: JobProgress | null;
  active?: boolean;
  className?: string;
};

export function JobProgressBar({ progress, active = true, className = "" }: Props) {
  if (!active && !progress) return null;
  const percent = Math.min(
    100,
    Math.max(0, Number(progress?.percent ?? 0) || 0),
  );
  const indeterminate = active && (!progress || !progress.total);
  const label =
    progress?.message ||
    (progress?.total
      ? `${progress.current ?? 0}/${progress.total}`
      : active
        ? "任务进行中…"
        : "");

  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && <p className="text-sm text-ink-500">{label}</p>}
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-ink-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : percent}
        aria-label={label || "任务进度"}
      >
        {indeterminate ? (
          <div className="job-progress-indeterminate h-full w-1/3 rounded-full bg-ink-600" />
        ) : (
          <div
            className="h-full rounded-full bg-ink-600 transition-[width] duration-300 ease-out"
            style={{ width: `${percent}%` }}
          />
        )}
      </div>
      {!indeterminate && progress?.total ? (
        <p className="text-xs text-ink-400">
          {progress.current ?? 0} / {progress.total}（{percent}%）
        </p>
      ) : null}
    </div>
  );
}
