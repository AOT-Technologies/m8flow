/**
 * Shared constants for the E2E specs.
 *
 * The SEED_PRIMARY_FILE / SEED_USER_TASK_* values describe wfh-approval.bpmn
 * (e2e/seed/catalog/templates/work-from-home/): the primary diagram of the
 * seeded "E2E Work From Home Request" model and of the mock models the
 * Processes specs create. Modeler specs open
 * their own copy of the seeded model (helpers/seedCatalog.ts).
 */

/** Slug of the seed tenant: used for /tenants/slug/{slug} and the tenant picker
 * (organization-option-{alias}; the Keycloak organization alias is the tenant slug). */
export const SEED_TENANT_SLUG = 'm8flow';
/** Tenant the tests work in. A user who belongs to several tenants is put in
 * this one whenever the "Select a Tenant" page appears (see continueInTenant). */
export const TEST_TENANT_SLUG = process.env.M8FLOW_E2E_TENANT_SLUG ?? SEED_TENANT_SLUG;
export const SEED_PRIMARY_FILE = 'wfh-approval.bpmn';

/** A real task in the seed diagram, stable across runs (not a synthesized id). */
export const SEED_USER_TASK_ELEMENT_ID = 'Activity_submit_wfh';
export const SEED_USER_TASK_NAME = 'Submit WFH Request';

/**
 * m8flow-backend origin for direct API calls from e2e setup code (seeding
 * phase-dedicated fixture files). Mirrors api.ts's own VITE_API_BASE_URL /
 * VITE_BACKEND_BASE_URL fallback so e2e and app code agree on the default
 * without either importing the other.
 */
export const BACKEND_BASE_URL =
  process.env.M8FLOW_BACKEND_BASE_URL ?? 'http://localhost:6840';

/** Second organization used only by Identity + Auth parity e2e (ticket 06). */
export const PARITY_SECOND_TENANT_SLUG = 'e2e-identity-auth-second';
export const PARITY_SECOND_TENANT_NAME = 'E2E Identity Auth Second';

/**
 * Keycloak origin and shared realm, used only by e2e cleanup to delete the
 * mock users that invitation tests create (see backendApi.ts).
 */
export const KEYCLOAK_BASE_URL = process.env.M8FLOW_E2E_KEYCLOAK_URL ?? 'http://localhost:6842';
export const SHARED_REALM = process.env.M8FLOW_E2E_SHARED_REALM ?? 'm8flow';

/**
 * Mock e-mail domain for invited test users. `.test` is reserved (RFC 2606),
 * so no real mailbox is ever contacted. Cleanup only touches users whose
 * address starts with `e2e-` and ends with this domain.
 */
export const MOCK_EMAIL_DOMAIN = 'example.test';
