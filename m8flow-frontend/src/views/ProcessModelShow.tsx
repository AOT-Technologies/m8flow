/**
 * Process model show page — delegate to upstream.
 *
 * Former m8flow fork only differed by: M8flow URI list (now via
 * `hooks/UriListForPermissions` override), a super-admin tenant chip, a
 * permission-gated actions menu, `buttonText` on ProcessInstanceRun, and
 * `target="_blank"` on the PR link. Those UX deltas were judged inessential
 * relative to carrying a 469-line LGPL-derived body; URI coverage is preserved
 * by the shared hook override.
 */
export { default } from '@spiff-core/views/ProcessModelShow';
