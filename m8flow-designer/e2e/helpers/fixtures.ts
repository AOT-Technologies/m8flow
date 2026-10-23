/**
 * Mock process model used by the Processes and Modeler specs. It is NOT real
 * instance data: helpers/mockCatalog.ts creates it (with the mock files in
 * e2e/fixtures/mock-model/) before a spec runs and deletes it afterwards, so
 * the tests work on any instance -- empty, groups only, or groups with models
 * -- and never change the instance's own process models.
 * The constant names keep the old SEED_ prefix so the specs did not need to
 * change; the values now point at the mock model.
 */
/** Slug of the seed tenant: used for /tenants/slug/{slug} and the tenant picker
 * (organization-option-{alias}; the Keycloak organization alias is the tenant slug). */
export const SEED_TENANT_SLUG = 'm8flow';
export const SEED_GROUP_ID = 'e2e-mock-catalog';
export const SEED_GROUP_NAME = 'E2E Mock Catalog';
export const SEED_MODEL_ID = 'e2e-mock-model';
export const SEED_MODEL_ROUTE_ID = `${SEED_GROUP_ID}:${SEED_MODEL_ID}`;
export const SEED_MODEL_NAME = 'E2E Mock Model';
export const SEED_PRIMARY_FILE = 'wfh-approval.bpmn';
export const SEED_MODEL_DETAIL_PATH = `/processes/${SEED_MODEL_ROUTE_ID}`;
export const SEED_MODELER_PATH = `/processes/${SEED_MODEL_ROUTE_ID}/modeler/${SEED_PRIMARY_FILE}`;

/** A real task in the seed diagram, stable across runs (not a synthesized id). */
export const SEED_USER_TASK_ELEMENT_ID = 'Activity_submit_wfh';
export const SEED_USER_TASK_NAME = 'Submit WFH Request';

/**
 * A second real, always-present seed process model (from the earlier
 * Process Modeler visual fidelity work's own coverage diagram) — used where
 * a test needs to prove *cross*-model navigation (e.g. Call Activity's
 * "Launch Editor"), since navigating a Call Activity to the model it's
 * already open in wouldn't prove real navigation happened.
 */
export const SECOND_SEED_MODEL_ROUTE_ID = 'element-coverage-sample:all-elements-sample';
export const SECOND_SEED_MODEL_NAME = 'All Elements Sample';
export const SECOND_SEED_PRIMARY_FILE = 'all-elements-sample.bpmn';
export const SECOND_SEED_MODELER_PATH = `/processes/${SECOND_SEED_MODEL_ROUTE_ID}/modeler/${SECOND_SEED_PRIMARY_FILE}`;

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
 * Builds the modeler route for an arbitrary file name inside the seeded
 * process model — used by phase-dedicated fixtures seeded via
 * `helpers/seedFixture.ts` so each phase's coverage diagram lives
 * side-by-side with (and never overwrites) SEED_PRIMARY_FILE.
 */
export function seedModelerPath(fileName: string): string {
  return `/processes/${SEED_MODEL_ROUTE_ID}/modeler/${fileName}`;
}

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
