/**
 * Root-path gates for multitenant landing and role-based home redirects.
 */
import { ReactElement } from 'react';
import { Navigate } from 'react-router-dom';
import BaseRoutes from '@spiffworkflow-frontend/views/BaseRoutes';
import { UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import UserService from './services/UserService';
import TenantSelectPage from './views/TenantSelectPage';

type AbilityLike = {
  can: (method: string, uri: string) => boolean;
};

type TargetUriMap = {
  processGroupListPath: string;
  processInstanceListPath: string;
  messageInstanceListPath: string;
  secretListPath: string;
  connectorsGroupedPath: string;
  m8flowTemplateListPath: string;
  m8flowTenantManagementPath: string;
  m8flowTenantListPath: string;
};

export type RootGateSharedProps = {
  extensionUxElements: UiSchemaUxElement[] | null;
  setAdditionalNavElement: (el: ReactElement | null) => void;
  isMobile: boolean;
  ability: AbilityLike;
  targetUris: TargetUriMap;
  permissionsLoaded: boolean;
};

type FallbackLanding = {
  path: string;
  httpMethod: string;
  permissionUri: keyof TargetUriMap;
};

const ROLE_FALLBACK_LANDINGS: FallbackLanding[] = [
  { path: '/process-groups', httpMethod: 'GET', permissionUri: 'processGroupListPath' },
  { path: '/process-instances', httpMethod: 'GET', permissionUri: 'processInstanceListPath' },
  { path: '/messages', httpMethod: 'GET', permissionUri: 'messageInstanceListPath' },
  { path: '/configuration', httpMethod: 'GET', permissionUri: 'secretListPath' },
  { path: '/connectors', httpMethod: 'GET', permissionUri: 'connectorsGroupedPath' },
  { path: '/templates', httpMethod: 'GET', permissionUri: 'm8flowTemplateListPath' },
  { path: '/tenant-management', httpMethod: 'GET', permissionUri: 'm8flowTenantManagementPath' },
  { path: '/tenants', httpMethod: 'GET', permissionUri: 'm8flowTenantListPath' },
];

function homeAllowed(ability: AbilityLike): boolean {
  const canUpdateTasks = ability.can('PUT', '/tasks/*');
  const superAdminReadOnlyHome =
    UserService.isSuperAdmin() && ability.can('GET', '/tasks/*');
  return canUpdateTasks || superAdminReadOnlyHome;
}

function baseRoutesElement(props: RootGateSharedProps) {
  return (
    <BaseRoutes
      extensionUxElements={props.extensionUxElements}
      setAdditionalNavElement={props.setAdditionalNavElement}
      isMobile={props.isMobile}
    />
  );
}

/** Redirects roles that don't have access to Home to their respective default pages. */
export function RoleBasedRootGate(props: RootGateSharedProps) {
  if (!props.permissionsLoaded) {
    return null;
  }

  if (homeAllowed(props.ability)) {
    return baseRoutesElement(props);
  }

  for (const landing of ROLE_FALLBACK_LANDINGS) {
    const uri = props.targetUris[landing.permissionUri];
    if (props.ability.can(landing.httpMethod, uri)) {
      return <Navigate to={landing.path} replace />;
    }
  }

  return baseRoutesElement(props);
}

function shouldBypassTenantSelect(props: RootGateSharedProps): boolean {
  if (props.ability.can('GET', props.targetUris.m8flowTenantListPath)) {
    return true;
  }
  if (UserService.isLoggedIn()) {
    return true;
  }
  return UserService.hasSelectedTenantCookie();
}

/** When ENABLE_MULTITENANT: at "/" show the sign-in landing until the user authenticates. */
export function MultitenantRootGate(props: RootGateSharedProps) {
  if (!props.permissionsLoaded) {
    return null;
  }

  if (shouldBypassTenantSelect(props)) {
    return <RoleBasedRootGate {...props} />;
  }

  return <TenantSelectPage />;
}
