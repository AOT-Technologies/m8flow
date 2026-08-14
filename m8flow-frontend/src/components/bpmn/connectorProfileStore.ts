/**
 * Connector profiles and schemas for the modeler's properties panel.
 *
 * The properties panel renders synchronously, so it cannot await a fetch. This
 * store follows the pattern bpmn-js-spiffworkflow uses for the operator list:
 * the first render triggers a load, the load caches, and subscribers re-render
 * when it lands.
 */
import HttpService from '../../services/HttpService';

export interface ConnectorProfileFieldDescriptor {
  id: string;
  label: string;
  type: string;
  required: boolean;
  group: string;
  binding: string;
  secret: boolean;
  default?: unknown;
  choices?: { value: unknown; label: string }[];
  format?: string;
  minLength?: number;
  maxLength?: number;
  helpText?: string;
  example?: string;
}

export interface ConnectorTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  docsUrl: string;
  supportsProfiles: boolean;
  testOperation: string | null;
  groups: { id: string; label: string }[];
  profileFields: ConnectorProfileFieldDescriptor[];
  taskFields: ConnectorProfileFieldDescriptor[];
}

export interface ConnectorProfile {
  id: number;
  connector_type: string;
  profile_name: string;
  display_name: string;
  description: string | null;
  config: Record<string, unknown>;
  configured_secrets: string[];
  is_active: boolean;
  is_default: boolean;
}

type Listener = () => void;

let templates: ConnectorTemplate[] = [];
let profiles: ConnectorProfile[] = [];
let loadState: 'idle' | 'loading' | 'loaded' = 'idle';
const listeners = new Set<Listener>();

const get = <T,>(path: string): Promise<T> =>
  new Promise((resolve, reject) => {
    HttpService.makeCallToBackend({
      path,
      successCallback: resolve as (result: unknown) => void,
      failureCallback: reject,
    });
  });

function notify() {
  listeners.forEach((listener) => listener());
}

/** Subscribe to load completion. Returns an unsubscribe function. */
export function onConnectorProfilesLoaded(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Load templates and profiles once.
 *
 * Failures are swallowed on purpose: a modeler that cannot reach the profile
 * endpoints (no permission, backend down) must still open and edit diagrams -
 * it just shows no profile options.
 */
export function loadConnectorProfiles(): void {
  if (loadState !== 'idle') {
    return;
  }
  loadState = 'loading';

  Promise.all([
    get<ConnectorTemplate[]>('/m8flow/connector-templates').catch(() => []),
    get<ConnectorProfile[]>('/m8flow/connector-profiles').catch(() => []),
  ]).then(([loadedTemplates, loadedProfiles]) => {
    templates = Array.isArray(loadedTemplates) ? loadedTemplates : [];
    profiles = Array.isArray(loadedProfiles) ? loadedProfiles : [];
    loadState = 'loaded';
    notify();
  });
}

/**
 * Forget everything loaded so far.
 *
 * Called when a modeler is torn down: profiles are tenant data, and this module
 * outlives any single modeler instance.
 */
export function resetConnectorProfiles(): void {
  templates = [];
  profiles = [];
  loadState = 'idle';
  listeners.clear();
}

/** Connector type of an operator id, e.g. "smtp/SendHTMLEmail" -> "smtp". */
export function connectorTypeForOperator(operatorId: string): string {
  if (!operatorId) {
    return '';
  }
  const slash = operatorId.indexOf('/');
  return slash === -1 ? operatorId : operatorId.slice(0, slash);
}

export function templateFor(connectorType: string): ConnectorTemplate | null {
  return templates.find((template) => template.id === connectorType) ?? null;
}

/** Active profiles for one connector, in display order. */
export function profilesFor(connectorType: string): ConnectorProfile[] {
  return profiles
    .filter((profile) => profile.connector_type === connectorType && profile.is_active)
    .sort((a, b) => a.profile_name.localeCompare(b.profile_name));
}

/** Parameter names a profile supplies for this connector. */
export function profileFieldNames(connectorType: string): string[] {
  return templateFor(connectorType)?.profileFields.map((field) => field.id) ?? [];
}

/** Whether this connector has anything a profile could supply. */
export function supportsProfiles(connectorType: string): boolean {
  const template = templateFor(connectorType);
  return !!template && template.supportsProfiles;
}

/** Test seam: preload without HTTP. */
export function primeConnectorProfiles(
  loadedTemplates: ConnectorTemplate[],
  loadedProfiles: ConnectorProfile[],
): void {
  templates = loadedTemplates;
  profiles = loadedProfiles;
  loadState = 'loaded';
}
