/**
 * Configuration section — secrets + extension tabs; active tab from path.
 */
import { useEffect, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tab, Tabs } from '@mui/material';

import ExtensionUxElementForDisplay from '../components/ExtensionUxElementForDisplay';
import { setPageTitle } from '../helpers';
import { usePermissionFetcher } from '../hooks/PermissionService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import type { PermissionsToCheck } from '../interfaces';
import type { UiSchemaUxElement } from '../extension_ui_schema_interfaces';
import { ConfigurationRoutes } from './configurationRoutes';

const ROOT = '/configuration';
const EXT = `${ROOT}/extension`;

function pathsForExtensionTab(el: UiSchemaUxElement): string[] {
  const claimed = el.location_specific_configs?.highlight_on_tabs;
  const pages = claimed?.length ? claimed : [el.page];
  return pages.map((page: string) => `${EXT}${page}`);
}

export default function Configuration({
  extensionUxElements,
}: {
  extensionUxElements?: UiSchemaUxElement[] | null;
}) {
  const { pathname } = useLocation();
  const go = useNavigate();
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const secretsUri = targetUris.secretListPath;

  const { ability, permissionsLoaded } = usePermissionFetcher({
    [secretsUri]: ['GET'],
  } as PermissionsToCheck);

  useEffect(() => {
    setPageTitle([t('configuration')]);
  }, [t]);

  const secretsOk = ability.can('GET', secretsUri);
  const extensions = extensionUxElements ?? [];

  const tabIndex = useMemo(() => {
    const hit = extensions.findIndex((el) =>
      pathsForExtensionTab(el).includes(pathname),
    );
    if (hit < 0) return 0;
    return hit + (secretsOk ? 1 : 0);
  }, [pathname, extensions, secretsOk]);

  if (!permissionsLoaded) return null;

  return (
    <>
      <Tabs value={tabIndex}>
        {secretsOk ? (
          <Tab
            label={t('secrets')}
            data-testid="configuration-tab-secrets"
            onClick={() => go(`${ROOT}/secrets`)}
          />
        ) : null}
        <ExtensionUxElementForDisplay
          displayLocation="configuration_tab_item"
          extensionUxElements={extensionUxElements}
          elementCallback={(el: UiSchemaUxElement, i: number) => (
            <Tab
              key={`${el.page}-${i}`}
              label={el.label}
              onClick={() => go(`${EXT}${el.page}`)}
            />
          )}
        />
      </Tabs>
      <br />
      <ConfigurationRoutes />
    </>
  );
}
