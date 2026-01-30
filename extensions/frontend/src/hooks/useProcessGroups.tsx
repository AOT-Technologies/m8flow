/**
 * Override: useProcessGroups Hook
 * 
 * This override adds a custom header to the process-groups API call
 * and logs the response to console.
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ProcessGroup, ProcessGroupLite } from '@spiffworkflow-frontend/interfaces';
import HttpService from '../services/HttpService';

export default function useProcessGroups({
  processInfo,
  getRunnableProcessModels = false,
}: {
  processInfo: Record<string, any>;
  getRunnableProcessModels?: boolean;
}) {
  const [processGroups, setProcessGroups] = useState<
    ProcessGroup[] | ProcessGroupLite[] | null
  >(null);
  const [loading, setLoading] = useState(false);

  const handleProcessGroupResponse = (result: any) => {
    setProcessGroups(result.results);
    setLoading(false);
  };

  let path = '/process-groups';
  if (getRunnableProcessModels) {
    path =
      '/process-models?filter_runnable_by_user=true&recursive=true&group_by_process_group=True&per_page=2000';
  }

  const getProcessGroups = async () => {
    setLoading(true);
    
    // Log the API call
    console.log('[m8 Extension] Calling Process Groups API:', path);
    
    HttpService.makeCallToBackend({
      path,
      httpMethod: 'GET',
      // Add custom header to the API call
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
    queryKey: [path, processInfo],
    queryFn: () => getProcessGroups(),
  });

  return {
    processGroups,
    loading,
  };
}
