import i18n from '@/i18n';

/**
 * Format an epoch-seconds timestamp as a short relative string matching the
 * Home mockup ("2h ago", "3d ago"). Returns "—" when missing.
 */
export function formatRelativeTime(
  timestamp: string | number | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (timestamp == null) {
    return '—';
  }
  const timestampMs = typeof timestamp === 'number' ? timestamp * 1000 : Date.parse(timestamp);
  if (!Number.isFinite(timestampMs)) return '—';
  const diffSec = Math.max(0, Math.floor(nowMs / 1000) - Math.floor(timestampMs / 1000));
  if (diffSec < 60) {
    return i18n.t('common.relativeTime.secondsAgo', { value: diffSec });
  }
  const minutes = Math.floor(diffSec / 60);
  if (minutes < 60) {
    return i18n.t('common.relativeTime.minutesAgo', { value: minutes });
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return i18n.t('common.relativeTime.hoursAgo', { value: hours });
  }
  const days = Math.floor(hours / 24);
  return i18n.t('common.relativeTime.daysAgo', { value: days });
}

/**
 * Longer relative phrases matching the My tasks mockup
 * ("about 10 hours ago", "3 days ago").
 */
export function formatRelativeTimeVerbose(
  timestamp: string | number | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (timestamp == null) {
    return '—';
  }
  const timestampMs = typeof timestamp === 'number' ? timestamp * 1000 : Date.parse(timestamp);
  if (!Number.isFinite(timestampMs)) return '—';
  const diffSec = Math.max(0, Math.floor(nowMs / 1000) - Math.floor(timestampMs / 1000));
  if (diffSec < 60) {
    return i18n.t('common.relativeTime.justNow');
  }
  const minutes = Math.floor(diffSec / 60);
  if (minutes < 60) {
    return i18n.t('common.relativeTime.aboutMinutesAgo', { count: minutes });
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return i18n.t('common.relativeTime.aboutHoursAgo', { count: hours });
  }
  const days = Math.floor(hours / 24);
  return i18n.t('common.relativeTime.daysAgoVerbose', { count: days });
}
