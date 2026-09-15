/**
 * Connector templates and profiles for the modeler's properties panel.
 *
 * The properties panel renders synchronously, so it cannot await a fetch. This
 * store follows the pattern bpmn-js-spiffworkflow already uses for the operator
 * list: the first render kicks off a load, the result is cached, and subscribers
 * re-render when it lands.
 */
import HttpService from '../../services/HttpService';

export interface ConnectorFieldDescriptor {
  /** The parameter name the connector proxy expects. */
  id: string;
  label: string;
  type: string;
  required: boolean;
  group: string;
  binding: string;
  secret: boolean;
  choices?: { value: unknown; label: string }[];
  format?: string;
  minLength?: number;
  maxLength?: number;
  helpText?: string;
  example?: string;
  default?: unknown;
}

export interface ConnectorTemplate {
  id: string;
  definitionId: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  docsUrl: string;
  supportsProfiles: boolean;
  groups: { id: string; label: string }[];
  profileFields: ConnectorFieldDescriptor[];
  taskFields: ConnectorFieldDescriptor[];
}

export interface ConnectorProfile {
  id: string;
  connector_type: string;
  profile_name: string;
  display_name: string;
  description: string | null;
  config: Record<string, unknown>;
  configured_secrets: string[];
  is_active: boolean;
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

/** Subscribe to load completion. Returns an unsubscribe function. */
export function onConnectorProfilesLoaded(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Load templates and profiles once.
 *
 * Only active profiles are requested: a deactivated profile must not be
 * selectable, while the management UI still lists it so it stays recoverable.
 *
 * Failures are swallowed deliberately. A modeler that cannot reach these
 * endpoints -- no permission, backend down -- must still open and edit diagrams;
 * it simply offers no profile options.
 */
export function loadConnectorProfiles(): void {
  if (loadState !== 'idle') {
    return;
  }
  loadState = 'loading';

  Promise.all([
    get<ConnectorTemplate[]>('/m8flow/connector-templates').catch(() => []),
    get<ConnectorProfile[]>(
      '/m8flow/connector-profiles?include_inactive=false',
    ).catch(() => []),
  ]).then(([loadedTemplates, loadedProfiles]) => {
    templates = Array.isArray(loadedTemplates) ? loadedTemplates : [];
    profiles = Array.isArray(loadedProfiles) ? loadedProfiles : [];
    loadState = 'loaded';
    listeners.forEach((listener) => listener());
  });
}

/**
 * Forget everything loaded so far.
 *
 * Called when a modeler is torn down: profiles are tenant data, and this module
 * outlives any single modeler instance, so a stale cache would leak one tenant's
 * profile names into the next modeler.
 */
export function resetConnectorProfiles(): void {
  templates = [];
  profiles = [];
  loadState = 'idle';
  listeners.clear();
}

/** Connector type of an operator id: "smtp/SendHTMLEmail" -> "smtp". */
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

/**
 * Active profiles for one connector, in a stable display order.
 *
 * Scoping by connector type is what bounds this list: it grows with the tenant's
 * own saved profiles, never with the connector catalogue.
 */
export function profilesFor(connectorType: string): ConnectorProfile[] {
  return profiles
    .filter(
      (profile) => profile.connector_type === connectorType && profile.is_active,
    )
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
