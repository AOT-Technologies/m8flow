import { useEffect, useMemo, useState } from 'react';
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
  Chip,
  CircularProgress,
  IconButton,
  InputAdornment,
  Link,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
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
import {
  type ConnectorConfigField,
  type ConnectorGroup,
} from '../components/ConnectorOperationsModal';

interface FieldState {
  /** Current input value. Empty means "leave unchanged" when the secret already exists. */
  value: string;
  /** Whether a secret for this field already exists (write-only: value is never loaded). */
  isSet: boolean;
  /** Validation error message for this field, if any. */
  error?: string;
}

/**
 * Compose the Secret key for a connector config field.
 *
 * Prefers the field's explicit `secretKey` (the canonical name the sample
 * templates reference, e.g. GITHUB_PAT_TOKEN). Falls back to
 * `{connectorId}_{fieldId}` when none is declared. Either way the result uses
 * only word characters (no hyphens): the runtime resolver matches
 * `M8FLOW_SECRET:(?P<name>\w+)` and `\w` excludes "-".
 */
const secretKeyFor = (
  connectorId: string,
  field: ConnectorConfigField,
): string => field.secretKey ?? `${connectorId}_${field.id}`;

const callBackend = (opts: {
  path: string;
  httpMethod: string;
  postBody?: any;
}): Promise<unknown> =>
  new Promise((resolve, reject) => {
    HttpService.makeCallToBackend({
      path: opts.path,
      httpMethod: opts.httpMethod,
      postBody: opts.postBody,
      successCallback: resolve,
      failureCallback: reject,
    });
  });

/**
 * Connector-specific configuration form.
 *
 * Reached via /connectors/:connectorId/configure for connectors that declare
 * `configFields` in the backend connector metadata. Saves/updates each field as
 * a Secret record through the standard /v1.0/secrets endpoints. Connectors with
 * no configurable fields never route here (the Connectors page redirects them to
 * Configuration > Secrets instead).
 *
 * Secret values are write-only by design, so existing values are never pre-filled:
 * a field whose secret already exists is shown as "Configured" and left unchanged
 * unless the user types a new value.
 */
