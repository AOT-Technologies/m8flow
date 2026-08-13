/**
 * Column descriptors and cell renderers for the messages list.
 * Kept out of MessageInstanceList.tsx - merging them trips the upstream
 * duplicate-code gate.
 */
import type { ReactNode } from 'react';
import { ErrorOutline } from '@mui/icons-material';
import { Button, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import { TFunction } from 'i18next';

import {
  modifyProcessIdentifierForPathParam,
} from '../../helpers';
import DateAndTimeService from '../../services/DateAndTimeService';
import { FormatProcessModelDisplayName } from '../MiniComponents';
import SpiffTooltip from '../SpiffTooltip';
import { MessageInstance } from '../../interfaces';

export type MessageRow = MessageInstance & {
  tenantName?: string;
  tenantId?: string;
};

export type MessageColumn = {
  id: string;
  title: string;
  cell: (row: MessageRow) => ReactNode;
};

function instanceHref(row: MessageRow): string {
  return `/process-instances/${modifyProcessIdentifierForPathParam(
    row.process_model_identifier,
  )}/${row.process_instance_id}`;
}

export function buildMessageColumns(opts: {
  t: TFunction;
  showTenant: boolean;
  onOpenDetail: (row: MessageRow) => void;
}): MessageColumn[] {
  const { t, showTenant, onOpenDetail } = opts;
  const cols: MessageColumn[] = [
    { id: 'id', title: t('message_id'), cell: (r) => r.id },
  ];

  if (showTenant) {
    cols.push({
      id: 'tenant',
      title: t('tenant'),
      cell: (r) => (
        <Typography variant="body2" data-testid="message-list-tenant-cell">
          {r.tenantName || r.tenantId || '-'}
        </Typography>
      ),
    });
  }

  cols.push(
    {
      id: 'model',
      title: t('process_label'),
      cell: (r) =>
        r.process_instance_id == null ? (
          <span>{t('external_call_label')}</span>
        ) : (
          FormatProcessModelDisplayName(r)
        ),
    },
    {
      id: 'instance',
      title: t('process_label_instance'),
      cell: (r) =>
        r.process_instance_id == null ? (
          <span />
        ) : (
          <Link data-testid="process-instance-show-link" to={instanceHref(r)}>
            {r.process_instance_id}
          </Link>
        ),
    },
    { id: 'name', title: t('name'), cell: (r) => r.name },
    { id: 'kind', title: t('type'), cell: (r) => r.message_type },
    {
      id: 'peer',
      title: t('corresponding_message_instance'),
      cell: (r) => r.counterpart_id,
    },
    {
      id: 'detail',
      title: t('details_label'),
      cell: (r) => {
        const errored = Boolean(r.failure_cause);
        return (
          <SpiffTooltip title={errored ? t('instance_has_error') : null}>
            <Button variant="text" onClick={() => onOpenDetail(r)}>
              {t('view')}
              {errored ? (
                <>
                  &nbsp;
                  <ErrorOutline style={{ fill: 'red' }} />
                </>
              ) : null}
            </Button>
          </SpiffTooltip>
        );
      },
    },
    { id: 'status', title: t('status'), cell: (r) => r.status },
    {
      id: 'when',
      title: t('created_at_label'),
      cell: (r) =>
        DateAndTimeService.convertSecondsToFormattedDateTime(
          r.created_at_in_seconds,
        ),
    },
  );

  return cols;
}
