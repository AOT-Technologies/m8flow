import { useMemo } from "react";
import { useUriListForPermissions as useSpiffUriListForPermissions } from "@spiffworkflow-frontend/hooks/UriListForPermissions";

export const useM8flowUriListForPermissions = () => {
  const { targetUris: spiffTargetUris } = useSpiffUriListForPermissions();

  const targetUris = useMemo(() => {
    return {
      ...spiffTargetUris,
      m8flowTenantManagementPath: "/m8flow/tenant-management",
      m8flowTenantListPath: "/m8flow/tenants",
      m8flowTemplateListPath: "/m8flow/templates",
      serviceTaskListPath: "/service-tasks",
      connectorsGroupedPath: "/m8flow/connectors-grouped",
      connectorTemplateListPath: "/m8flow/connector-templates",
      // Reads gate the modeler dropdown; writes gate profile management.
      connectorProfileListPath: "/m8flow/connector-profiles",
      m8flowMcpConnectionPath: "/m8flow/mcp-connection",
      m8flowNatsTokensPath: "/m8flow/nats-tokens",
      // Event history is the one NATS monitoring view a tenant-admin may read (rows carry a
      // tenant; /varz and /jsz do not), so this is what gates the page and nav item rather
      // than a super-admin flag.
      m8flowNatsEventsPath: "/m8flow/nats/events",
    };
  }, [spiffTargetUris]);

  return { targetUris };
};
