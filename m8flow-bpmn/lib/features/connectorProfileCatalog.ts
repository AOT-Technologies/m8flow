/**
 * Active connector profiles for the Service Task Config tab.
 *
 * Same pub-sub shape as `serviceTaskOperatorCatalog`: the panel cannot await,
 * so the first render of a connector family kicks off a load, empty results
 * are cached (so we do not re-request forever), and subscribers re-render
 * when the host answers `m8flow.connector_profiles.returned`.
 */
import { useEffect, useState } from 'preact/hooks';

import type { ConnectorProfileOption } from './connectorProfileBinding';

export const CONNECTOR_PROFILES_REQUESTED = 'm8flow.connector_profiles.requested';
export const CONNECTOR_PROFILES_RETURNED = 'm8flow.connector_profiles.returned';

export type ConnectorProfileCatalogEntry = {
  profiles: ConnectorProfileOption[];
  hiddenFieldIds: string[];
  supportsProfiles: boolean;
};

export type ConnectorProfileCatalogState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; entry: ConnectorProfileCatalogEntry };

export type ConnectorProfileCatalog = {
  getState(connectorType: string): ConnectorProfileCatalogState;
  markLoading(connectorType: string): boolean;
  setLoaded(connectorType: string, entry: unknown): void;
  subscribe(listener: () => void): () => void;
  reset(): void;
};

export type ConnectorProfilesReturnedEvent = {
  connectorType?: string;
  profiles?: unknown;
  hiddenFieldIds?: unknown;
  supportsProfiles?: unknown;
};

function asOptions(profiles: unknown): ConnectorProfileOption[] {
  if (!Array.isArray(profiles)) {
    return [];
  }
  return profiles.flatMap((row) => {
    if (!row || typeof row !== 'object') {
      return [];
    }
    const record = row as { profile_name?: unknown; display_name?: unknown };
    const profileName = typeof record.profile_name === 'string' ? record.profile_name.trim() : '';
    if (!profileName) {
      return [];
    }
    const displayName =
      typeof record.display_name === 'string' && record.display_name.trim()
        ? record.display_name
        : profileName;
    return [{ profile_name: profileName, display_name: displayName }];
  });
}

function normalizeEntry(entry: unknown): ConnectorProfileCatalogEntry {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return { profiles: [], hiddenFieldIds: [], supportsProfiles: false };
  }
  const record = entry as ConnectorProfilesReturnedEvent;
  const hidden = Array.isArray(record.hiddenFieldIds)
    ? record.hiddenFieldIds.filter((id): id is string => typeof id === 'string' && id.length > 0)
    : [];
  return {
    profiles: asOptions(record.profiles),
    hiddenFieldIds: hidden,
    supportsProfiles: record.supportsProfiles === true,
  };
}

export function createConnectorProfileCatalog(): ConnectorProfileCatalog {
  const stateByType = new Map<string, ConnectorProfileCatalogState>();
  const listeners = new Set<() => void>();

  const notify = () => {
    listeners.forEach((listener) => listener());
  };

  return {
    getState(connectorType) {
      return stateByType.get(connectorType) ?? { status: 'idle' };
    },
    markLoading(connectorType) {
      if (!connectorType) {
        return false;
      }
      const current = stateByType.get(connectorType);
      if (current && current.status !== 'idle') {
        return false;
      }
      stateByType.set(connectorType, { status: 'loading' });
      notify();
      return true;
    },
    setLoaded(connectorType, entry) {
      if (!connectorType) {
        return;
      }
      stateByType.set(connectorType, { status: 'loaded', entry: normalizeEntry(entry) });
      notify();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    reset() {
      stateByType.clear();
      notify();
    },
  };
}

export const connectorProfileCatalog = createConnectorProfileCatalog();

export function useConnectorProfileCatalog(
  connectorType: string,
  catalog: ConnectorProfileCatalog = connectorProfileCatalog,
): ConnectorProfileCatalogState {
  const [, forceUpdate] = useState(0);
  useEffect(() => catalog.subscribe(() => forceUpdate((n) => n + 1)), [catalog]);
  return catalog.getState(connectorType);
}
