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

  const confirmDelete = (key: string) => {
    HttpService.makeCallToBackend({
      path: `/secrets/${key}`,
      httpMethod: 'DELETE',
      successCallback: () => window.location.reload(),
    });
  };

  if (!permissionsLoaded || !loaded) {
    return null;
  }

  const { page, perPage } = getPageInfoFromSearchParams(searchParams);

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
