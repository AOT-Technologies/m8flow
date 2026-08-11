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
import HttpService from '../services/HttpService';
import { getPageInfoFromSearchParams } from '../helpers';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import { PermissionsToCheck } from '../interfaces';
import { usePermissionFetcher } from '../hooks/PermissionService';
import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import {
  getSmtpStatus,
  type SmtpStatus,
} from '../services/ExternalFormNotificationService';

export default function SecretList() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [secrets, setSecrets] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [secretToDelete, setSecretToDelete] = useState<any>(null);
  // Null until the SMTP status resolves; stays null if the call fails or the user
  // lacks permission, in which case no banner is shown at all.
  const [smtpStatus, setSmtpStatus] = useState<SmtpStatus | null>(null);
  const { t } = useTranslation();

  const isSuperAdmin = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();

  const { targetUris } = useUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {
    [targetUris.authenticationListPath]: ['GET'],
    [targetUris.secretListPath]: ['GET', 'POST', 'DELETE'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );

  const fetchSecrets = useCallback(() => {
    const setSecretsFromResult = (result: any) => {
      setSecrets(result.results);
      setPagination(result.pagination);
    };
    const { page, perPage } = getPageInfoFromSearchParams(searchParams);
    let path = `/secrets?per_page=${perPage}&page=${page}`;
    if (isSuperAdmin && selectedTenantId) {
      path += `&tenantId=${encodeURIComponent(selectedTenantId)}`;
    }
    HttpService.makeCallToBackend({
      path,
      successCallback: setSecretsFromResult,
    });
  }, [searchParams, isSuperAdmin, selectedTenantId]);

  useEffect(() => {
    if (permissionsLoaded) {
      if (
        !ability.can('GET', targetUris.secretListPath) &&
        ability.can('GET', targetUris.authenticationListPath)
      ) {
        navigate('/configuration/authentications');
      } else {
        fetchSecrets();
      }
    }
  }, [
    permissionsLoaded,
    ability,
    navigate,
    targetUris.authenticationListPath,
    targetUris.secretListPath,
    fetchSecrets,
  ]);

  // External form notification emails silently do nothing until the tenant's NATS_SMTP_*
  // secrets exist, and nothing on this page named those keys. Surface the gap here, where
  // the fix lives. A failure leaves the banner hidden — that covers a 403 for a user who
  // cannot read the status, and the 400 a super admin gets before choosing a tenant.
  //
  // Depends on selectedTenantId: the answer is per-tenant, and the secrets table below
  // already re-fetches on switch, so the banner must not keep the previous verdict.
  useEffect(() => {
    let cancelled = false;
    const tenantId = isSuperAdmin ? selectedTenantId : null;
    setSmtpStatus(null);
    getSmtpStatus(tenantId)
      .then((result) => {
        if (!cancelled) {
          setSmtpStatus(result);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isSuperAdmin, selectedTenantId]);

  const reloadSecrets = (_result: any) => {
    window.location.reload();
  };

  const handleDeleteSecret = (key: any) => {
    HttpService.makeCallToBackend({
      path: `/secrets/${key}`,
      successCallback: reloadSecrets,
      httpMethod: 'DELETE',
    });
  };

  const buildTable = () => {
    const rows = secrets.map((row) => {
      const tenantName = (row as any).tenantName || (row as any).tenantId || '-';
      return (
        <TableRow key={(row as any).key}>
          <TableCell>
            <Link to={`/configuration/secrets/${(row as any).key}`}>
              {(row as any).id}
            </Link>
          </TableCell>
          <TableCell>
            <Link to={`/configuration/secrets/${(row as any).key}`}>
              {(row as any).key}
            </Link>
          </TableCell>
          <TableCell>{(row as any).username}</TableCell>
          {isSuperAdmin && (
            <TableCell data-testid="secret-list-tenant-cell">
              <Typography variant="body2">{tenantName}</Typography>
            </TableCell>
          )}
          <TableCell aria-label="Delete">
            <Can I="DELETE" a={targetUris.secretListPath} ability={ability}>
              <MdDelete onClick={() => setSecretToDelete(row)} />
            </Can>
          </TableCell>
        </TableRow>
      );
    });
    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t('id')}</TableCell>
              <TableCell>{t('secret_key')}</TableCell>
              <TableCell>{t('creator')}</TableCell>
              {isSuperAdmin && <TableCell>{t('tenant')}</TableCell>}
              <TableCell>{t('delete')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>{rows}</TableBody>
        </Table>
      </TableContainer>
    );
  };

  const SecretsDisplayArea = () => {
    // Still loading: render nothing rather than flashing "no secrets to display".
    if (!pagination) {
      return null;
    }
    const { page, perPage } = getPageInfoFromSearchParams(searchParams);
    let displayText = null;
    if (secrets?.length > 0) {
      displayText = (
        <PaginationForTable
          page={page}
          perPage={perPage}
          pagination={pagination as any}
          tableToDisplay={buildTable()}
        />
      );
    } else {
      displayText = <p>{t('no_secrets_to_display')}</p>;
    }
    return displayText;
  };

  const externalFormEmailBanner = () => {
    if (!smtpStatus) {
      return null;
    }
    const keys = smtpStatus.configured
      ? smtpStatus.required_keys
      : smtpStatus.missing_required_keys;
    // "These keys are missing" is wrong when the secret exists but cannot be decrypted —
    // adding it again would not help. Show the backend's specific reason instead.
    const unreadable = smtpStatus.unreadable_keys ?? [];
    const headline =
      unreadable.length > 0 && smtpStatus.reason
        ? smtpStatus.reason
        : (smtpStatus.configured
            ? t('external_form_smtp_configured_hint')
            : t('external_form_smtp_missing_hint'));
    return (
      <Alert
        severity={smtpStatus.configured ? 'info' : 'warning'}
        sx={{ mb: 2 }}
        data-testid={
          smtpStatus.configured
            ? 'external-form-smtp-configured'
            : 'external-form-smtp-not-configured'
        }
        action={
          <Can I="POST" a={targetUris.secretListPath} ability={ability}>
            <Button
              size="small"
              component={Link}
              to="/configuration/external-form-email"
            >
              {t('external_form_email_configure_action')}
            </Button>
          </Can>
        }
      >
        {headline}{' '}
        {keys.map((key) => (
          <Box
            key={key}
            component="code"
            sx={{
              fontFamily: 'monospace',
              bgcolor: 'action.hover',
              px: 0.5,
              mr: 0.5,
              borderRadius: 0.5,
            }}
          >
            {key}
          </Box>
        ))}
      </Alert>
    );
  };

  // The banner must render even before the secrets call resolves — a tenant with no
  // secrets at all is exactly the case that needs the warning most.
  if (permissionsLoaded) {
    return (
      <div>
        {externalFormEmailBanner()}
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
        {SecretsDisplayArea()}
        <Dialog
          open={!!secretToDelete}
          onClose={() => setSecretToDelete(null)}
        >
          <DialogTitle>{t('delete_secret_title')}</DialogTitle>
          <DialogContent>
            <DialogContentText>
              {t('delete_secret_confirm', { name: secretToDelete?.key })}
            </DialogContentText>
            <DialogContentText
              sx={{ color: 'error.main', fontWeight: 500, mt: 1 }}
            >
              {t('action_cannot_be_undone')}
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSecretToDelete(null)}>
              {t('cancel')}
            </Button>
            <Button
              color="error"
              variant="contained"
              onClick={() => {
                handleDeleteSecret(secretToDelete?.key);
                setSecretToDelete(null);
              }}
            >
              {t('delete')}
            </Button>
          </DialogActions>
        </Dialog>
      </div>
    );
  }
  return null;
}
