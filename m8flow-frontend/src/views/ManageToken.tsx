import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  SelectChangeEvent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  DeleteOutline as DeleteOutlineIcon,
  VpnKey as VpnKeyIcon,
  WarningAmberOutlined as WarningAmberOutlinedIcon,
} from '@mui/icons-material';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { useApi } from '../utils/useApi';
import CopyActionButton from '../components/CopyActionButton';

// Expiry options offered in the UI. `days: null` => the key never expires.
// The day values must match the backend's ALLOWED_EXPIRY_DAYS.
const EXPIRY_OPTIONS: { value: string; days: number | null; labelKey: string }[] = [
  { value: '30', days: 30, labelKey: 'manage_token_expiry_30_days' },
  { value: '90', days: 90, labelKey: 'manage_token_expiry_90_days' },
  { value: '365', days: 365, labelKey: 'manage_token_expiry_1_year' },
  { value: 'never', days: null, labelKey: 'manage_token_expiry_never' },
];

type ApiKey = {
  id: string;
  label: string;
  scope?: string | null;
  expiresAtInSeconds?: number | null;
  lastUsedAtInSeconds?: number | null;
  revokedAtInSeconds?: number | null;
  createdAtInSeconds?: number | null;
  createdBy?: string | null;
};

type ApiKeyListResponse = {
  keys?: ApiKey[];
};

function formatEpochSeconds(seconds?: number | null): string | null {
  if (!seconds) {
    return null;
  }
  return new Date(seconds * 1000).toLocaleString();
}

