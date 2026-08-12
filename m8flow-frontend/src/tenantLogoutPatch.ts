/**
 * Clears tenant selection artifacts when UserService.doLogout runs so the next
 * visit re-enters tenant selection instead of a stale org cookie/storage.
 */
import UserService from './services/UserService';
import { GLOBAL_TENANT_STORAGE_KEY } from './contexts/GlobalTenantContext';
import { M8FLOW_TENANT_STORAGE_KEY } from './views/TenantSelectPage';

const TENANT_LOCAL_KEYS = [
  M8FLOW_TENANT_STORAGE_KEY,
  'm8f_tenant_id',
  GLOBAL_TENANT_STORAGE_KEY,
] as const;

const TENANT_COOKIE_CLEAR = 'm8flow_selected_tenant=; Max-Age=0; Path=/';

const previousDoLogout = UserService.doLogout;

function wipeTenantClientState(): void {
  if (typeof window === 'undefined') {
    return;
  }
  for (const storageKey of TENANT_LOCAL_KEYS) {
    localStorage.removeItem(storageKey);
  }
  document.cookie = TENANT_COOKIE_CLEAR;
}

UserService.doLogout = () => {
  wipeTenantClientState();
  previousDoLogout();
};
