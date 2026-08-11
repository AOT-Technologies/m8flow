import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, Navigate, useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { Notification } from '../components/Notification';
import SecretFieldsForm from '../components/SecretFieldsForm';
import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import {
  clearSmtpStatusCache,
  getSmtpStatus,
  listNotifications,
  resendNotification,
  type ExternalFormNotification,
  type SmtpStatus,
} from '../services/ExternalFormNotificationService';

/** Statuses whose notification never reached the recipient. */
const PROBLEM_STATUSES = new Set(['smtp_unconfigured', 'failed']);

const statusChipColor = (status: string): 'success' | 'error' | 'warning' | 'default' => {
  if (status === 'submitted' || status === 'completed' || status === 'notified') {
    return 'success';
  }
  if (PROBLEM_STATUSES.has(status)) {
    return 'error';
  }
  if (status === 'pending') {
    return 'warning';
  }
  return 'default';
};

/**
 * Configure the SMTP credentials the external-form notification worker uses, and see what
 * happened to recent notifications.
 *
 * These are the NATS_SMTP_* tenant secrets — deliberately separate from the SMTP_* secrets
 * the BPMN smtp connector reads, so the two email paths can be configured independently.
 * Before this page existed the keys had to be typed by hand into Configuration > Secrets,
 * with no way to tell whether the worker could actually send.
 *
 * Reached from the warning banner on the Secrets page. Gated on secret write permission,
 * matching ConnectorConfigure: it exists only to create/update secrets.
 */
export default function ExternalFormEmailConfigure() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { targetUris } = useUriListForPermissions();
  // Super admins are exempt from backend tenant scoping, so every call here has to name
  // the tenant they are currently viewing. Everyone else is scoped server-side.
  const isSuperAdmin = UserService.isSuperAdmin();
  const { selectedTenantId } = useGlobalTenant();
  const tenantId = isSuperAdmin ? selectedTenantId : null;

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.secretListPath]: ['GET', 'POST'],
    [targetUris.m8flowExternalFormNotificationsPath]: ['GET'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(permissionRequestData);
  const canManageSecrets = ability.can('POST', targetUris.secretListPath);
  const canReadNotifications = ability.can(
    'GET',
    targetUris.m8flowExternalFormNotificationsPath,
  );

  const [status, setStatus] = useState<SmtpStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [notifications, setNotifications] = useState<ExternalFormNotification[] | null>(
    null,
  );
  const [showSuccess, setShowSuccess] = useState(false);
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);

  useEffect(() => {
    setPageTitle([t('configuration'), t('external_form_email_title')]);
  }, [t]);

  const loadStatus = useCallback(() => {
    getSmtpStatus(tenantId)
      .then((result) => {
        setStatus(result);
        setStatusError(false);
      })
      .catch(() => setStatusError(true));
  }, [tenantId]);

  const loadNotifications = useCallback(() => {
    if (!canReadNotifications) {
      return;
    }
    listNotifications({ perPage: 20, tenantId })
      .then((page) => setNotifications(page.results))
      .catch(() => setNotifications([]));
  }, [canReadNotifications, tenantId]);

  useEffect(() => {
    if (!permissionsLoaded || !canManageSecrets) {
      return;
    }
    loadStatus();
    loadNotifications();
  }, [permissionsLoaded, canManageSecrets, loadStatus, loadNotifications]);

  const handleSaved = () => {
    setShowSuccess(true);
    // The saved secrets change the answer, so the cached verdict for this tenant must
    // not be reused. Other tenants' entries are unaffected.
    clearSmtpStatusCache(tenantId);
    loadStatus();
  };

  const handleResend = (id: number) => {
    setResendingId(id);
    setResendError(null);
    resendNotification(id, tenantId)
      .then(() => {
        setResendingId(null);
        loadNotifications();
      })
      .catch(() => {
        setResendingId(null);
        setResendError(t('external_form_email_resend_failed'));
      });
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canManageSecrets) {
    return <Navigate to="/configuration/secrets" replace />;
  }

  const banner =
    status && !status.configured ? (
      <Alert
        severity="warning"
        sx={{ mb: 2 }}
        data-testid="external-form-email-not-configured"
      >
        {t('external_form_email_missing_secrets')}{' '}
        {status.missing_required_keys.map((key) => (
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
    ) : status?.configured ? (
      <Alert severity="success" sx={{ mb: 2 }} data-testid="external-form-email-configured">
        {t('external_form_email_configured')}
      </Alert>
    ) : null;

  return (
    <Box sx={{ p: 3 }}>
      {showSuccess && (
        <Notification
          title={t('connector_config_saved')}
          onClose={() => setShowSuccess(false)}
        />
      )}
      <Breadcrumbs aria-label="breadcrumb" sx={{ mb: 1 }}>
        <Link
          component={RouterLink}
          to="/configuration/secrets"
          underline="hover"
          color="primary"
        >
          {t('secrets')}
        </Link>
        <Typography color="text.primary">{t('external_form_email_title')}</Typography>
      </Breadcrumbs>

      <Typography variant="h4" sx={{ fontWeight: 700, mt: 2, mb: 1 }}>
        {t('external_form_email_title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {t('external_form_email_subtitle')}
      </Typography>

      {statusError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('connector_config_load_failed')}
        </Alert>
      ) : null}

      {status ? (
        <SecretFieldsForm
          fields={status.fields}
          secretKeyOf={(field) => field.secretKey ?? field.id}
          banner={banner}
          onSaved={handleSaved}
          secondaryAction={
            <Button
              variant="outlined"
              onClick={() => navigate('/configuration/secrets')}
              data-testid="external-form-email-cancel"
            >
              {t('cancel')}
            </Button>
          }
        />
      ) : (
        !statusError && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        )
      )}

      {canReadNotifications && notifications && notifications.length > 0 && (
        <Box sx={{ mt: 5, maxWidth: 960 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
            {t('external_form_email_recent_title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('external_form_email_recent_subtitle')}
          </Typography>
          {resendError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {resendError}
            </Alert>
          )}
          <TableContainer component={Paper} elevation={0} variant="outlined">
            <Table size="small" data-testid="external-form-notification-table">
              <TableHead>
                <TableRow>
                  <TableCell>{t('external_form_email_recipient')}</TableCell>
                  <TableCell>{t('status')}</TableCell>
                  <TableCell>{t('external_form_email_attempts')}</TableCell>
                  <TableCell>{t('external_form_email_last_error')}</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {notifications.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>{row.email}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={row.status}
                        color={statusChipColor(row.status)}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>{row.attempts}</TableCell>
                    <TableCell
                      sx={{ maxWidth: 320, whiteSpace: 'normal', wordBreak: 'break-word' }}
                    >
                      {row.last_error ?? '—'}
                    </TableCell>
                    <TableCell align="right">
                      {PROBLEM_STATUSES.has(row.status) && (
                        <Button
                          size="small"
                          onClick={() => handleResend(row.id)}
                          disabled={resendingId === row.id}
                          data-testid={`external-form-notification-resend-${row.id}`}
                        >
                          {t('external_form_email_resend')}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Stack direction="row" sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {t('external_form_email_resend_hint')}
            </Typography>
          </Stack>
        </Box>
      )}
    </Box>
  );
}
