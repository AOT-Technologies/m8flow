import type { PermissionCheckResult } from '@/lib/api';

/**
 * UI permission checks are declared once so the requested URI/method pairs
 * cannot drift from the booleans exposed by SessionProvider.
 */
export const permissionCheckTargets = {
  readProcessModels: ['/process-models', 'GET'],
  createProcessModels: ['/process-models', 'POST'],
  updateProcessModels: ['/process-models', 'PUT'],
  readProcessInstances: ['/process-instances', 'GET'],
  createProcessInstances: ['/process-instances', 'POST'],
  createProcessGroups: ['/process-groups', 'POST'],
  updateProcessGroups: ['/process-groups/{id}', 'PUT'],
  deleteProcessGroups: ['/process-groups/{id}', 'DELETE'],
  deleteProcessModels: ['/process-models/capability-check', 'DELETE'],
  copyProcessModels: ['/process-models/{id}/copy', 'POST'],
  runProcessModelTests: ['/process-models/{id}/tests/run', 'POST'],
  createScriptUnitTests: ['/process-models/{id}/script-unit-tests', 'POST'],
  runScriptUnitTests: ['/process-models/{id}/script-unit-tests/run', 'POST'],
  createProcessModelFiles: ['/process-models/{id}/files', 'POST'],
  updateProcessModelFiles: ['/process-models/{id}/files/{file}', 'PUT'],
  deleteProcessModelFiles: ['/process-models/{id}/files/{file}', 'DELETE'],
  suspendProcessInstances: ['/process-instances/{id}/suspend', 'POST'],
  resumeProcessInstances: ['/process-instances/{id}/resume', 'POST'],
  terminateProcessInstances: ['/process-instances/{id}/terminate', 'POST'],
  deleteProcessInstances: ['/process-instances/{id}', 'DELETE'],
  readMcpConnection: ['/m8flow/mcp-connection', 'GET'],
  readMessages: ['/messages', 'GET'],
  readSecrets: ['/secrets', 'GET'],
  createSecrets: ['/secrets', 'POST'],
  readConnectors: ['/m8flow/connectors-grouped', 'GET'],
  readTemplates: ['/m8flow/templates', 'GET'],
  createTemplates: ['/m8flow/templates', 'POST'],
  importTemplates: ['/m8flow/templates/import', 'POST'],
  updateTemplates: ['/m8flow/templates/{id}', 'PUT'],
  deleteTemplates: ['/m8flow/templates/{id}', 'DELETE'],
  restoreTemplates: ['/m8flow/templates/{id}/restore', 'POST'],
  updateTemplateFiles: ['/m8flow/templates/{id}/files/{file}', 'PUT'],
  deleteTemplateFiles: ['/m8flow/templates/{id}/files/{file}', 'DELETE'],
  createProcessModelsFromTemplates: ['/m8flow/templates/{id}/create-process-model', 'POST'],
  readNatsMonitoring: ['/m8flow/nats/streams', 'GET'],
  readNatsEvents: ['/m8flow/nats/events', 'GET'],
  readNatsApiKeys: ['/m8flow/nats-tokens', 'GET'],
  createNatsApiKeys: ['/m8flow/nats-tokens', 'POST'],
  revokeNatsApiKeys: ['/m8flow/nats-tokens/{id}', 'DELETE'],
  // The inbox has a narrower audience than the read-only task-list API.
  readTaskReview: ['/m8flow/task-review-access', 'GET'],
  readHomeTaskCount: ['/m8flow/home-task-count', 'GET'],
  submitTaskReviews: ['/m8flow/task-review-access/{id}/submit', 'POST'],
  createConnectorProfiles: ['/m8flow/connector-profiles', 'POST'],
  updateConnectorProfiles: ['/m8flow/connector-profiles/{id}', 'PUT'],
  deleteConnectorProfiles: ['/m8flow/connector-profiles/{id}', 'DELETE'],
  updateSecrets: ['/secrets/{key}', 'PUT'],
  deleteSecrets: ['/secrets/{key}', 'DELETE'],
  createTenants: ['/m8flow/tenant-realms', 'POST'],
  readTenantManagement: ['/m8flow/tenant-management', 'GET'],
  updateTenants: ['/m8flow/tenants/{id}', 'PUT'],
  addTenantMembers: ['/m8flow/tenants/{id}/members', 'POST'],
  removeTenantMembers: ['/m8flow/tenants/{id}/members/{username}', 'DELETE'],
  createTenantGroups: ['/m8flow/tenants/{id}/groups', 'POST'],
  updateTenantGroups: ['/m8flow/tenants/{id}/groups/{group}', 'PUT'],
  deleteTenantGroups: ['/m8flow/tenants/{id}/groups/{group}', 'DELETE'],
  updateTenantGroupMemberships: ['/m8flow/tenants/{id}/groups/{group}/members/{username}', 'PUT'],
  removeTenantGroupMemberships: ['/m8flow/tenants/{id}/groups/{group}/members/{username}', 'DELETE'],
  updateTenantGroupRoles: ['/m8flow/tenants/{id}/groups/{group}/roles/{role}', 'PUT'],
  removeTenantGroupRoles: ['/m8flow/tenants/{id}/groups/{group}/roles/{role}', 'DELETE'],
} as const;

export type PermissionCheckKey = keyof typeof permissionCheckTargets;

export function buildPermissionCheckRequest(): Record<string, string[]> {
  const request: Record<string, string[]> = {};
  for (const [uri, method] of Object.values(permissionCheckTargets)) {
    (request[uri] ??= []).push(method);
  }
  return request;
}

export function hasPermission(result: PermissionCheckResult, key: PermissionCheckKey): boolean {
  const [uri, method] = permissionCheckTargets[key];
  return result[uri]?.[method] === true;
}
