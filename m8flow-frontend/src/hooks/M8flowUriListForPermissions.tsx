import { useMemo } from "react";
import { useUriListForPermissions as useSpiffUriListForPermissions } from "@spiffworkflow-frontend/hooks/UriListForPermissions";

export const useM8flowUriListForPermissions = () => {
  const { targetUris: spiffTargetUris } = useSpiffUriListForPermissions();

  const targetUris = useMemo(() => {
    return {
      ...spiffTargetUris,
      m8flowTenantListPath: "/m8flow/tenants",
      m8flowTemplateListPath: "/m8flow/templates",
      serviceTaskListPath: "/service-tasks",
      connectorsGroupedPath: "/m8flow/connectors-grouped",
    };
  }, [spiffTargetUris]);

  return { targetUris };
};
