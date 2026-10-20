import type { Translation } from '.';
import acceptInvitation from './fi/acceptInvitation.json';
import apiKeys from './fi/apiKeys.json';
import common from './fi/common.json';
import configuration from './fi/configuration.json';
import connectors from './fi/connectors.json';
import home from './fi/home.json';
import mcpConnection from './fi/mcpConnection.json';
import mcpTools from './fi/mcpTools.json';
import messages from './fi/messages.json';
import modeler from './fi/modeler.json';
import nats from './fi/nats.json';
import processInstances from './fi/processInstances.json';
import processModelDetail from './fi/processModelDetail.json';
import processes from './fi/processes.json';
import shell from './fi/shell.json';
import taskReview from './fi/taskReview.json';
import templates from './fi/templates.json';
import tenantManagement from './fi/tenantManagement.json';
import tenantSelect from './fi/tenantSelect.json';
import tenants from './fi/tenants.json';

// Typed as the English tree, so a key missing from Finnish fails `tsc`.
const fi: Translation = {
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

export default fi;
