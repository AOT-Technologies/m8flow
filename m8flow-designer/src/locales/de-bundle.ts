import type { Translation } from '.';
import acceptInvitation from './de/acceptInvitation.json';
import apiKeys from './de/apiKeys.json';
import common from './de/common.json';
import configuration from './de/configuration.json';
import connectors from './de/connectors.json';
import home from './de/home.json';
import mcpConnection from './de/mcpConnection.json';
import mcpTools from './de/mcpTools.json';
import messages from './de/messages.json';
import modeler from './de/modeler.json';
import nats from './de/nats.json';
import processInstances from './de/processInstances.json';
import processModelDetail from './de/processModelDetail.json';
import processes from './de/processes.json';
import shell from './de/shell.json';
import taskReview from './de/taskReview.json';
import templates from './de/templates.json';
import tenantManagement from './de/tenantManagement.json';
import tenantSelect from './de/tenantSelect.json';
import tenants from './de/tenants.json';

// Typed as the English tree, so a key missing from German fails `tsc`.
const de: Translation = {
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

export default de;
