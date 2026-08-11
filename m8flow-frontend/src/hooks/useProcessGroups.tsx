// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.

/**
 * Override: useProcessGroups Hook
 *
 * Adds custom headers and forwards an optional ``tenantId`` query parameter so
 * a super-admin can narrow the cross-tenant process-group / process-model
 * listing to a single tenant.
 *
 * Results and in-flight status are held in one state object: they are always
 * written together, so splitting them would allow a render where the list has
 * arrived but loading is still true.
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ProcessGroup, ProcessGroupLite } from '@spiffworkflow-frontend/interfaces';
import HttpService from '../services/HttpService';

type FetchState = {
  processGroups: ProcessGroup[] | ProcessGroupLite[] | null;
  loading: boolean;
};

export default function useProcessGroups({
  processInfo,
  getRunnableProcessModels = false,
  tenantId = null,
}: {
  processInfo: Record<string, any>;
  getRunnableProcessModels?: boolean;
  tenantId?: string | null;
}) {
  const [state, setState] = useState<FetchState>({
    processGroups: null,
    loading: false,
  });

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
    setState((prev) => ({ ...prev, loading: true }));

    HttpService.makeCallToBackend({
      path,
      httpMethod: 'GET',
      extraHeaders: {
        'X-m8-Extension': 'true',
        'X-m8-Request-Source': 'useProcessGroups-override',
      },
      successCallback: (result: any) =>
        setState({ processGroups: result.results, loading: false }),
      failureCallback: (error: any) => {
        console.error('[m8 Extension] Process Groups API Error:', error);
        setState((prev) => ({ ...prev, loading: false }));
      },
    });

    // Tanstack query requires a resolved value; the data itself arrives via the
    // HttpService callbacks above, so the query is used only for scheduling.
    return true;
  };

  useQuery({
    queryKey: [path, processInfo, tenantId],
    queryFn: () => getProcessGroups(),
  });

  return { processGroups: state.processGroups, loading: state.loading };
}
