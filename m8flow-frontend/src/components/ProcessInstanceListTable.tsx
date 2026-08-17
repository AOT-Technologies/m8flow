/**
 * Process-instance table — delegate to upstream.
 *
 * Former fork injected a Tenant column for super-admins and hid the "Go"
 * complete-task control for them. Row payloads still include `tenantName` from
 * the backend report patch; restoring a visible column (or SA Go suppress) can
 * return as a thin post-process once a seam exists. Completion remains
 * backend-authorized.
 */
export { default } from '@spiff-core/components/ProcessInstanceListTable';
