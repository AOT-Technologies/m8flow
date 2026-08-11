import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material';
import HttpService from '../services/HttpService';
import { type ConnectorConfigField } from './ConnectorOperationsModal';
import { validateConnectorField } from '../utils/connectorFieldValidation';

interface FieldState {
  /** Current input value. Empty means "leave unchanged" when the secret already exists. */
  value: string;
  /** Whether a secret for this field already exists (write-only: value is never loaded). */
  isSet: boolean;
  /** Validation error message for this field, if any. */
  error?: string;
}

export const callBackend = (opts: {
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

/** Page size when scanning existing secrets. */
const SECRETS_PER_PAGE = 100;

/**
 * Fetch every Secret key visible to the active tenant.
 *
 * Follows pagination (`{ results, pagination: { pages } }`) so keys beyond the
 * first page are not missed — fetching only page 1 would wrongly report a
 * secret as "not configured" for tenants with many secrets, forcing a
 * spurious required-field error and a POST create that conflicts with the
 * already-existing key. Correct even if the server caps `per_page`, since it
 * relies on the reported page count.
 */
export const fetchAllSecretKeys = async (): Promise<Set<string>> => {
  const keys = new Set<string>();
  const collect = (res: any) =>
    (res?.results ?? []).forEach((r: any) => {
      if (r?.key) {
        keys.add(r.key);
      }
    });

  const firstPage: any = await callBackend({
    path: `/secrets?per_page=${SECRETS_PER_PAGE}&page=1`,
    httpMethod: 'GET',
  });
  collect(firstPage);

  const totalPages = Number(firstPage?.pagination?.pages) || 1;
  if (totalPages > 1) {
    const remaining = await Promise.all(
      Array.from({ length: totalPages - 1 }, (_, i) =>
        callBackend({
          path: `/secrets?per_page=${SECRETS_PER_PAGE}&page=${i + 2}`,
          httpMethod: 'GET',
        }),
      ),
    );
    remaining.forEach(collect);
  }
  return keys;
};

interface SecretFieldsFormProps {
  /** Field descriptors to render, in display order. */
  fields: ConnectorConfigField[];
  /** The Secret key each field persists to. */
  secretKeyOf: (field: ConnectorConfigField) => string;
  /**
   * Show the `M8FLOW_SECRET:<key>` caption under each field. Meaningful for connector
   * credentials, which are referenced that way from Service Tasks; misleading for
   * secrets a backend service reads directly.
   */
  showResolverHint?: boolean;
  /** Rendered above the fields, e.g. a "not configured yet" warning. */
  banner?: React.ReactNode;
  /** Called after every field with a value entered has been persisted. */
  onSaved?: () => void;
  /** Rendered next to Save (typically a Cancel button). */
  secondaryAction?: React.ReactNode;
}

/**
 * Write-only credential entry form backed by the standard /v1.0/secrets endpoints.
 *
 * Secret values are never readable, so existing values are never pre-filled: a field
 * whose secret already exists is shown as "Configured" and left unchanged unless the user
 * types a new value. Shared by the connector Configure page and the external form email
 * settings page so both behave identically.
 *
 * Callers are responsible for gating on secret write permission before rendering this.
 */
export default function SecretFieldsForm({
  fields,
  secretKeyOf,
  showResolverHint = false,
  banner,
  onSaved,
  secondaryAction,
}: SecretFieldsFormProps) {
  const { t } = useTranslation();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fieldStates, setFieldStates] = useState<Record<string, FieldState>>({});
  const [visibleFields, setVisibleFields] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Save is disabled while any field shows an active validation error.
  const hasActiveErrors = useMemo(
    () => Object.values(fieldStates).some((state) => !!state.error),
    [fieldStates],
  );

  // Determine which fields already have a saved secret (keys only).
  // Scans every page so a secret beyond page 1 is still detected.
  const loadExistingKeys = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    fetchAllSecretKeys()
      .then((keys) => {
        const initial: Record<string, FieldState> = {};
        fields.forEach((field) => {
          initial[field.id] = { value: '', isSet: keys.has(secretKeyOf(field)) };
        });
        setFieldStates(initial);
        setLoading(false);
      })
      .catch(() => {
        setLoadError(t('connector_config_load_failed'));
        setLoading(false);
      });
    // secretKeyOf is derived from fields by every caller; re-running on identity
    // changes alone would refetch on each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields, t]);

  useEffect(loadExistingKeys, [loadExistingKeys]);

  const handleValueChange = (fieldId: string, value: string) => {
    const field = fields.find((f) => f.id === fieldId);
    setFieldStates((prev) => {
      const prevState = prev[fieldId];
      const error = field
        ? validateConnectorField(field, value, !!prevState?.isSet, t)
        : undefined;
      return { ...prev, [fieldId]: { ...prevState, value, error } };
    });
  };

  const toggleVisibility = (fieldId: string) => {
    setVisibleFields((prev) => ({ ...prev, [fieldId]: !prev[fieldId] }));
  };

  const handleSave = () => {
    // Full validation pass over every field (required, whitespace-only, length,
    // format). Catches untouched-but-empty required fields the live check on
    // change never ran against.
    let hasError = false;
    const validated = { ...fieldStates };
    fields.forEach((field) => {
      const state = validated[field.id];
      const error = validateConnectorField(field, state?.value ?? '', !!state?.isSet, t);
      validated[field.id] = {
        ...state,
        value: state?.value ?? '',
        isSet: !!state?.isSet,
        error,
      };
      if (error) {
        hasError = true;
      }
    });
    if (hasError) {
      setFieldStates(validated);
      return;
    }

    // Build one create/update per field that has a value entered. The trimmed
    // value is what gets persisted so stray leading/trailing whitespace is never
    // stored in the secret.
    const tasks = fields
      .map((field) => {
        const state = fieldStates[field.id];
        const value = (state?.value ?? '').trim();
        if (value === '') {
          return null; // blank -> leave unchanged
        }
        const key = secretKeyOf(field);
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
      onSaved?.();
      return;
    }

    setSaving(true);
    setSaveError(null);
    Promise.all(tasks)
      .then(() => {
        // Everything entered is now persisted; reflect that in the form state.
        setFieldStates((prev) => {
          const next = { ...prev };
          fields.forEach((field) => {
            const state = next[field.id];
            if (state && state.value.trim() !== '') {
              next[field.id] = { value: '', isSet: true };
            }
          });
          return next;
        });
        setSaving(false);
        onSaved?.();
      })
      .catch(() => {
        setSaving(false);
        setSaveError(t('connector_config_save_failed'));
      });
  };

  // The banner explains why the caller opened this form at all, so it renders alongside
  // the loading and error states rather than only once the secrets scan finishes.
  if (loading) {
    return (
      <>
        {banner}
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      </>
    );
  }

  if (loadError) {
    return (
      <>
        {banner}
        <Alert severity="error" sx={{ mt: 2 }}>
          {loadError}
        </Alert>
      </>
    );
  }

  return (
    <>
      {banner}
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
          {fields.map((field) => {
            const state = fieldStates[field.id];
            const isPassword = field.type === 'password';
            const isVisible = !!visibleFields[field.id];
            const secretKey = secretKeyOf(field);
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
                    state?.isSet ? t('connector_config_leave_blank_hint') : undefined
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
                  {showResolverHint ? (
                    <>
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
                    </>
                  ) : (
                    <>
                      {t('secret_key')}:{' '}
                      <Box
                        component="code"
                        sx={{
                          fontFamily: 'monospace',
                          bgcolor: 'action.hover',
                          px: 0.5,
                          borderRadius: 0.5,
                        }}
                      >
                        {secretKey}
                      </Box>
                    </>
                  )}
                </Typography>
              </Box>
            );
          })}
        </Stack>

        <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || hasActiveErrors}
            data-testid="connector-config-save"
          >
            {saving ? (
              <CircularProgress size={20} sx={{ color: 'inherit' }} />
            ) : (
              t('connector_config_save')
            )}
          </Button>
          {secondaryAction}
        </Stack>
      </Paper>
    </>
  );
}
