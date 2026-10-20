import type { Translation } from '.';
import acceptInvitation from './zh-CN/acceptInvitation.json';
import apiKeys from './zh-CN/apiKeys.json';
import common from './zh-CN/common.json';
import configuration from './zh-CN/configuration.json';
import connectors from './zh-CN/connectors.json';
import home from './zh-CN/home.json';
import mcpConnection from './zh-CN/mcpConnection.json';
import mcpTools from './zh-CN/mcpTools.json';
import messages from './zh-CN/messages.json';
import modeler from './zh-CN/modeler.json';
import nats from './zh-CN/nats.json';
import processInstances from './zh-CN/processInstances.json';
import processModelDetail from './zh-CN/processModelDetail.json';
import processes from './zh-CN/processes.json';
import shell from './zh-CN/shell.json';
import taskReview from './zh-CN/taskReview.json';
import templates from './zh-CN/templates.json';
import tenantManagement from './zh-CN/tenantManagement.json';
import tenantSelect from './zh-CN/tenantSelect.json';
import tenants from './zh-CN/tenants.json';

// Typed as the English tree, so a key missing from Chinese fails `tsc`.
const zh: Translation = {
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

export default zh;
