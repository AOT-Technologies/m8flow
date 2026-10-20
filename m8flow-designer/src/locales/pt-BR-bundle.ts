import type { Translation } from '.';
import acceptInvitation from './pt-BR/acceptInvitation.json';
import apiKeys from './pt-BR/apiKeys.json';
import common from './pt-BR/common.json';
import configuration from './pt-BR/configuration.json';
import connectors from './pt-BR/connectors.json';
import home from './pt-BR/home.json';
import mcpConnection from './pt-BR/mcpConnection.json';
import mcpTools from './pt-BR/mcpTools.json';
import messages from './pt-BR/messages.json';
import modeler from './pt-BR/modeler.json';
import nats from './pt-BR/nats.json';
import processInstances from './pt-BR/processInstances.json';
import processModelDetail from './pt-BR/processModelDetail.json';
import processes from './pt-BR/processes.json';
import shell from './pt-BR/shell.json';
import taskReview from './pt-BR/taskReview.json';
import templates from './pt-BR/templates.json';
import tenantManagement from './pt-BR/tenantManagement.json';
import tenantSelect from './pt-BR/tenantSelect.json';
import tenants from './pt-BR/tenants.json';

// Typed as the English tree, so a key missing from Brazilian Portuguese fails `tsc`.
const ptBR: Translation = {
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

export default ptBR;
