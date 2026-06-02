/**
 * Override: useProcessGroups Hook
 *
 * Adds custom headers and forwards an optional ``tenantId`` query parameter so
 * a super-admin can narrow the cross-tenant process-group / process-model
 * listing to a single tenant.
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ProcessGroup, ProcessGroupLite } from '@spiffworkflow-frontend/interfaces';
import HttpService from '../services/HttpService';

export default function useProcessGroups({
  processInfo,
  getRunnableProcessModels = false,
  tenantId = null,
}: {
  processInfo: Record<string, any>;
  getRunnableProcessModels?: boolean;
  tenantId?: string | null;
}) {
  const [processGroups, setProcessGroups] = useState<
    ProcessGroup[] | ProcessGroupLite[] | null
  >(null);
  const [loading, setLoading] = useState(false);

  const handleProcessGroupResponse = (result: any) => {
    setProcessGroups(result.results);
    setLoading(false);
  };

  let basePath = '/process-groups';
  if (getRunnableProcessModels) {
    basePath =
      '/process-models?filter_runnable_by_user=true&recursive=true&group_by_process_group=True&per_page=2000';
  }

  let path = basePath;
  if (tenantId) {
    const separator = basePath.includes('?') ? '&' : '?';
    path = `${basePath}${separator}tenantId=${encodeURIComponent(tenantId)}`;
  }

  const getProcessGroups = async () => {
    setLoading(true);

    HttpService.makeCallToBackend({
      path,
      httpMethod: 'GET',
      extraHeaders: {
        'X-m8-Extension': 'true',
        'X-m8-Request-Source': 'useProcessGroups-override',
      },
      successCallback: handleProcessGroupResponse,
      failureCallback: (error: any) => {
        console.error('[m8 Extension] Process Groups API Error:', error);
        setLoading(false);
      },
    });

    // return required for Tanstack query
    return true;
  };

  useQuery({
    queryKey: [path, processInfo, tenantId],
    queryFn: () => getProcessGroups(),
  });

  return {
    processGroups,
    loading,
  };
}
