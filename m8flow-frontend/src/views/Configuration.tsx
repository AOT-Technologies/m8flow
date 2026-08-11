/**
 * m8flow Configuration section.
 *
 * Renders the configuration tab bar and its routed panels. Secrets is the only
 * built-in tab; extensions may contribute further tabs by declaring a
 * `configuration_tab_item` UX element.
 *
 * The active tab is derived from the current path rather than tracked in state,
 * so browser navigation and deep links stay in sync without an effect.
 */
import { useEffect, useMemo } from 'react';
import { Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tab, Tabs } from '@mui/material';

import { usePermissionFetcher } from '../hooks/PermissionService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import { setPageTitle } from '../helpers';
import { PermissionsToCheck } from '../interfaces';
import { UiSchemaUxElement } from '../extension_ui_schema_interfaces';
import ExtensionUxElementForDisplay from '../components/ExtensionUxElementForDisplay';
import Extension from './Extension';
import SecretList from './SecretList';
import SecretNew from './SecretNew';
import SecretShow from './SecretShow';

const BASE_PATH = '/configuration';
const EXTENSION_PREFIX = `${BASE_PATH}/extension`;

type OwnProps = {
  extensionUxElements?: UiSchemaUxElement[] | null;
};

/** Paths that should light up an extension's tab: its own page, plus any it claims. */
function highlightPathsFor(element: UiSchemaUxElement): string[] {
  const claimed = element.location_specific_configs?.highlight_on_tabs;
  const pages = claimed?.length ? claimed : [element.page];
  return pages.map((page: string) => `${EXTENSION_PREFIX}${page}`);
}

export default function Configuration({ extensionUxElements }: OwnProps) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const { targetUris } = useUriListForPermissions();
  const permissionsToCheck: PermissionsToCheck = {
    [targetUris.secretListPath]: ['GET'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(permissionsToCheck);

  useEffect(() => {
    setPageTitle([t('configuration')]);
  }, [t]);

  const canViewSecrets = ability.can('GET', targetUris.secretListPath);
  const extensions = extensionUxElements ?? [];

  // Tab 0 is Secrets when visible; extension tabs follow in declaration order.
  const activeTab = useMemo(() => {
    const extensionIndex = extensions.findIndex((element) =>
      highlightPathsFor(element).includes(pathname),
    );
    if (extensionIndex === -1) {
      return 0;
    }
    return extensionIndex + (canViewSecrets ? 1 : 0);
  }, [pathname, extensions, canViewSecrets]);

  if (!permissionsLoaded) {
    return null;
  }

  const renderExtensionTab = (
    element: UiSchemaUxElement,
    index: number,
  ) => (
    <Tab
      key={`${element.page}-${index}`}
      label={element.label}
      onClick={() => navigate(`${EXTENSION_PREFIX}${element.page}`)}
    />
  );

  return (
    <>
      <Tabs value={activeTab}>
        {canViewSecrets && (
          <Tab
            label={t('secrets')}
            data-testid="configuration-tab-secrets"
            onClick={() => navigate(`${BASE_PATH}/secrets`)}
          />
        )}
        <ExtensionUxElementForDisplay
          displayLocation="configuration_tab_item"
          elementCallback={renderExtensionTab}
          extensionUxElements={extensionUxElements}
        />
      </Tabs>
      <br />
      <Routes>
        <Route path="/" element={<SecretList />} />
        <Route path="secrets" element={<SecretList />} />
        <Route path="secrets/new" element={<SecretNew />} />
        <Route path="secrets/:secret_identifier" element={<SecretShow />} />
        <Route
          path="extension/:page_identifier"
          element={<Extension displayErrors={false} />}
        />
      </Routes>
    </>
  );
}
