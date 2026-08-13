// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.

/**
 * Cross-tenant task table for super-admins.
 *
 * A super-admin browses tasks across every tenant to audit and support them,
 * not to work them, so this view differs from the per-tenant task list in two
 * ways: it names the owning tenant on each row, and it offers no "complete
 * task" action, since a super-admin is never a potential owner.
 *
 * The per-tenant view is upstream's TaskTable; see TaskTable.tsx, which routes
 * between the two.
 */

import { useMemo } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  Chip,
} from '@mui/material';
import { AccessTime } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { ProcessInstance, ProcessInstanceTask } from '../interfaces';
import { TimeAgo } from '../helpers/timeago';
import DateAndTimeService from '../services/DateAndTimeService';

type Entry = ProcessInstanceTask | ProcessInstance;

export type TenantTaskTableProps = {
  entries: Entry[] | null;
  showNonActive?: boolean;
};

const INACTIVE_STATUSES = ['complete', 'error'];
const MAX_OWNERS_SHOWN = 2;

/** Process instance id, whichever shape the API returned. */
function instanceIdOf(entry: Entry): string | number | null {
  if ('process_instance_id' in entry) return entry.process_instance_id;
  if ('id' in entry) return entry.id;
  return null;
}

function tenantOf(entry: Entry): string {
  const loose = entry as any;
  return loose.tenantName || loose.tenant_name || '-';
}

function summaryOf(entry: Entry): string | null {
  const loose = entry as any;
  return loose.summary || loose.process_instance_summary || null;
}

/**
 * Who the task is waiting on. A group assignment supersedes the individual
 * candidate list, because that is the party actually accountable for it.
 */
function waitingOn(entry: Entry): { full: string; short: string } | null {
  if (entry.assigned_user_group_identifier) {
    const group = entry.assigned_user_group_identifier;
    return { full: group, short: group };
  }
  if (!entry.potential_owner_usernames) return null;
  const owners = entry.potential_owner_usernames.split(',');
  const shown = owners.slice(0, MAX_OWNERS_SHOWN);
  if (owners.length > MAX_OWNERS_SHOWN) shown.push('...');
  return { full: entry.potential_owner_usernames, short: shown.join(',') };
}

/** Relative age with the absolute timestamp on hover. */
function Timestamp({ seconds }: { seconds: number }) {
  return (
    <Typography
      variant="body2"
      color="textSecondary"
      sx={{ display: 'flex', alignItems: 'center' }}
      title={DateAndTimeService.convertSecondsToFormattedDateTime(seconds) || '-'}
    >
      <AccessTime sx={{ fontSize: 'small', mr: 0.5 }} />
      {TimeAgo.inWords(seconds)}
    </Typography>
  );
}

export default function TenantTaskTable({
  entries,
  showNonActive = false,
}: TenantTaskTableProps) {
  const { t } = useTranslation();

  const visible = useMemo(() => {
    if (!entries) return [];
    if (showNonActive) return entries;
    return entries.filter(
      (entry) =>
        !('status' in entry && INACTIVE_STATUSES.includes(entry.status)),
    );
  }, [entries, showNonActive]);

  if (!entries) return null;

  const headings = [
    t('id'),
    t('tenant'),
    t('task_details'),
    t('created'),
    t('last_milestone'),
    t('last_updated'),
    t('waiting_for'),
  ];

  return (
    <TableContainer
      component={Paper}
      sx={{
        bgcolor: 'background.paper',
        boxShadow: 'none',
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: 'borders.table',
      }}
    >
      <Table>
        <TableHead>
          <TableRow>
            {headings.map((heading) => (
              <TableCell key={heading}>{heading}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {visible.map((entry) => {
            const instanceId = instanceIdOf(entry);
            const waiting = waitingOn(entry);
            const summary = summaryOf(entry);
            return (
              <TableRow
                key={entry.id}
                data-testid={`process-instance-row-${instanceId}`}
              >
                <TableCell>
                  <Typography variant="body2">{instanceId}</Typography>
                </TableCell>
                <TableCell data-testid="task-table-tenant-cell">
                  <Typography variant="body2">{tenantOf(entry)}</Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={entry.process_model_display_name}
                    size="small"
                    sx={{
                      bgcolor: '#E0E0E0',
                      color: '#616161',
                      mb: 1,
                      fontWeight: 'normal',
                    }}
                  />
                  <Typography variant="body2" paragraph>
                    {entry.task_title || entry.task_name}
                  </Typography>
                  {summary ? (
                    <Typography variant="body2" color="primary.main">
                      {summary}
                    </Typography>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Typography variant="body2" paragraph>
                    {entry.process_initiator_username}
                  </Typography>
                  <Timestamp seconds={entry.created_at_in_seconds} />
                </TableCell>
                <TableCell>
                  <Typography
                    variant="body2"
                    sx={{ display: 'flex', alignItems: 'center' }}
                  >
                    {'● '}
                    {entry.last_milestone_bpmn_name}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Timestamp seconds={entry.updated_at_in_seconds} />
                </TableCell>
                <TableCell>
                  {waiting ? (
                    <span title={waiting.full}>{waiting.short}</span>
                  ) : null}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
