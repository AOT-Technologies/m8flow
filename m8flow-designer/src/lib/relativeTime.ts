/**
 * Format an epoch-seconds timestamp as a short relative string matching the
 * Home mockup ("2h ago", "3d ago"). Returns "—" when missing.
 */
export function formatRelativeTime(
  epochSeconds: number | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (epochSeconds == null) {
    return '—';
  }
  const diffSec = Math.max(0, Math.floor(nowMs / 1000) - epochSeconds);
  if (diffSec < 60) {
    return `${diffSec}s ago`;
  }
  const minutes = Math.floor(diffSec / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Longer relative phrases matching the My tasks mockup
 * ("about 10 hours ago", "3 days ago").
 */
export function formatRelativeTimeVerbose(
  epochSeconds: number | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (epochSeconds == null) {
    return '—';
  }
  const diffSec = Math.max(0, Math.floor(nowMs / 1000) - epochSeconds);
  if (diffSec < 60) {
    return 'just now';
  }
  const minutes = Math.floor(diffSec / 60);
  if (minutes < 60) {
    return minutes === 1 ? 'about 1 minute ago' : `about ${minutes} minutes ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? 'about 1 hour ago' : `about ${hours} hours ago`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}
