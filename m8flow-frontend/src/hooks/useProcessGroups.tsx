/**
 * Process-group / runnable-model fetch — SA tenant filter + extension headers.
 *
 * When `tenantId` is omitted, super-admins inherit the GlobalTenant selection so
 * upstream callers (e.g. ProcessModelTreePage via `@spiff-core`) stay scoped.
 */
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { ProcessGroup, ProcessGroupLite } from '../interfaces';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';
import UserService from '../services/UserService';
import { registerProcessTenantLabels } from '../views/StartProcess/processTenantLabelRegistry';

type Result = {
  processGroups: ProcessGroup[] | ProcessGroupLite[] | null;
  loading: boolean;
};

function buildListUrl(runnableOnly: boolean, tenantId?: string | null) {
  const base = runnableOnly
    ? '/process-models?filter_runnable_by_user=true&recursive=true&group_by_process_group=True&per_page=2000'
    : '/process-groups';
  if (!tenantId) return base;
  const join = base.includes('?') ? '&' : '?';
  return `${base}${join}tenantId=${encodeURIComponent(tenantId)}`;
}

export default function useProcessGroups({
  processInfo,
  getRunnableProcessModels = false,
  tenantId,
}: {
  processInfo: Record<string, any>;
  getRunnableProcessModels?: boolean;
  tenantId?: string | null;
}) {
  const { selectedTenantId } = useGlobalTenant();
  const effectiveTenantId =
    tenantId !== undefined
      ? tenantId
      : UserService.isSuperAdmin()
        ? selectedTenantId
        : null;

  const [result, setResult] = useState<Result>({
    processGroups: null,
    loading: false,
  });
  const url = buildListUrl(getRunnableProcessModels, effectiveTenantId);

  useQuery({
    queryKey: [url, processInfo, effectiveTenantId],
    queryFn: async () => {
      setResult((prev) => ({ ...prev, loading: true }));
      HttpService.makeCallToBackend({
        path: url,
        httpMethod: 'GET',
        extraHeaders: {
          'X-m8-Extension': 'true',
          'X-m8-Request-Source': 'useProcessGroups-override',
        },
        successCallback: (payload: any) => {
          registerProcessTenantLabels(payload.results);
          setResult({ processGroups: payload.results, loading: false });
        },
        failureCallback: (err: any) => {
          console.error('[m8 Extension] Process Groups API Error:', err);
          setResult((prev) => ({ ...prev, loading: false }));
        },
      });
      return true;
    },
  });

  return { processGroups: result.processGroups, loading: result.loading };
}