export default function ManageToken() {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { makeCallToBackend, HttpMethods } = useApi();

  const tokenPath = targetUris.m8flowNatsTokensPath;
  const permissionRequestData: PermissionsToCheck = {
    [tokenPath]: ['GET', 'POST', 'DELETE'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canRead = ability.can('GET', tokenPath);
  const canManage = ability.can('POST', tokenPath);
  const canDelete = ability.can('DELETE', tokenPath);

  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [scope, setScope] = useState('');
  const [expiry, setExpiry] = useState<string>('90');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The freshly generated key, shown exactly once. Never re-fetchable.
  const [generatedToken, setGeneratedToken] = useState<string | null>(null);
  const [generatedLabel, setGeneratedLabel] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

  useEffect(() => {
    setPageTitle([t('manage_token')]);
  }, [t]);

  const loadKeys = useCallback(() => {
    setKeysLoading(true);
    makeCallToBackend({
      path: tokenPath,
      httpMethod: HttpMethods.GET,
      successCallback: (result: ApiKeyListResponse) => {
        setKeys(Array.isArray(result?.keys) ? result.keys : []);
        setKeysLoading(false);
      },
      failureCallback: (err: any) => {
        setError(err?.message || t('manage_token_load_error'));
        setKeysLoading(false);
      },
    });
  }, [makeCallToBackend, HttpMethods, tokenPath, t]);

  useEffect(() => {
    if (permissionsLoaded && canRead) {
      loadKeys();
    }
  }, [permissionsLoaded, canRead, loadKeys]);

  const createKey = () => {
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setError(t('manage_token_label_required'));
      return;
    }
    const selected = EXPIRY_OPTIONS.find((option) => option.value === expiry);
    const expiresInDays = selected ? selected.days : null;
    const trimmedScope = scope.trim();

    const postBody: {
      label: string;
      expiresInDays: number | null;
      scope?: string;
    } = { label: trimmedLabel, expiresInDays };
    if (trimmedScope) {
      postBody.scope = trimmedScope;
    }

    setSubmitting(true);
    setError(null);
    makeCallToBackend({
      path: tokenPath,
      httpMethod: HttpMethods.POST,
      postBody,
      successCallback: (result: { token: string; label?: string }) => {
        setGeneratedToken(result.token);
        setGeneratedLabel(result.label || trimmedLabel);
        setLabel('');
        setScope('');
        setExpiry('90');
        setSubmitting(false);
      },
      failureCallback: (err: any) => {
        setError(err?.message || t('manage_token_create_error'));
        setSubmitting(false);
      },
    });
  };

  const revokeKey = (key: ApiKey) => {
    setSubmitting(true);
    setError(null);
    setRevokeTarget(null);
    makeCallToBackend({
      path: `${tokenPath}/${key.id}`,
      httpMethod: HttpMethods.DELETE,
      successCallback: () => {
        setSubmitting(false);
        loadKeys();
      },
      failureCallback: (err: any) => {
        setError(err?.message || t('manage_token_delete_error'));
        setSubmitting(false);
      },
    });
  };

  // Dismiss the one-time key display and refresh the list so the secret is gone.
  const dismissGeneratedToken = () => {
    setGeneratedToken(null);
    setGeneratedLabel(null);
    loadKeys();
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canRead) {
    return <Navigate to="/" replace />;
  }

  const renderCreateForm = () => (
    <Box sx={{ mt: 2.5 }} data-testid="manage-token-create-section">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('manage_token_create_hint')}
      </Typography>
      <Box
        sx={{
          display: 'flex',
          gap: 2,
          flexWrap: 'wrap',
          alignItems: 'flex-start',
        }}
      >
        <TextField
          size="small"
          label={t('manage_token_label_field')}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          sx={{ minWidth: 220 }}
          inputProps={{ 'data-testid': 'manage-token-label-input' }}
        />
        <TextField
          size="small"
          label={t('manage_token_scope_field')}
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          placeholder={t('manage_token_scope_placeholder')}
          helperText={t('manage_token_scope_hint')}
          sx={{ minWidth: 260 }}
          inputProps={{ 'data-testid': 'manage-token-scope-input' }}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="manage-token-expiry-label">
            {t('manage_token_expiry_label')}
          </InputLabel>
          <Select
            labelId="manage-token-expiry-label"
            label={t('manage_token_expiry_label')}
            value={expiry}
            onChange={(event: SelectChangeEvent) => setExpiry(event.target.value)}
            data-testid="manage-token-expiry-select"
          >
            {EXPIRY_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {t(option.labelKey)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button
          variant="contained"
          onClick={createKey}
          disabled={submitting || !canManage || !label.trim()}
          data-testid="manage-token-create-button"
          sx={{ mt: 0.25 }}
        >
          {t('manage_token_create_button')}
        </Button>
      </Box>
    </Box>
  );

  const renderKeyList = () => (
    <Box sx={{ mt: 3 }} data-testid="manage-token-list-section">
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        {t('manage_token_keys_title')}
      </Typography>
      {keysLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress />
        </Box>
      ) : keys.length === 0 ? (
        <Alert severity="info" icon={<VpnKeyIcon fontSize="inherit" />}>
          {t('manage_token_no_keys')}
        </Alert>
      ) : (
        <Paper variant="outlined" sx={{ borderRadius: 2, overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('manage_token_col_label')}</TableCell>
                <TableCell>{t('manage_token_col_scope')}</TableCell>
                <TableCell>{t('manage_token_col_created')}</TableCell>
                <TableCell>{t('manage_token_col_expires')}</TableCell>
                <TableCell>{t('manage_token_col_last_used')}</TableCell>
                <TableCell>{t('manage_token_col_status')}</TableCell>
                <TableCell align="right">{t('manage_token_col_actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.map((key) => {
                const revoked = Boolean(key.revokedAtInSeconds);
                return (
                  <TableRow key={key.id} data-testid={`manage-token-row-${key.id}`}>
                    <TableCell>{key.label}</TableCell>
                    <TableCell>{key.scope || t('manage_token_scope_any')}</TableCell>
                    <TableCell>
                      {formatEpochSeconds(key.createdAtInSeconds) || '—'}
                    </TableCell>
                    <TableCell>
                      {formatEpochSeconds(key.expiresAtInSeconds) ||
                        t('manage_token_never_expires_short')}
                    </TableCell>
                    <TableCell>
                      {formatEpochSeconds(key.lastUsedAtInSeconds) ||
                        t('manage_token_last_used_never')}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={revoked ? 'default' : 'success'}
                        label={
                          revoked
                            ? t('manage_token_status_revoked')
                            : t('manage_token_status_active')
                        }
                      />
                    </TableCell>
                    <TableCell align="right">
                      {!revoked && (
                        <Button
                          size="small"
                          color="error"
                          startIcon={<DeleteOutlineIcon />}
                          onClick={() => setRevokeTarget(key)}
                          disabled={submitting || !canDelete}
                          data-testid={`manage-token-revoke-${key.id}`}
                        >
                          {t('manage_token_revoke_button')}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  );

  const renderGeneratedToken = () => (
    <Box sx={{ mt: 2.5 }} data-testid="manage-token-generated-section">
      <Alert
        severity="warning"
        icon={<WarningAmberOutlinedIcon fontSize="inherit" />}
        sx={{ mb: 2 }}
      >
        {t('manage_token_shown_once_warning')}
      </Alert>
      <Paper
        variant="outlined"
        sx={{ p: 2, borderRadius: 2, bgcolor: 'action.hover' }}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', mb: 0.5, fontWeight: 600 }}
        >
          {generatedLabel
            ? t('manage_token_your_key_named', { label: generatedLabel })
            : t('manage_token_your_token')}
        </Typography>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            flexWrap: 'wrap',
          }}
        >
          <Typography
            data-testid="manage-token-value"
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.9375rem',
              flex: 1,
              minWidth: 0,
              overflowX: 'auto',
              whiteSpace: 'nowrap',
              userSelect: 'all',
            }}
          >
            {generatedToken}
          </Typography>
          <CopyActionButton
            value={generatedToken || ''}
            label={t('copy_to_clipboard')}
            testId="manage-token-copy"
            variant="contained"
          />
        </Box>
      </Paper>
      <Box sx={{ mt: 2 }}>
        <Button
          variant="outlined"
          onClick={dismissGeneratedToken}
          data-testid="manage-token-done-button"
        >
          {t('manage_token_done_button')}
        </Button>
      </Box>
    </Box>
  );

  const renderBody = () => {
    if (generatedToken) {
      return renderGeneratedToken();
    }
    return (
      <>
        {canManage && renderCreateForm()}
        {renderKeyList()}
      </>
    );
  };

  return (
    <Box
      sx={{
        p: { xs: 2, md: 3 },
        width: '100%',
        maxWidth: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
      data-testid="manage-token-page"
    >
      <Paper
        elevation={0}
        sx={{
          p: 3,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          maxWidth: '100%',
          boxSizing: 'border-box',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 2,
              bgcolor: 'background.light',
              color: 'primary.main',
              flexShrink: 0,
            }}
          >
            <VpnKeyIcon />
          </Box>
          <Box>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              {t('manage_token')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('manage_token_subtitle')}
            </Typography>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mt: 2.5 }} data-testid="manage-token-error">
            {error}
          </Alert>
        )}

        {renderBody()}
      </Paper>

      <Dialog
        open={Boolean(revokeTarget)}
        onClose={() => setRevokeTarget(null)}
        data-testid="manage-token-revoke-dialog"
      >
        <DialogTitle>{t('manage_token_revoke_confirm_title')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('manage_token_revoke_confirm_body', {
              label: revokeTarget?.label || '',
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setRevokeTarget(null)}
            data-testid="manage-token-revoke-cancel"
          >
            {t('cancel')}
          </Button>
          <Button
            onClick={() => revokeTarget && revokeKey(revokeTarget)}
            color="error"
            variant="contained"
            data-testid="manage-token-revoke-confirm"
          >
            {t('manage_token_revoke_button')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
