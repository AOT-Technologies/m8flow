// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.

/**
 * Override: task table.
 *
 * m8flow only diverges from the upstream task table in one situation — a
 * super-admin viewing the list as a table, who needs the owning tenant on each
 * row and must not be offered a "complete task" action. That case is served by
 * TenantTaskTable; every other case delegates to upstream unchanged.
 *
 * Tile mode is deliberately not branched: it renders TaskCard, which is
 * tenant-agnostic and gates its own action on ownership, so a super-admin sees
 * the same tiles as anyone else.
 *
 * Upstream is reached through `@spiff-core` so this override is not resolved
 * back onto itself. Its own relative imports still pick up m8flow overrides
 * (see vite-plugin-override-resolver), so delegating does not bypass m8flow's
 * UserService or helpers.
 */

import UpstreamTaskTable from '@spiff-core/components/TaskTable';
import { ProcessInstance, ProcessInstanceTask } from '../interfaces';
import UserService from '../services/UserService';
import TenantTaskTable from './TenantTaskTable';

type TaskTableProps = {
  entries: ProcessInstanceTask[] | ProcessInstance[] | null;
  viewMode?: string;
  showNonActive?: boolean;
};

export default function TaskTable({
  entries,
  viewMode = 'table',
  showNonActive = false,
}: TaskTableProps) {
  if (viewMode === 'table' && UserService.isSuperAdmin()) {
    return <TenantTaskTable entries={entries} showNonActive={showNonActive} />;
  }
  return (
    <UpstreamTaskTable
      entries={entries}
      viewMode={viewMode}
      showNonActive={showNonActive}
    />
  );
}
