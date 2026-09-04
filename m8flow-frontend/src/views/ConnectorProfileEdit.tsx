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
  CircularProgress,
  Divider,
  IconButton,
  InputAdornment,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { validateConnectorField } from '../utils/connectorFieldValidation';
import type { ConnectorConfigField } from '../components/ConnectorOperationsModal';
import {
  createConnectorProfile,
  fetchConnectorProfile,
  fetchConnectorTemplate,
  profileErrorMessage,
  profileFieldErrors,
  updateConnectorProfile,
  type ConnectorFieldDescriptor,
  type ConnectorProfile,
  type ConnectorTemplate,
} from '../services/ConnectorProfileService';

/**
 * The immutable identifier is also the Vault document path component. Keep
 * the browser validation aligned with the backend before a profile is saved.
 */
const PROFILE_NAME_RE = /^[a-zA-Z0-9]([a-zA-Z0-9_.-]{0,62}[a-zA-Z0-9])?$/;

/**
 * Adapt a descriptor field to the shape the existing connector field validator
 * expects, so validation rules live in one place rather than being restated.
 */
const asConfigField = (
  field: ConnectorFieldDescriptor,
): ConnectorConfigField => ({
  id: field.id,
  label: field.label,
  type: field.secret ? 'password' : 'text',
  required: field.required,
  format: field.format,
  minLength: field.minLength,
  maxLength: field.maxLength,
  helpText: field.helpText,
});

/**
 * Create or edit one connector profile.
 *
 * Fields come from the connector's descriptor, grouped by the definition's own
 * groups, so adding a connector needs no change here.
 *
 * Secret values are write-only by design: an existing secret shows as
 * "Configured" with an empty input and is left untouched unless the user types a
 * replacement. The backend treats a blank secret as "leave unchanged", so an
 * edit never silently wipes a credential the user did not mean to change.
 */
