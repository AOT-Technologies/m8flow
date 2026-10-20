import enCommon from './en-US/common.json';
import enHome from './en-US/home.json';
import enShell from './en-US/shell.json';
import type enAcceptInvitation from './en-US/acceptInvitation.json';
import type enApiKeys from './en-US/apiKeys.json';
import type enConfiguration from './en-US/configuration.json';
import type enConnectors from './en-US/connectors.json';
import type enMcpConnection from './en-US/mcpConnection.json';
import type enMcpTools from './en-US/mcpTools.json';
import type enMessages from './en-US/messages.json';
import type enModeler from './en-US/modeler.json';
import type enNats from './en-US/nats.json';
import type enProcessInstances from './en-US/processInstances.json';
import type enProcessModelDetail from './en-US/processModelDetail.json';
import type enProcesses from './en-US/processes.json';
import type enTaskReview from './en-US/taskReview.json';
import type enTemplates from './en-US/templates.json';
import type enTenantManagement from './en-US/tenantManagement.json';
import type enTenantSelect from './en-US/tenantSelect.json';
import type enTenants from './en-US/tenants.json';

// What the first screen needs (sidebar, shared components, Home) is bundled; every other
// page area is lazy (see `en-pages.ts`), and every other language is lazy too (`<language>-bundle.ts`).
const en = {
  common: enCommon,
  home: enHome,
  shell: enShell,
};

/** The full English tree. Every key is typed, even for areas that load later. */
export type Translation = typeof en & {
  acceptInvitation: typeof enAcceptInvitation;
  apiKeys: typeof enApiKeys;
  configuration: typeof enConfiguration;
  connectors: typeof enConnectors;
  mcpConnection: typeof enMcpConnection;
  mcpTools: typeof enMcpTools;
  messages: typeof enMessages;
  modeler: typeof enModeler;
  nats: typeof enNats;
  processInstances: typeof enProcessInstances;
  processModelDetail: typeof enProcessModelDetail;
  processes: typeof enProcesses;
  taskReview: typeof enTaskReview;
  templates: typeof enTemplates;
  tenantManagement: typeof enTenantManagement;
  tenantSelect: typeof enTenantSelect;
  tenants: typeof enTenants;
};

/** English strings for the lazy page areas; loaded before any lazy page renders. */
export type PageTranslation = Omit<Translation, keyof typeof en>;

export const resources = { 'en-US': { translation: en } };
