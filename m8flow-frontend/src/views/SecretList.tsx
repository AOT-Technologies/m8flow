/**
 * Secrets index — clean-room. Super-admin gets tenantId query + tenant column.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { MdDelete } from 'react-icons/md';
import { Can } from '@casl/react';

import PaginationForTable from '../components/PaginationForTable';
import { getPageInfoFromSearchParams } from '../helpers';
import { usePermissionFetcher } from '../hooks/PermissionService';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';
import UserService from '../services/UserService';
import {
  clearSmtpStatusCache,
  getSmtpStatus,
  type SmtpStatus,
} from '../services/ExternalFormNotificationService';
import type { PermissionsToCheck } from '../interfaces';

type SecretRow = {
  id: string | number;
  key: string;
  username?: string;
  tenantName?: string;
  tenantId?: string;
};

function getErrorMessage(error: any, fallback: string): string {
  if (typeof error?.detail === 'string' && error.detail) {
    return error.detail;
  }
  if (typeof error?.message === 'string' && error.message) {
    return error.message;
  }
  return fallback;
}

function secretsListPath(page: number, perPage: number, tenantId?: string | null) {
  const qs = new URLSearchParams({
    per_page: String(perPage),
    page: String(page),
  });
  if (tenantId) qs.set('tenantId', tenantId);
  return `/secrets?${qs.toString()}`;
}

function tenantLabel(row: SecretRow): string {
  return row.tenantName || row.tenantId || '-';
}

export default function SecretList() {
  const { t } = useTranslation();
  const go = useNavigate();
  const [searchParams] = useSearchParams();

  const sa = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();
  const { targetUris } = useUriListForPermissions();

  const [rows, setRows] = useState<SecretRow[]>([]);
  const [pageMeta, setPageMeta] = useState<any>(null);
  const [pendingDelete, setPendingDelete] = useState<SecretRow | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  // Null until the SMTP status resolves; stays null if the call fails or the user lacks
  // permission, in which case no banner is shown at all.
  const [smtpStatus, setSmtpStatus] = useState<SmtpStatus | null>(null);

  const { ability, permissionsLoaded } = usePermissionFetcher({
    [targetUris.authenticationListPath]: ['GET'],
    [targetUris.secretListPath]: ['GET', 'POST', 'DELETE'],
  } as PermissionsToCheck);

  const load = useCallback(() => {
    const { page, perPage } = getPageInfoFromSearchParams(searchParams);
    HttpService.makeCallToBackend({
      path: secretsListPath(
        page,
        perPage,
        sa ? selectedTenantId : null,
      ),
      successCallback: (payload: any) => {
        setRows(payload.results ?? []);
        setPageMeta(payload.pagination);
        setErrorMessage('');
        setLoaded(true);
      },
      failureCallback: (error: unknown) => {
        setRows([]);
        setPageMeta(null);
        setErrorMessage(
          getErrorMessage(error, 'Could not list secrets.'),
        );
        setLoaded(true);
      },
    });
  }, [searchParams, sa, selectedTenantId, t]);

  useEffect(() => {
    if (!permissionsLoaded) return;
    const canSecrets = ability.can('GET', targetUris.secretListPath);
    const canAuth = ability.can('GET', targetUris.authenticationListPath);
    if (!canSecrets && canAuth) {
      go('/configuration/authentications');
      return;
    }
    setLoaded(false);
    load();
  }, [
    permissionsLoaded,
    ability,
    go,
    targetUris.authenticationListPath,
    targetUris.secretListPath,
    load,
  ]);

  // External form notification emails silently do nothing until the tenant's NATS_SMTP_*
  // secrets exist, and nothing else on this page names those keys. Surface the gap here,
  // where the fix lives. A failure leaves the banner hidden — that covers a 403 for a user
  // who cannot read the status, and the 400 a super admin gets before choosing a tenant.
  //
  // Depends on selectedTenantId: the answer is per-tenant, and the table below already
  // re-fetches on switch, so the banner must not keep the previous tenant's verdict.
  // Force a fresh fetch each time SecretList mounts or the tenant changes so that newly
  // added or updated SMTP secrets are reflected immediately without needing a browser reload.
  useEffect(() => {
    let cancelled = false;
    const tenantId = sa ? selectedTenantId : null;
    setSmtpStatus(null);
    clearSmtpStatusCache(tenantId);
    getSmtpStatus(tenantId, { force: true })
      .then((result) => {
        if (!cancelled) setSmtpStatus(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sa, selectedTenantId]);

  const confirmDelete = (key: string) => {
    HttpService.makeCallToBackend({
      path: `/secrets/${key}`,
      httpMethod: 'DELETE',
      successCallback: () => {
        clearSmtpStatusCache(sa ? selectedTenantId : null);
        window.location.reload();
      },
    });
  };

  if (!permissionsLoaded || !loaded) {
    return null;
  }

  const { page, perPage } = getPageInfoFromSearchParams(searchParams);

  const externalFormEmailBanner = () => {
    if (!smtpStatus) return null;
    const keys = smtpStatus.configured
      ? smtpStatus.required_keys
      : smtpStatus.missing_required_keys;
    // "These keys are missing" is wrong when the secret exists but cannot be decrypted —
    // adding it again would not help. Show the backend's specific reason instead.
    const unreadable = smtpStatus.unreadable_keys ?? [];
    const headline =
      unreadable.length > 0 && smtpStatus.reason
        ? smtpStatus.reason
        : smtpStatus.configured
          ? t('external_form_smtp_configured_hint')
          : t('external_form_smtp_missing_hint');
    return (
      <Alert
        severity={smtpStatus.configured ? 'info' : 'warning'}
        sx={{ mb: 2 }}
        data-testid={
          smtpStatus.configured
            ? 'external-form-smtp-configured'
            : 'external-form-smtp-not-configured'
        }
      >
        {headline}{' '}
        {keys.map((key) => (
          <Box
            key={key}
            component="code"
            sx={{ fontFamily: 'monospace', mr: 1, whiteSpace: 'nowrap' }}
          >
            {key}
          </Box>
        ))}
      </Alert>
    );
  };

  const table = (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{t('id')}</TableCell>
            <TableCell>{t('secret_key')}</TableCell>
            <TableCell>{t('creator')}</TableCell>
            {sa ? <TableCell>{t('tenant')}</TableCell> : null}
            <TableCell>{t('delete')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell>
                <Link to={`/configuration/secrets/${row.key}`}>{row.id}</Link>
              </TableCell>
              <TableCell>
                <Link to={`/configuration/secrets/${row.key}`}>{row.key}</Link>
              </TableCell>
              <TableCell>{row.username}</TableCell>
              {sa ? (
                <TableCell data-testid="secret-list-tenant-cell">
                  <Typography variant="body2">{tenantLabel(row)}</Typography>
                </TableCell>
              ) : null}
              <TableCell aria-label="Delete">
                <Can I="DELETE" a={targetUris.secretListPath} ability={ability}>
                  <MdDelete onClick={() => setPendingDelete(row)} />
                </Can>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  return (
    <div>
      <Box
        sx={{
          display: 'flex',
          alignItems: { xs: 'flex-start', sm: 'center' },
          justifyContent: 'space-between',
          gap: 2,
          flexDirection: { xs: 'column', sm: 'row' },
          mb: 2,
        }}
      >
        <Typography variant="h1">{t('secrets')}</Typography>
        <Can I="POST" a={targetUris.secretListPath} ability={ability}>
          <Button
            component={Link}
            variant="contained"
            to="/configuration/secrets/new"
          >
            {t('add_a_secret')}
          </Button>
        </Can>
      </Box>

      {externalFormEmailBanner()}

      {rows.length > 0 ? (
        <PaginationForTable
          page={page}
          perPage={perPage}
          pagination={pageMeta}
          tableToDisplay={table}
        />
      ) : errorMessage ? (
        <Alert severity="error" data-testid="secret-list-error">
          {errorMessage}
        </Alert>
      ) : (
        <p>{t('no_secrets_to_display')}</p>
      )}

      <Dialog open={!!pendingDelete} onClose={() => setPendingDelete(null)}>
        <DialogTitle>{t('delete_secret_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('delete_secret_confirm', { name: pendingDelete?.key })}
          </DialogContentText>
          <DialogContentText
            sx={{ color: 'error.main', fontWeight: 500, mt: 1 }}
          >
            {t('action_cannot_be_undone')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDelete(null)}>{t('cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              if (pendingDelete?.key) confirmDelete(pendingDelete.key);
              setPendingDelete(null);
            }}
          >
            {t('delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