export default function ConnectorProfileEdit() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { connectorId = '', profileId } = useParams();
  const isEdit = !!profileId;
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.connectorProfileListPath]: ['GET', 'POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canManage = ability.can('POST', targetUris.connectorProfileListPath);

  const [loading, setLoading] = useState(true);
  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [existing, setExisting] = useState<ConnectorProfile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [profileName, setProfileName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setPageTitle([
      t('connectors'),
      isEdit
        ? t('connector_profile_edit', { defaultValue: 'Edit profile' })
        : t('connector_profile_add', { defaultValue: 'Add profile' }),
    ]);
  }, [t, isEdit]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const loadedTemplate = await fetchConnectorTemplate(connectorId);
      setTemplate(loadedTemplate);

      if (isEdit && profileId) {
        const profile = await fetchConnectorProfile(profileId);
        setExisting(profile);
        setProfileName(profile.profile_name);
        setDisplayName(profile.display_name);
        setDescription(profile.description ?? '');
        // Config values round-trip; secrets never come back, so their inputs
        // start empty and mean "leave unchanged".
        const initial: Record<string, string> = {};
        Object.entries(profile.config ?? {}).forEach(([key, value]) => {
          initial[key] = value === null || value === undefined ? '' : String(value);
        });
        setValues(initial);
      }
    } catch (error: any) {
      if (error?.status_code === 404) {
        setNotFound(true);
      } else {
        setLoadError(profileErrorMessage(error));
      }
    } finally {
      setLoading(false);
    }
  }, [connectorId, isEdit, profileId]);

  useEffect(() => {
    if (!permissionsLoaded || !canManage) {
      return;
    }
    load();
  }, [permissionsLoaded, canManage, load]);

  const fields = useMemo(() => template?.profileFields ?? [], [template]);

  /** Fields grouped in the order the definition declares its groups. */
  const grouped = useMemo(() => {
    const groups = template?.groups?.length
      ? template.groups
      : [{ id: '', label: '' }];
    return groups
      .map((group) => ({
        group,
        fields: fields.filter(
          (field) => field.group === group.id || !group.id,
        ),
      }))
      .filter((entry) => entry.fields.length > 0);
  }, [template, fields]);

  const isConfigured = (field: ConnectorFieldDescriptor) =>
    !!existing?.configured_secrets.includes(field.id);

  const setValue = (field: ConnectorFieldDescriptor, raw: string) => {
    setValues((prev) => ({ ...prev, [field.id]: raw }));
    const message = validateConnectorField(
      asConfigField(field),
      raw,
      isConfigured(field),
      t,
    );
    setErrors((prev) => {
      const next = { ...prev };
      if (message) {
        next[field.id] = message;
      } else {
        delete next[field.id];
      }
      return next;
    });
  };

  const validateAll = (): boolean => {
    const found: Record<string, string> = {};

    if (!isEdit) {
      if (!PROFILE_NAME_RE.test(profileName.trim())) {
        found.profile_name = t('connector_profile_name_invalid', {
          defaultValue:
            'Use 1-64 letters, digits, ".", "-" or "_", starting and ending with a letter or digit. This identifier is used in the Vault path.',
        });
      }
    }

    fields.forEach((field) => {
      const message = validateConnectorField(
        asConfigField(field),
        values[field.id] ?? '',
        isConfigured(field),
        t,
      );
      if (message) {
        found[field.id] = message;
      }
    });

    setErrors(found);
    return Object.keys(found).length === 0;
  };

  const save = async () => {
    if (!validateAll()) {
      return;
    }
    setSaving(true);
    setSaveError(null);

    // Only non-empty values are sent. For a secret that means "leave unchanged";
    // for a config field it means "not set".
    const config: Record<string, unknown> = {};
    fields.forEach((field) => {
      const raw = (values[field.id] ?? '').trim();
      if (raw !== '') {
        config[field.id] = raw;
      }
    });

    try {
      if (isEdit && profileId) {
        await updateConnectorProfile(profileId, {
          display_name: displayName.trim() || profileName,
          description: description.trim() || null,
          config,
        });
      } else {
        await createConnectorProfile({
          connector_type: connectorId,
          profile_name: profileName.trim(),
          display_name: displayName.trim() || profileName.trim(),
          description: description.trim() || null,
          config,
        });
      }
      navigate(`/connectors/${connectorId}/profiles`);
    } catch (error: any) {
      setSaveError(profileErrorMessage(error));
      const fieldErrors = profileFieldErrors(error);
      if (Object.keys(fieldErrors).length) {
        setErrors((prev) => ({ ...prev, ...fieldErrors }));
      }
    } finally {
      setSaving(false);
    }
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  // Profile writes hold credentials, so a user without write permission is sent
  // back rather than shown a form they cannot submit.
  if (!canManage || notFound) {
    return <Navigate to={`/connectors/${connectorId}/profiles`} replace />;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 760 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/connectors" underline="hover">
          {t('connectors')}
        </Link>
        <Link
          component={RouterLink}
          to={`/connectors/${connectorId}/profiles`}
          underline="hover"
        >
          {template?.name ?? connectorId}
        </Link>
        <Typography color="text.primary">
          {isEdit
            ? t('connector_profile_edit', { defaultValue: 'Edit profile' })
            : t('connector_profile_add', { defaultValue: 'Add profile' })}
        </Typography>
      </Breadcrumbs>

      {loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      ) : null}
      {saveError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setSaveError(null)}>
          {saveError}
        </Alert>
      ) : null}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <TextField
              label={t('connector_profile_identifier', {
                defaultValue: 'Identifier',
              })}
              value={profileName}
              onChange={(event) => {
                const nextName = event.target.value;
                setProfileName(nextName);
                setErrors((previous) => {
                  if (!previous.profile_name || PROFILE_NAME_RE.test(nextName.trim())) {
                    const nextErrors = { ...previous };
                    delete nextErrors.profile_name;
                    return nextErrors;
                  }
                  return previous;
                });
              }}
              // Immutable after create: BPMN diagrams store this name, so
              // changing it would orphan every task that selected the profile.
              disabled={isEdit}
              required
              error={!!errors.profile_name}
              helperText={
                errors.profile_name ??
                t('connector_profile_identifier_help', {
                  defaultValue:
                    'The immutable identifier service tasks select and Vault uses as the secret document name, e.g. smtp-production.',
                })
              }
              fullWidth
            />
            <TextField
              label={t('connector_profile_display_name', {
                defaultValue: 'Display name',
              })}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              fullWidth
            />
            <TextField
              label={t('description', { defaultValue: 'Description' })}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
            {grouped.map(({ group, fields: groupFields }) => (
              <Box key={group.id || 'default'}>
                <Divider sx={{ my: 1 }} />
                {group.label ? (
                  <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                    {group.label}
                  </Typography>
                ) : null}
                <Stack spacing={2}>
                  {groupFields.map((field) => {
                    const configured = isConfigured(field);
                    const isSecret = field.secret;
                    const shown = !!visible[field.id];
                    const helper =
                      errors[field.id] ??
                      (configured
                        ? t('connector_profile_secret_configured', {
                            defaultValue:
                              'Configured. Leave blank to keep the stored value.',
                          })
                        : field.helpText);

                    if (field.choices?.length) {
                      return (
                        <TextField
                          key={field.id}
                          select
                          label={field.label}
                          value={values[field.id] ?? ''}
                          onChange={(event) => setValue(field, event.target.value)}
                          required={field.required}
                          error={!!errors[field.id]}
                          helperText={helper}
                          fullWidth
                        >
                          {field.choices.map((choice) => (
                            <MenuItem
                              key={String(choice.value)}
                              value={String(choice.value)}
                            >
                              {choice.label}
                            </MenuItem>
                          ))}
                        </TextField>
                      );
                    }

                    return (
                      <TextField
                        key={field.id}
                        label={field.label}
                        value={values[field.id] ?? ''}
                        onChange={(event) => setValue(field, event.target.value)}
                        // A configured secret is satisfied by what is stored, so
                        // the field must not read as required-and-empty.
                        required={field.required && !configured}
                        error={!!errors[field.id]}
                        helperText={helper}
                        placeholder={field.example}
                        type={isSecret && !shown ? 'password' : 'text'}
                        autoComplete={isSecret ? 'new-password' : 'off'}
                        fullWidth
                        InputProps={
                          isSecret
                            ? {
                                endAdornment: (
                                  <InputAdornment position="end">
                                    <IconButton
                                      size="small"
                                      onClick={() =>
                                        setVisible((prev) => ({
                                          ...prev,
                                          [field.id]: !prev[field.id],
                                        }))
                                      }
                                      aria-label={t('toggle_visibility', {
                                        defaultValue: 'Toggle visibility',
                                      })}
                                    >
                                      {shown ? (
                                        <VisibilityOffIcon fontSize="small" />
                                      ) : (
                                        <VisibilityIcon fontSize="small" />
                                      )}
                                    </IconButton>
                                  </InputAdornment>
                                ),
                              }
                            : undefined
                        }
                      />
                    );
                  })}
                </Stack>
              </Box>
            ))}

            <Divider sx={{ my: 1 }} />
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button
                onClick={() => navigate(`/connectors/${connectorId}/profiles`)}
              >
                {t('cancel', { defaultValue: 'Cancel' })}
              </Button>
              <Button
                variant="contained"
                onClick={save}
                disabled={saving || Object.keys(errors).length > 0}
              >
                {saving
                  ? t('saving', { defaultValue: 'Saving...' })
                  : t('save', { defaultValue: 'Save' })}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      )}
    </Box>
  );
}