export default function ConnectorConfigure() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { connectorId } = useParams();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.connectorsGroupedPath]: ['GET'],
    [targetUris.secretListPath]: ['GET', 'POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canManageSecrets = ability.can('POST', targetUris.secretListPath);

  const [loading, setLoading] = useState(true);
  const [connector, setConnector] = useState<ConnectorGroup | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fieldStates, setFieldStates] = useState<Record<string, FieldState>>({});
  const [visibleFields, setVisibleFields] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  const configFields: ConnectorConfigField[] = useMemo(
    () => connector?.configFields ?? [],
    [connector],
  );

  useEffect(() => {
    setPageTitle([t('connectors'), connectorId ?? '']);
  }, [t, connectorId]);

  useEffect(() => {
    if (!permissionsLoaded || !canManageSecrets || !connectorId) {
      return;
    }
    setLoading(true);
    setLoadError(null);

    // 1. Load the connector definition (field schema lives here).
    HttpService.makeCallToBackend({
      path: '/m8flow/connectors-grouped',
      successCallback: (result: unknown) => {
        const list = Array.isArray(result) ? (result as ConnectorGroup[]) : [];
        const match = list.find((c) => c.id === connectorId) ?? null;
        if (!match || !match.configFields || match.configFields.length === 0) {
          setNotFound(true);
          setLoading(false);
          return;
        }
        setConnector(match);

        // 2. Determine which fields already have a saved secret (keys only).
        HttpService.makeCallToBackend({
          path: '/secrets?per_page=100&page=1',
          successCallback: (secretResult: any) => {
            const keys = new Set<string>(
              (secretResult?.results ?? []).map((r: any) => r.key),
            );
            const initial: Record<string, FieldState> = {};
            match.configFields!.forEach((field) => {
              initial[field.id] = {
                value: '',
                isSet: keys.has(secretKeyFor(connectorId, field)),
              };
            });
            setFieldStates(initial);
            setLoading(false);
          },
          failureCallback: () => {
            setLoadError(t('connector_config_load_failed'));
            setLoading(false);
          },
        });
      },
      failureCallback: () => {
        setLoadError(t('connector_config_load_failed'));
        setLoading(false);
      },
    });
  }, [permissionsLoaded, canManageSecrets, connectorId, t]);

  const handleValueChange = (fieldId: string, value: string) => {
    setFieldStates((prev) => ({
      ...prev,
      [fieldId]: { ...prev[fieldId], value, error: undefined },
    }));
  };

  const toggleVisibility = (fieldId: string) => {
    setVisibleFields((prev) => ({ ...prev, [fieldId]: !prev[fieldId] }));
  };

  const handleSave = () => {
    if (!connectorId) {
      return;
    }

    // Validate: a required field with no existing secret must be filled in.
    let hasError = false;
    const validated = { ...fieldStates };
    configFields.forEach((field) => {
      const state = validated[field.id];
      const value = state?.value ?? '';
      if (field.required && !state?.isSet && value.trim() === '') {
        validated[field.id] = {
          ...state,
          error: t('connector_config_required_field'),
        };
        hasError = true;
      }
    });
    if (hasError) {
      setFieldStates(validated);
      return;
    }

    // Build one create/update per field that has a value entered.
    const tasks = configFields
      .map((field) => {
        const state = fieldStates[field.id];
        const value = state?.value ?? '';
        if (value.trim() === '') {
          return null; // blank -> leave unchanged
        }
        const key = secretKeyFor(connectorId, field);
        if (state?.isSet) {
          return callBackend({
            path: `/secrets/${key}`,
            httpMethod: 'PUT',
            postBody: { value },
          });
        }
        return callBackend({
          path: '/secrets',
          httpMethod: 'POST',
          postBody: { key, value },
        });
      })
      .filter((task): task is Promise<unknown> => task !== null);

    if (tasks.length === 0) {
      // Nothing changed; treat as a no-op success so the user gets feedback.
      setShowSuccess(true);
      return;
    }

    setSaving(true);
    setSaveError(null);
    Promise.all(tasks)
      .then(() => {
        // Everything entered is now persisted; reflect that in the form state.
        setFieldStates((prev) => {
          const next = { ...prev };
          configFields.forEach((field) => {
            const state = next[field.id];
            if (state && state.value.trim() !== '') {
              next[field.id] = { value: '', isSet: true };
            }
          });
          return next;
        });
        setSaving(false);
        setShowSuccess(true);
      })
      .catch(() => {
        setSaving(false);
        setSaveError(t('connector_config_save_failed'));
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
    return <Navigate to="/connectors" replace />;
  }

  // Connectors without configurable fields fall back to the generic Secrets page.
  if (notFound) {
    return <Navigate to="/configuration/secrets" replace />;
  }

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
          to="/connectors"
          underline="hover"
          color="primary"
        >
          {t('connectors')}
        </Link>
        <Typography color="text.primary">
          {connector?.name ?? connectorId ?? ''}
        </Typography>
      </Breadcrumbs>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : loadError ? (
        <Alert severity="error" sx={{ mt: 2 }}>
          {loadError}
        </Alert>
      ) : connector ? (
        <>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 2, mb: 1 }}>
            <ConnectorNameAvatar
              displayName={connector.name}
              pluginKey={connector.id}
            />
            <Typography variant="h4" sx={{ fontWeight: 700 }}>
              {t('connector_configure_title', { name: connector.name })}
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            {t('connector_config_subtitle')}
          </Typography>

          {saveError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {saveError}
            </Alert>
          )}

          <Paper
            elevation={0}
            sx={{
              p: 3,
              maxWidth: 640,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 2,
            }}
          >
            <Stack spacing={3}>
              {configFields.map((field) => {
                const state = fieldStates[field.id];
                const isPassword = field.type === 'password';
                const isVisible = !!visibleFields[field.id];
                const secretKey = secretKeyFor(connectorId!, field);
                return (
                  <Box key={field.id}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {field.label}
                        {field.required ? ' *' : ''}
                      </Typography>
                      {state?.isSet && (
                        <Chip
                          label={t('connector_config_field_set')}
                          size="small"
                          color="success"
                          variant="outlined"
                        />
                      )}
                    </Box>
                    <TextField
                      fullWidth
                      size="small"
                      type={isPassword && !isVisible ? 'password' : 'text'}
                      value={state?.value ?? ''}
                      onChange={(e) => handleValueChange(field.id, e.target.value)}
                      error={!!state?.error}
                      helperText={state?.error}
                      placeholder={
                        state?.isSet
                          ? t('connector_config_leave_blank_hint')
                          : undefined
                      }
                      data-testid={`connector-config-field-${field.id}`}
                      slotProps={
                        isPassword
                          ? {
                              input: {
                                endAdornment: (
                                  <InputAdornment position="end">
                                    <IconButton
                                      size="small"
                                      aria-label={t('toggle_visibility')}
                                      onClick={() => toggleVisibility(field.id)}
                                      edge="end"
                                    >
                                      {isVisible ? (
                                        <VisibilityOffIcon fontSize="small" />
                                      ) : (
                                        <VisibilityIcon fontSize="small" />
                                      )}
                                    </IconButton>
                                  </InputAdornment>
                                ),
                              },
                            }
                          : undefined
                      }
                    />
                    {field.helpText && (
                      <Typography variant="caption" color="text.secondary">
                        {field.helpText}
                      </Typography>
                    )}
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      component="div"
                      sx={{ mt: 0.5 }}
                    >
                      {t('connector_config_reference_hint')}{' '}
                      <Box
                        component="code"
                        sx={{
                          fontFamily: 'monospace',
                          bgcolor: 'action.hover',
                          px: 0.5,
                          borderRadius: 0.5,
                        }}
                      >
                        M8FLOW_SECRET:{secretKey}
                      </Box>
                    </Typography>
                  </Box>
                );
              })}
            </Stack>

            <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
              <Can I="POST" a={targetUris.secretListPath} ability={ability}>
                <Button
                  variant="contained"
                  onClick={handleSave}
                  disabled={saving}
                  data-testid="connector-config-save"
                >
                  {saving ? (
                    <CircularProgress size={20} sx={{ color: 'inherit' }} />
                  ) : (
                    t('connector_config_save')
                  )}
                </Button>
              </Can>
              <Button
                variant="outlined"
                onClick={() => navigate('/connectors')}
                disabled={saving}
                data-testid="connector-config-cancel"
              >
                {t('cancel')}
              </Button>
            </Stack>
          </Paper>
        </>
      ) : null}
    </Box>
  );
}
