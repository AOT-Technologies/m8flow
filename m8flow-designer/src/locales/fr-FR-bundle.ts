import type { Translation } from '.';
import acceptInvitation from './fr-FR/acceptInvitation.json';
import apiKeys from './fr-FR/apiKeys.json';
import common from './fr-FR/common.json';
import configuration from './fr-FR/configuration.json';
import connectors from './fr-FR/connectors.json';
import home from './fr-FR/home.json';
import mcpConnection from './fr-FR/mcpConnection.json';
import mcpTools from './fr-FR/mcpTools.json';
import messages from './fr-FR/messages.json';
import modeler from './fr-FR/modeler.json';
import nats from './fr-FR/nats.json';
import processInstances from './fr-FR/processInstances.json';
import processModelDetail from './fr-FR/processModelDetail.json';
import processes from './fr-FR/processes.json';
import shell from './fr-FR/shell.json';
import taskReview from './fr-FR/taskReview.json';
import templates from './fr-FR/templates.json';
import tenantManagement from './fr-FR/tenantManagement.json';
import tenantSelect from './fr-FR/tenantSelect.json';
import tenants from './fr-FR/tenants.json';

// Typed as the English tree, so a key missing from French fails `tsc`.
const fr: Translation = {
  acceptInvitation,
  apiKeys,
  common,
  configuration,
  connectors,
  home,
  mcpConnection,
  mcpTools,
  messages,
  modeler,
  nats,
  processInstances,
  processModelDetail,
  processes,
  shell,
  taskReview,
  templates,
  tenantManagement,
  tenantSelect,
  tenants,
};

export default fr;
