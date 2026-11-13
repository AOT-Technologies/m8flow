import { useEffect, useState } from 'react';

import { checkPermissions, processModelActionPath } from '@/lib/api';

export function processModelVersionPermissionRequest(id: string) {
  return {
    [processModelActionPath(id, 'versions')]: ['GET'],
    [processModelActionPath(id, 'publish')]: ['POST'],
    [processModelActionPath(id, 'working-version')]: ['PUT'],
    [processModelActionPath(id, 'start')]: ['POST'],
  };
}

export function useProcessModelVersionPermissions(id: string, tenantId?: string | null, enabled = true) {
  const key = enabled && id ? JSON.stringify([id, tenantId]) : null;
  const [result, setResult] = useState<{ key: string; history: boolean; publish: boolean; restore: boolean; start: boolean }>();
  useEffect(() => {
    if (!key) return;
    let active = true;
    checkPermissions(processModelVersionPermissionRequest(id)).then((permissions) => {
      if (!active) return;
      setResult({
        key,
        history: permissions[processModelActionPath(id, 'versions')]?.GET === true,
        publish: permissions[processModelActionPath(id, 'publish')]?.POST === true,
        restore: permissions[processModelActionPath(id, 'working-version')]?.PUT === true,
        start: permissions[processModelActionPath(id, 'start')]?.POST === true,
      });
    }).catch(() => { if (active) setResult(undefined); });
    return () => { active = false; };
  }, [id, key]);
  return result?.key === key ? result : undefined;
}
