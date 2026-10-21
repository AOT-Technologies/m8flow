import type { Translation } from '.';
import acceptInvitation from './cs-CZ/acceptInvitation.json';
import apiKeys from './cs-CZ/apiKeys.json';
import common from './cs-CZ/common.json';
import configuration from './cs-CZ/configuration.json';
import connectors from './cs-CZ/connectors.json';
import home from './cs-CZ/home.json';
import mcpConnection from './cs-CZ/mcpConnection.json';
import mcpTools from './cs-CZ/mcpTools.json';
import messages from './cs-CZ/messages.json';
import modeler from './cs-CZ/modeler.json';
import nats from './cs-CZ/nats.json';
import processInstances from './cs-CZ/processInstances.json';
import processModelDetail from './cs-CZ/processModelDetail.json';
import processes from './cs-CZ/processes.json';
import shell from './cs-CZ/shell.json';
import taskReview from './cs-CZ/taskReview.json';
import templates from './cs-CZ/templates.json';
import tenantManagement from './cs-CZ/tenantManagement.json';
import tenantSelect from './cs-CZ/tenantSelect.json';
import tenants from './cs-CZ/tenants.json';

// Typed as the English tree, so a key missing from Czech fails `tsc`.
const cs: Translation = {
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

export default cs;
