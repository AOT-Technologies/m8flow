import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Link as RouterLink,
  Navigate,
  useNavigate,
  useParams,
} from 'react-router-dom';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Link,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  StarBorder as StarBorderIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material';
import { Can } from '@casl/react';
import HttpService from '../services/HttpService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { ConnectorNameAvatar } from '../utils/connectorCardDisplay';
import { Notification } from '../components/Notification';
import { type ConnectorConfigField } from '../components/ConnectorOperationsModal';
import { validateConnectorField } from '../utils/connectorFieldValidation';

interface ConnectorTemplate {
  id: string;
  name: string;
  description: string;
  docsUrl?: string;
  supportsProfiles: boolean;
  groups: { id: string; label: string }[];
  profileFields: ConnectorConfigField[];
}

interface ConnectorProfile {
  id: number;
  connector_type: string;
  profile_name: string;
  display_name: string;
  description: string | null;
  config: Record<string, unknown>;
  configured_secrets: string[];
  is_active: boolean;
  is_default: boolean;
}

const callBackend = <T,>(opts: {
  path: string;
  httpMethod?: string;
  postBody?: unknown;
}): Promise<T> =>
  new Promise((resolve, reject) => {
    HttpService.makeCallToBackend({
      path: opts.path,
      httpMethod: opts.httpMethod ?? 'GET',
      postBody: opts.postBody,
      successCallback: resolve as (result: unknown) => void,
      failureCallback: reject,
    });
  });

/** Values the edit dialog holds, keyed by field id. */
type FormValues = Record<string, string | boolean>;

const initialValues = (
  fields: ConnectorConfigField[],
  profile: ConnectorProfile | null,
): FormValues => {
  const values: FormValues = {};
  fields.forEach((field) => {
    if (field.type === 'boolean') {
      const stored = profile ? profile.config[field.id] : field.default;
      values[field.id] = stored === undefined || stored === null ? false : !!stored;
      return;
    }
    if (field.secret) {
      // Stored secrets are never returned by the API; an empty box means
      // "keep what is saved".
      values[field.id] = '';
      return;
    }
    const stored = profile ? profile.config[field.id] : field.default;
    values[field.id] = stored === undefined || stored === null ? '' : String(stored);
  });
  return values;
};

/**
 * Connector profiles.
 *
 * Reached from Connectors -> Configure. A profile is a named credential and
 * configuration set - "smtp-staging", "smtp-production" - that a BPMN service
 * task binds to by name instead of spelling out hosts and passwords.
 *
 * Secret values are write-only: a saved secret shows as "Configured" and is
 * left untouched unless the user types a replacement.
 */
