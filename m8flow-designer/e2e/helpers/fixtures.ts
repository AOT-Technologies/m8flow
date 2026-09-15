/**
 * Real seed data confirmed live against the dev stack for tenant `m8flow`
 * (editor's tenant, and the only concrete tenant super-admin can select):
 * one process group with one process model. Not synthesized — these are the
 * actual rows `GET /v1.0/m8flow/process-models` returns. See
 * `.e2e-agent/research.md` for how this was confirmed.
 */
export const SEED_TENANT_LABEL = 'm8flow';
export const SEED_GROUP_ID = 'test-process-group';
export const SEED_GROUP_NAME = 'Test Process Group';
export const SEED_MODEL_ROUTE_ID = 'test-process-group:wfh-group-4355dd7e70';
export const SEED_MODEL_NAME = 'Single Approval';
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
