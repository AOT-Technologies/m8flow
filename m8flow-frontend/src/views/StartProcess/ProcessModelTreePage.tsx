/**
 * Process model tree / start-process browser — delegate to upstream.
 *
 * SA tenant scoping is applied inside the useProcessGroups override (reads
 * GlobalTenant when the caller omits tenantId). Card tenant chips still work when
 * the API payload carries tenantName on models/groups (backend injects it);
 * upstream's processGroupToLite omits those fields on nested lites — acceptable
 * when the list is already tenant-filtered.
 */
export { default } from '@spiff-core/views/StartProcess/ProcessModelTreePage';
// Keep the named helper for unit tests that import it from this module.
export { processGroupToLite } from './processGroupToLite';
