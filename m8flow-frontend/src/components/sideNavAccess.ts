/**
 * Nav-item visibility rules for the primary drawer.
 * Control flow is intentionally unlike upstream SideNav's forEach gate.
 */
import type { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import UserService from '../services/UserService';
import { NAV_IDS, type SideNavCatalogEntry } from './sideNavCatalog';

type AbilityLike = { can: (method: string, uri: string) => boolean };

function methodForUri(
  uri: string,
  permissionPlan: PermissionsToCheck,
): string {
  const actions = permissionPlan[uri];
  return actions?.[0] ?? 'GET';
}

function anyRouteAllowed(
  routes: string[] | undefined,
  ability: AbilityLike,
  permissionPlan: PermissionsToCheck,
): boolean {
  if (!routes?.length) {
    return true;
  }
  return routes.some((uri) =>
    ability.can(methodForUri(uri, permissionPlan), uri),
  );
}

function homeVisible(ability: AbilityLike): boolean {
  const canWriteTasks = ability.can('PUT', '/tasks/*');
  if (canWriteTasks) {
    return true;
  }
  // Super-admins with read-only task access still see Home.
  return UserService.isSuperAdmin() && ability.can('GET', '/tasks/*');
}

export function canSeeNavEntry(
  entry: SideNavCatalogEntry,
  ability: AbilityLike,
  permissionPlan: PermissionsToCheck,
): boolean {
  if (entry.superAdminOnly) {
    return UserService.isSuperAdmin();
  }
  if (entry.id === NAV_IDS.home) {
    return homeVisible(ability);
  }
  if (!('permissionRoutes' in entry) || entry.permissionRoutes == null) {
    return true;
  }
  return anyRouteAllowed(entry.permissionRoutes, ability, permissionPlan);
}

export function buildSideNavPermissionPlan(
  targetUris: Record<string, string>,
): PermissionsToCheck {
  return {
    [targetUris.messageInstanceListPath]: ['GET'],
    [targetUris.processGroupListPath]: ['GET'],
    [targetUris.processInstanceListPath]: ['GET'],
    [targetUris.processInstanceListForMePath]: ['POST'],
    [targetUris.secretListPath]: ['GET'],
    [targetUris.connectorsGroupedPath]: ['GET'],
    [targetUris.m8flowMcpConnectionPath]: ['GET'],
    // POST gates manage-nats-tokens (tenant-admin); a bare GET hid the item for all.
    [targetUris.m8flowNatsTokensPath]: ['POST'],
    '/tasks/*': ['GET', 'PUT'],
    [targetUris.m8flowTenantManagementPath]: ['GET'],
    '/m8flow/tenants': ['GET'],
    '/m8flow/templates': ['GET'],
  };
}
