/**
 * Tenant-scoped messages list: fetch and column composition.
 *
 * Cell renderers live in messageListColumns.tsx. Keep them there - merging the
 * two back together trips the upstream duplicate-code gate.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  Typography,
} from '@mui/material';
import { useSearchParams } from 'react-router-dom';

import PaginationForTable from '../PaginationForTable';
import ProcessBreadcrumb from '../ProcessBreadcrumb';
import { getPageInfoFromSearchParams } from '../../helpers';
import HttpService from '../../services/HttpService';
import UserService from '../../services/UserService';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import {
  buildMessageColumns,
  type MessageRow,
} from './messageListColumns';

type Props = { processInstanceId?: number };

const PAGE_PARAM_NS = 'message-list';

function messagesApiPath(args: {
  page: number;
  perPage: number;
  processInstanceId?: number;
  tenantFilter?: string;
}): string {
  const qs = new URLSearchParams({
    per_page: String(args.perPage),
    page: String(args.page),
  });
  if (args.processInstanceId != null) {
    qs.set('process_instance_id', String(args.processInstanceId));
  }
  if (args.tenantFilter) {
    qs.set('tenantId', args.tenantFilter);
  }
  return `/messages?${qs.toString()}`;
}

export default function MessageInstanceList({ processInstanceId }: Props) {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const showTenant = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();

  const [rows, setRows] = useState<MessageRow[]>([]);
  const [pageMeta, setPageMeta] = useState<any>(null);
  const [openRow, setOpenRow] = useState<MessageRow | null>(null);

  const pull = useCallback(() => {
    const { page, perPage } = getPageInfoFromSearchParams(
      searchParams,
      undefined,
      undefined,
      PAGE_PARAM_NS,
    );
    HttpService.makeCallToBackend({
      path: messagesApiPath({
        page,
        perPage,
        processInstanceId,
        tenantFilter:
          showTenant && selectedTenantId ? selectedTenantId : undefined,
      }),
      successCallback: (payload: {
        results: MessageRow[];
        pagination: unknown;
      }) => {
        setRows(payload.results);
        setPageMeta(payload.pagination);
      },
    });
  }, [processInstanceId, searchParams, showTenant, selectedTenantId]);

  useEffect(() => {
    pull();
  }, [pull]);

  const columns = useMemo(
    () =>
      buildMessageColumns({
        t,
        showTenant,
        onOpenDetail: setOpenRow,
      }),
    [t, showTenant],
  );

  if (!pageMeta) return null;

  const { page, perPage } = getPageInfoFromSearchParams(
    searchParams,
    undefined,
    undefined,
    PAGE_PARAM_NS,
  );

  const piFromQuery = searchParams.get('process_instance_id');
  const modelFromQuery = searchParams.get('process_model_id') || '';

  return (
    <>
      {piFromQuery ? (
        <ProcessBreadcrumb
          hotCrumbs={[
            [t('process_groups'), '/process-groups'],
            {
              entityToExplode: modelFromQuery,
              entityType: 'process-model-id',
              linkLastItem: true,
            },
            [
              t('process_instance_label', { id: piFromQuery }),
              `/process-instances/${modelFromQuery}/${piFromQuery}`,
            ],
            [t('messages_tab')],
          ]}
        />
      ) : null}

      {openRow ? (
        <Dialog
          open
          onClose={() => setOpenRow(null)}
          aria-labelledby="message-correlation-title"
        >
          <DialogTitle id="message-correlation-title">
            {t('message_title', {
              id: openRow.id,
              name: openRow.name,
              type: openRow.message_type,
            })}
          </DialogTitle>
          <DialogContent>
            {openRow.failure_cause ? (
              <Typography variant="body1" className="failure-string" paragraph>
                {openRow.failure_cause}
              </Typography>
            ) : null}
            <DialogContentText>{t('correlations')}:</DialogContentText>
            <pre>{JSON.stringify(openRow.correlation_keys, null, 2)}</pre>
          </DialogContent>
        </Dialog>
      ) : null}

      <PaginationForTable
        page={page}
        perPage={perPage}
        perPageOptions={[10, 50, 100, 500, 1000]}
        pagination={pageMeta}
        paginationQueryParamPrefix={PAGE_PARAM_NS}
        tableToDisplay={
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  {columns.map((col) => (
                    <TableCell key={col.id}>{col.title}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    {columns.map((col) => (
                      <TableCell key={col.id}>{col.cell(row)}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        }
      />
    </>
  );
}
