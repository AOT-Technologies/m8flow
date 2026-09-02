/**
 * Primary-nav catalog as plain data; icons are resolved at render time.
 */
import type { ReactElement } from 'react';
import {
  Build,
  Business,
  Cable,
  Description,
  Extension,
  Home,
  Hub,
  Markunread,
  Schema,
  SettingsApplicationsSharp,
  Speed,
  Storage,
  Timeline,
  VpnKey,
} from '@mui/icons-material';
import type { TFunction } from 'i18next';
import type { UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';

export const NAV_IDS = {
  home: 'home',
  processes: 'processes',
  processInstances: 'processInstances',
  messages: 'messages',
  configuration: 'configuration',
  connectors: 'connectors',
  mcpConnection: 'mcpConnection',
  mcpToolsCatalog: 'mcpToolsCatalog',
  manageToken: 'manageToken',
  templates: 'templates',
  tenantManagement: 'tenantManagement',
  monitoringCelery: 'monitoringCelery',
  monitoringNats: 'monitoringNats',
} as const;

export type SideNavIconKey =
  | 'home'
  | 'schema'
  | 'timeline'
  | 'mail'
  | 'settings'
  | 'hub'
  | 'cable'
  | 'build'
  | 'vpnKey'
  | 'description'
  | 'business'
  | 'speed'
  | 'storage'
  | 'extension';

export type SideNavCatalogEntry = {
  label: string;
  iconKey: SideNavIconKey;
  path: string;
  id: string;
  permissionRoutes?: string[];
  superAdminOnly?: boolean;
};

const ICON_MAP: Record<SideNavIconKey, () => ReactElement> = {
  home: () => <Home />,
  schema: () => <Schema />,
  timeline: () => <Timeline />,
  mail: () => <Markunread />,
  settings: () => <SettingsApplicationsSharp />,
  hub: () => <Hub />,
  cable: () => <Cable />,
  build: () => <Build />,
  vpnKey: () => <VpnKey />,
  description: () => <Description />,
  business: () => <Business />,
  speed: () => <Speed />,
  storage: () => <Storage />,
  extension: () => <Extension />,
};

export function iconForNavKey(key: SideNavIconKey): ReactElement {
  return ICON_MAP[key]();
}

type CatalogOpts = {
  t: TFunction;
  targetUris: Record<string, string>;
  mcpEnabled: boolean;
  natsMonitoringEnabled: boolean;
};

export function buildSideNavCatalog(opts: CatalogOpts): SideNavCatalogEntry[] {
  const { t, targetUris, mcpEnabled, natsMonitoringEnabled } = opts;
  const entries: SideNavCatalogEntry[] = [
    {
      label: t('home'),
      iconKey: 'home',
      path: '/',
      id: NAV_IDS.home,
      permissionRoutes: ['/tasks/*'],
    },
    {
      label: t('processes'),
      iconKey: 'schema',
      path: '/process-groups',
      id: NAV_IDS.processes,
      permissionRoutes: [targetUris.processGroupListPath],
    },
    {
      label: t('process_instances'),
      iconKey: 'timeline',
      path: '/process-instances',
      id: NAV_IDS.processInstances,
      permissionRoutes: [targetUris.processInstanceListPath],
    },
    {
      label: t('messages'),
      iconKey: 'mail',
      path: '/messages',
      id: NAV_IDS.messages,
      permissionRoutes: [targetUris.messageInstanceListPath],
    },
    {
      label: t('configuration'),
      iconKey: 'settings',
      path: '/configuration',
      id: NAV_IDS.configuration,
      permissionRoutes: [targetUris.secretListPath],
    },
    {
      label: t('connectors'),
      iconKey: 'hub',
      path: '/connectors',
      id: NAV_IDS.connectors,
      permissionRoutes: [targetUris.connectorsGroupedPath],
    },
  ];

  if (mcpEnabled) {
    entries.push({
      label: t('mcp_connection'),
      iconKey: 'cable',
      path: '/mcp-connection',
      id: NAV_IDS.mcpConnection,
      permissionRoutes: [targetUris.m8flowMcpConnectionPath],
    });
    entries.push({
      label: t('mcp_tools_catalog'),
      iconKey: 'build',
      path: '/mcp-tools',
      id: NAV_IDS.mcpToolsCatalog,
      permissionRoutes: [targetUris.m8flowMcpToolsCatalogPath],
    });
  }

  entries.push(
    {
      label: t('manage_token'),
      iconKey: 'vpnKey',
      path: '/manage-token',
      id: NAV_IDS.manageToken,
      permissionRoutes: [targetUris.m8flowNatsTokensPath],
    },
    {
      label: t('templates'),
      iconKey: 'description',
      path: '/templates',
      id: NAV_IDS.templates,
      permissionRoutes: ['/m8flow/templates'],
    },
    {
      label: t('tenant_management'),
      iconKey: 'business',
      path: '/tenant-management',
      id: NAV_IDS.tenantManagement,
      permissionRoutes: [targetUris.m8flowTenantManagementPath],
    },
    {
      label: t('celery_monitoring'),
      iconKey: 'speed',
      path: '/monitoring/celery',
      id: NAV_IDS.monitoringCelery,
      superAdminOnly: true,
    },
  );

  if (natsMonitoringEnabled) {
    entries.push({
      label: t('nats_monitoring'),
      iconKey: 'storage',
      path: '/monitoring/nats',
      id: NAV_IDS.monitoringNats,
      // Not superAdminOnly: tenant-admins get the event-history tab, and tenant roles are
      // not in the JWT, so visibility has to come from the permission grant. The page
      // hides the broker-wide tabs from non-super-admins itself.
      permissionRoutes: [targetUris.m8flowNatsEventsPath],
    });
  }

  return entries;
}

/** Prefix → nav id. Longer / more specific prefixes win via ordered checks. */
const PATH_ACTIVE_RULES: Array<{ test: (p: string) => boolean; id: string }> = [
  { test: (p) => p === '/' || p === '/started-by-me', id: NAV_IDS.home },
  { test: (p) => p.startsWith('/process-instances'), id: NAV_IDS.processInstances },
  { test: (p) => p.startsWith('/process-'), id: NAV_IDS.processes },
  { test: (p) => p === '/messages', id: NAV_IDS.messages },
  { test: (p) => p.startsWith('/configuration'), id: NAV_IDS.configuration },
  { test: (p) => p.startsWith('/connectors'), id: NAV_IDS.connectors },
  { test: (p) => p.startsWith('/mcp-connection'), id: NAV_IDS.mcpConnection },
  { test: (p) => p.startsWith('/mcp-tools'), id: NAV_IDS.mcpToolsCatalog },
  { test: (p) => p.startsWith('/manage-token'), id: NAV_IDS.manageToken },
  { test: (p) => p.startsWith('/templates'), id: NAV_IDS.templates },
  { test: (p) => p.startsWith('/tenant-management'), id: NAV_IDS.tenantManagement },
  { test: (p) => p.startsWith('/monitoring/celery'), id: NAV_IDS.monitoringCelery },
  { test: (p) => p.startsWith('/monitoring/nats'), id: NAV_IDS.monitoringNats },
];

export function resolveActiveNavId(pathname: string): string | null {
  for (const rule of PATH_ACTIVE_RULES) {
    if (rule.test(pathname)) {
      return rule.id;
    }
  }
  return null;
}

export function appendExtensionCatalogEntries(
  entries: SideNavCatalogEntry[],
  uxElement: UiSchemaUxElement,
  pathname: string,
): string | null {
  const extensionPath = `/extensions${uxElement.page}`;
  entries.push({
    label: uxElement.label,
    iconKey: 'extension',
    path: extensionPath,
    id: uxElement.page,
  });
  return pathname === extensionPath ? uxElement.page : null;
}

/** Reserve space below the list for the optional secondary panel (TreePanel, etc.). */
export function secondaryPanelHeightPx(entryCount: number): number {
  return 45 * entryCount + 140;
}
