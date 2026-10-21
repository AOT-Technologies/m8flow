import type { Translation } from '.';
import acceptInvitation from './pt-PT/acceptInvitation.json';
import apiKeys from './pt-PT/apiKeys.json';
import common from './pt-PT/common.json';
import configuration from './pt-PT/configuration.json';
import connectors from './pt-PT/connectors.json';
import home from './pt-PT/home.json';
import mcpConnection from './pt-PT/mcpConnection.json';
import mcpTools from './pt-PT/mcpTools.json';
import messages from './pt-PT/messages.json';
import modeler from './pt-PT/modeler.json';
import nats from './pt-PT/nats.json';
import processInstances from './pt-PT/processInstances.json';
import processModelDetail from './pt-PT/processModelDetail.json';
import processes from './pt-PT/processes.json';
import shell from './pt-PT/shell.json';
import taskReview from './pt-PT/taskReview.json';
import templates from './pt-PT/templates.json';
import tenantManagement from './pt-PT/tenantManagement.json';
import tenantSelect from './pt-PT/tenantSelect.json';
import tenants from './pt-PT/tenants.json';

// Typed as the English tree, so a key missing from European Portuguese fails `tsc`.
const ptPT: Translation = {
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

export default ptPT;
