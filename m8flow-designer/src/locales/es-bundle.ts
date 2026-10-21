import type { Translation } from '.';
import acceptInvitation from './es/acceptInvitation.json';
import apiKeys from './es/apiKeys.json';
import common from './es/common.json';
import configuration from './es/configuration.json';
import connectors from './es/connectors.json';
import home from './es/home.json';
import mcpConnection from './es/mcpConnection.json';
import mcpTools from './es/mcpTools.json';
import messages from './es/messages.json';
import modeler from './es/modeler.json';
import nats from './es/nats.json';
import processInstances from './es/processInstances.json';
import processModelDetail from './es/processModelDetail.json';
import processes from './es/processes.json';
import shell from './es/shell.json';
import taskReview from './es/taskReview.json';
import templates from './es/templates.json';
import tenantManagement from './es/tenantManagement.json';
import tenantSelect from './es/tenantSelect.json';
import tenants from './es/tenants.json';

// Typed as the English tree, so a key missing from Spanish fails `tsc`.
const es: Translation = {
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

export default es;
