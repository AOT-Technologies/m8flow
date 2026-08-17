// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.

/**
 * Override: process-instance list tab bar.
 *
 * m8flow hides the "for me" tab for super-admins and for any user who can list
 * tenants, since a cross-tenant operator has no personal task list worth
 * showing; those users are redirected to the "all" tab.
 *
 * Tabs are declared as data and then filtered by permission, so the MUI tab
 * index is always the position within the *visible* set. Deriving the index
 * from the visible list rather than from `variant` alone keeps the highlight
 * correct when a permission check removes a tab ahead of the active one.
 */

import { useEffect } from 'react';
import { Tabs, Tab } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { usePermissionFetcher } from '../hooks/PermissionService';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '../interfaces';
import UserService from '../services/UserService';
import SpiffTooltip from './SpiffTooltip';

type OwnProps = {
  variant: string;
};

export default function ProcessInstanceListTabs({ variant }: OwnProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.processInstanceListPath]: ['GET'],
    [targetUris.processInstanceListForMePath]: ['POST'],
    [targetUris.m8flowTenantListPath]: ['GET'],
  };
  const { ability, permissionsLoaded } =
    usePermissionFetcher(permissionRequestData);

  const isCrossTenantOperator =
    UserService.isSuperAdmin() ||
    (permissionsLoaded && ability.can('GET', targetUris.m8flowTenantListPath));

  useEffect(() => {
    if (isCrossTenantOperator && variant === 'for-me') {
      navigate('/process-instances/all', { replace: true });
    }
  }, [isCrossTenantOperator, variant, navigate]);

  const allTabs = [
    {
      variant: 'for-me',
      route: '/process-instances/for-me',
      label: t('for_me'),
      tooltip: t('tooltip_only_show_for_me'),
      testId: 'process-instance-list-for-me',
      visible: !isCrossTenantOperator,
    },
    {
      variant: 'all',
      route: '/process-instances/all',
      label: t('all'),
      tooltip: t('tooltip_show_for_all'),
      testId: 'process-instance-list-all',
      visible: ability.can('GET', targetUris.processInstanceListPath),
    },
    {
      variant: 'find-by-id',
      route: '/process-instances/find-by-id',
      label: t('find_by_id'),
      tooltip: t('tooltip_search_by_id'),
      testId: 'process-instance-list-find-by-id',
      visible: ability.can('POST', targetUris.processInstanceListForMePath),
    },
  ];

  const visibleTabs = allTabs.filter((tab) => tab.visible);
  const activeIndex = Math.max(
    visibleTabs.findIndex((tab) => tab.variant === variant),
    0,
  );

  return (
    <Tabs value={activeIndex} aria-label={t('list_of_tabs')}>
      {visibleTabs.map((tab) => (
        <SpiffTooltip key={tab.variant} title={tab.tooltip}>
          <Tab
            label={tab.label}
            data-testid={tab.testId}
            onClick={() => navigate(tab.route)}
          />
        </SpiffTooltip>
      ))}
    </Tabs>
  );
}