export default function ConnectorConfigure() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { connectorId } = useParams();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.connectorsGroupedPath]: ['GET'],
    [targetUris.connectorProfilesPath]: ['GET', 'POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(permissionRequestData);
  const canManageProfiles = ability.can('POST', targetUris.connectorProfilesPath);

  const [loading, setLoading] = useState(true);
  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [editing, setEditing] = useState<ConnectorProfile | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [profileName, setProfileName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [values, setValues] = useState<FormValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const fields: ConnectorConfigField[] = useMemo(
    () => template?.profileFields ?? [],
    [template],
  );

  useEffect(() => {
    setPageTitle([t('connectors'), connectorId ?? '']);
  }, [t, connectorId]);

  const reloadProfiles = useCallback(() => {
    if (!connectorId) {
      return Promise.resolve();
    }
    return callBackend<ConnectorProfile[]>({
      path: `/m8flow/connector-profiles?connector_type=${encodeURIComponent(connectorId)}`,
    }).then((result) => {
      setProfiles(Array.isArray(result) ? result : []);
    });
  }, [connectorId]);

  useEffect(() => {
    if (!permissionsLoaded || !canManageProfiles || !connectorId) {
      return;
    }
    setLoading(true);
    setLoadError(null);

    callBackend<ConnectorTemplate>({
      path: `/m8flow/connector-templates/${encodeURIComponent(connectorId)}`,
    })
      .then((result) => {
        if (!result || !result.supportsProfiles) {
          // Connectors with nothing to configure (e.g. HTTP) have no profiles.
          setNotFound(true);
          setLoading(false);
          return undefined;
        }
        setTemplate(result);
        return reloadProfiles().then(() => setLoading(false));
      })
      .catch(() => {
        setLoadError(t('connector_config_load_failed'));
        setLoading(false);
      });
  }, [permissionsLoaded, canManageProfiles, connectorId, reloadProfiles, t]);

  const openCreate = () => {
    setEditing(null);
    setProfileName('');
    setDisplayName('');
    setValues(initialValues(fields, null));
    setErrors({});
    setVisibleSecrets({});
    setSaveError(null);
    setDialogOpen(true);
  };

  const openEdit = (profile: ConnectorProfile) => {
    setEditing(profile);
    setProfileName(profile.profile_name);
    setDisplayName(profile.display_name);
    setValues(initialValues(fields, profile));
    setErrors({});
    setVisibleSecrets({});
    setSaveError(null);
    setDialogOpen(true);
  };

  const isConfigured = (field: ConnectorConfigField) =>
    !!editing && editing.configured_secrets.includes(field.id);

  const validateAll = (): Record<string, string> => {
    const found: Record<string, string> = {};
    if (!profileName.trim()) {
      found.__name = t('connector_profile_name_required');
    }
    fields.forEach((field) => {
      if (field.type === 'boolean' || field.type === 'select') {
        return;
      }
      const raw = String(values[field.id] ?? '');
      const error = validateConnectorField(field, raw, isConfigured(field), t);
      if (error) {
        found[field.id] = error;
      }
    });
    return found;
  };

  const handleSave = () => {
    const found = validateAll();
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }

    const config: Record<string, unknown> = {};
    fields.forEach((field) => {
      const value = values[field.id];
      if (field.type === 'boolean') {
        config[field.id] = !!value;
        return;
      }
      const text = String(value ?? '').trim();
      if (field.secret && text === '') {
        // Blank secret means "leave the stored value alone".
        return;
      }
      config[field.id] = text;
    });

    const body = {
      connector_type: connectorId,
      profile_name: profileName.trim(),
      display_name: displayName.trim() || profileName.trim(),
      config,
    };

    setSaving(true);
    setSaveError(null);
    const request = editing
      ? callBackend({
          path: `/m8flow/connector-profiles/${editing.id}`,
          httpMethod: 'PATCH',
          postBody: body,
        })
      : callBackend({
          path: '/m8flow/connector-profiles',
          httpMethod: 'POST',
          postBody: body,
        });

    request
      .then(() => reloadProfiles())
      .then(() => {
        setSaving(false);
        setDialogOpen(false);
        setSuccessMessage(t('connector_profile_saved'));
      })
      .catch((error: any) => {
        setSaving(false);
        setSaveError(error?.message || t('connector_config_save_failed'));
      });
  };

  const handleDelete = (profile: ConnectorProfile) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(t('connector_profile_delete_confirm', { name: profile.display_name }))) {
      return;
    }
    callBackend({
      path: `/m8flow/connector-profiles/${profile.id}`,
      httpMethod: 'DELETE',
    })
      .then(() => reloadProfiles())
      .then(() => setSuccessMessage(t('connector_profile_deleted')))
      .catch(() => setLoadError(t('connector_config_save_failed')));
  };

  const handleSetDefault = (profile: ConnectorProfile) => {
    callBackend({
      path: `/m8flow/connector-profiles/${profile.id}/default`,
      httpMethod: 'POST',
    })
      .then(() => reloadProfiles())
      .catch(() => setLoadError(t('connector_config_save_failed')));
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canManageProfiles) {
    return <Navigate to="/connectors" replace />;
  }

  if (notFound) {
    return <Navigate to="/connectors" replace />;
  }

  const renderField = (field: ConnectorConfigField) => {
    const error = errors[field.id];
    const configured = isConfigured(field);

    if (field.type === 'boolean') {
      return (
        <FormControlLabel
          key={field.id}
          control={
            <Checkbox
              checked={!!values[field.id]}
              onChange={(event) =>
                setValues((prev) => ({ ...prev, [field.id]: event.target.checked }))
              }
            />
          }
          label={field.label}
        />
      );
    }

    const common = {
      fullWidth: true,
      'data-testid': `connector-profile-field-${field.id}`,
      label: field.label,
      required: field.required && !configured,
      value: String(values[field.id] ?? ''),
      error: !!error,
      helperText: error || (configured ? t('connector_config_field_set') : field.helpText),
      onChange: (event: { target: { value: string } }) => {
        const next = event.target.value;
        setValues((prev) => ({ ...prev, [field.id]: next }));
        setErrors((prev) => {
          const { [field.id]: _removed, ...rest } = prev;
          return rest;
        });
      },
    };

    if (field.type === 'select') {
      return (
        <TextField key={field.id} {...common} select>
          {(field.choices ?? []).map((choice) => (
            <MenuItem key={String(choice.value)} value={String(choice.value)}>
              {choice.label}
            </MenuItem>
          ))}
        </TextField>
      );
    }

    if (field.secret) {
      const visible = !!visibleSecrets[field.id];
      return (
        <TextField
          key={field.id}
          {...common}
          type={visible ? 'text' : 'password'}
          placeholder={configured ? t('connector_config_leave_blank_hint') : undefined}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <IconButton
                  aria-label={field.label}
                  edge="end"
                  onClick={() =>
                    setVisibleSecrets((prev) => ({ ...prev, [field.id]: !prev[field.id] }))
                  }
                >
                  {visible ? <VisibilityOffIcon /> : <VisibilityIcon />}
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
      );
    }

    return (
      <TextField
        key={field.id}
        {...common}
        type={field.type === 'number' ? 'number' : 'text'}
      />
    );
  };

  return (
    <Box sx={{ p: 3 }} data-testid="connector-profiles-page">
      {successMessage && (
        <Notification title={successMessage} onClose={() => setSuccessMessage(null)} />
      )}
      <Breadcrumbs aria-label="breadcrumb" sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/connectors" underline="hover" color="primary">
          {t('connectors')}
        </Link>
        <Typography color="text.primary">{template?.name ?? connectorId ?? ''}</Typography>
      </Breadcrumbs>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <ConnectorNameAvatar
          displayName={template?.name ?? connectorId ?? ''}
          pluginKey={connectorId ?? ''}
        />
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          {t('connector_profiles_title')}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Can I="POST" a={targetUris.connectorProfilesPath} ability={ability}>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={openCreate}
            data-testid="connector-profile-add"
          >
            {t('connector_profile_add')}
          </Button>
        </Can>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('connector_profiles_help')}
      </Typography>

      {loadError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Paper variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('connector_profile_name')}</TableCell>
                <TableCell>{t('connector_profile_identifier')}</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {profiles.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                      {t('connector_profiles_empty')}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
              {profiles.map((profile) => (
                <TableRow
                  key={profile.id}
                  hover
                  data-testid={`connector-profile-row-${profile.profile_name}`}
                >
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2">{profile.display_name}</Typography>
                      {profile.is_default && (
                        <Chip size="small" color="primary" label={t('connector_profile_default')} />
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {profile.profile_name}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    {!profile.is_default && (
                      <Tooltip title={t('connector_profile_make_default')}>
                        <IconButton
                          size="small"
                          aria-label={t('connector_profile_make_default')}
                          data-testid={`connector-profile-default-${profile.profile_name}`}
                          onClick={() => handleSetDefault(profile)}
                        >
                          <StarBorderIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                    <Tooltip title={t('edit')}>
                      <IconButton
                        size="small"
                        aria-label={t('edit')}
                        data-testid={`connector-profile-edit-${profile.profile_name}`}
                        onClick={() => openEdit(profile)}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('delete')}>
                      <IconButton
                        size="small"
                        aria-label={t('delete')}
                        data-testid={`connector-profile-delete-${profile.profile_name}`}
                        onClick={() => handleDelete(profile)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Button sx={{ mt: 2 }} onClick={() => navigate('/connectors')}>
        {t('back')}
      </Button>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editing ? t('connector_profile_edit') : t('connector_profile_add')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {saveError && <Alert severity="error">{saveError}</Alert>}
            <TextField
              fullWidth
              required
              data-testid="connector-profile-identifier-input"
              label={t('connector_profile_identifier')}
              value={profileName}
              error={!!errors.__name}
              helperText={errors.__name || t('connector_profile_identifier_help')}
              onChange={(event) => setProfileName(event.target.value)}
            />
            <TextField
              fullWidth
              label={t('connector_profile_name')}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
            {fields.map(renderField)}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('cancel')}</Button>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving}
            data-testid="connector-profile-save"
          >
            {saving ? t('saving') : t('save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
