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
  const namedValuesUri = '/m8flow/named-values';

  const { ability, permissionsLoaded } = usePermissionFetcher({
    [namedValuesUri]: ['GET'],
  } as PermissionsToCheck);

  useEffect(() => {
    setPageTitle([t('configuration')]);
  }, [t]);

  const namedValuesOk = ability.can('GET', namedValuesUri);
  const extensions = extensionUxElements ?? [];

  const tabIndex = useMemo(() => {
    if (pathname.startsWith(`${ROOT}/named-values`)) {
      return 0;
    }
    if (pathname.startsWith(`${ROOT}/secrets`)) {
      return 0;
    }
    const hit = extensions.findIndex((el) =>
      pathsForExtensionTab(el).includes(pathname),
    );
    if (hit < 0) return 0;
    return hit + (namedValuesOk ? 1 : 0);
  }, [pathname, extensions, namedValuesOk]);

  if (!permissionsLoaded) return null;

  return (
    <>
      <Tabs value={tabIndex}>
        {namedValuesOk ? (
          <Tab
            label="Configuration Variables"
            data-testid="configuration-tab-configuration-variables"
            onClick={() => go(`${ROOT}/named-values`)}
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
