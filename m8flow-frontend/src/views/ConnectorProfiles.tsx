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
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  ToggleOff as ToggleOffIcon,
  ToggleOn as ToggleOnIcon,
} from '@mui/icons-material';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { ConnectorNameAvatar } from '../utils/connectorCardDisplay';
import { Notification } from '../components/Notification';
import {
  deleteConnectorProfile,
  fetchConnectorProfiles,
  fetchConnectorTemplate,
  profileErrorMessage,
  reactivateConnectorProfile,
  type ConnectorProfile,
  type ConnectorTemplate,
} from '../services/ConnectorProfileService';

/**
 * The profiles saved for one connector.
 *
 * A profile is a named credential/configuration set -- "smtp-staging",
 * "smtp-production" -- that a BPMN service task selects from a dropdown instead
 * of spelling out host, user and password on every task.
 *
 * Inactive profiles stay listed (dimmed, sorted last) so a deactivated profile
 * is visibly recoverable rather than appearing to be gone.
 */
export default function ConnectorProfiles() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { connectorId = '' } = useParams();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.connectorProfileListPath]: ['GET', 'POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canRead = ability.can('GET', targetUris.connectorProfileListPath);
  const canManage = ability.can('POST', targetUris.connectorProfileListPath);

  const [loading, setLoading] = useState(true);
  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ConnectorProfile | null>(
    null,
  );

  useEffect(() => {
    setPageTitle([t('connectors'), template?.name ?? connectorId]);
  }, [t, template, connectorId]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [loadedTemplate, loadedProfiles] = await Promise.all([
        fetchConnectorTemplate(connectorId),
        fetchConnectorProfiles(connectorId),
      ]);
      setTemplate(loadedTemplate);
      setProfiles(loadedProfiles);
    } catch (error: any) {
      if (error?.status_code === 404) {
        setNotFound(true);
      } else {
        setLoadError(profileErrorMessage(error));
      }
    } finally {
      setLoading(false);
    }
  }, [connectorId]);

  useEffect(() => {
    if (!permissionsLoaded || !canRead) {
      return;
    }
    load();
  }, [permissionsLoaded, canRead, load]);

  /** Active first, then by name, so a deactivated profile sorts to the bottom. */
  const ordered = useMemo(
    () =>
      [...profiles].sort((a, b) => {
        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }
        return a.profile_name.localeCompare(b.profile_name);
      }),
    [profiles],
  );

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setActionError(null);
    try {
      await action();
      setSuccessMessage(message);
      await load();
    } catch (error: any) {
      setActionError(profileErrorMessage(error));
    }
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canRead || notFound) {
    return <Navigate to="/connectors" replace />;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/connectors" underline="hover">
          {t('connectors')}
        </Link>
        <Typography color="text.primary">
          {template?.name ?? connectorId}
        </Typography>
      </Breadcrumbs>

      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 1 }}
      >
        <Stack direction="row" spacing={2} alignItems="center">
          {template ? (
            <ConnectorNameAvatar
              displayName={template.name}
              pluginKey={template.id}
            />
          ) : null}
          <Box>
            <Typography variant="h5">
              {t('connector_profiles_title', {
                defaultValue: '{{name}} profiles',
                name: template?.name ?? connectorId,
              })}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('connector_profiles_subtitle', {
                defaultValue:
                  'Saved credential sets a service task can select by name.',
              })}
            </Typography>
          </Box>
        </Stack>
        {canManage ? (
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() =>
              navigate(`/connectors/${connectorId}/profiles/new`)
            }
          >
            {t('connector_profile_add', { defaultValue: 'Add profile' })}
          </Button>
        ) : null}
      </Stack>

      {loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      ) : null}
      {actionError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      ) : null}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Paper variant="outlined">
          {ordered.length === 0 ? (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography color="text.secondary" gutterBottom>
                {t('connector_profiles_empty', {
                  defaultValue:
                    'No profiles yet. Add one to select it from a service task.',
                })}
              </Typography>
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>
                    {t('connector_profile_name', { defaultValue: 'Profile' })}
                  </TableCell>
                  <TableCell>
                    {t('connector_profile_identifier', {
                      defaultValue: 'Identifier',
                    })}
                  </TableCell>
                  <TableCell>
                    {t('connector_profile_credentials', {
                      defaultValue: 'Credentials',
                    })}
                  </TableCell>
                  <TableCell align="right">
                    {t('actions', { defaultValue: 'Actions' })}
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {ordered.map((profile) => (
                  <TableRow
                    key={profile.id}
                    sx={{ opacity: profile.is_active ? 1 : 0.55 }}
                  >
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2">
                          {profile.display_name}
                        </Typography>
                        {!profile.is_active ? (
                          <Chip
                            size="small"
                            label={t('inactive', { defaultValue: 'Inactive' })}
                          />
                        ) : null}
                      </Stack>
                      {profile.description ? (
                        <Typography variant="caption" color="text.secondary">
                          {profile.description}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {profile.profile_name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {/* Names only: a stored secret's value is never returned. */}
                      <Typography variant="caption" color="text.secondary">
                        {profile.configured_secrets.length
                          ? profile.configured_secrets.join(', ')
                          : t('connector_profile_no_secrets', {
                              defaultValue: 'None stored',
                            })}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      {canManage ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Tooltip title={t('edit', { defaultValue: 'Edit' })}>
                            <IconButton
                              size="small"
                              onClick={() =>
                                navigate(
                                  `/connectors/${connectorId}/profiles/${profile.id}/edit`,
                                )
                              }
                            >
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          {profile.is_active ? (
                            <Tooltip
                              title={t('connector_profile_deactivate', {
                                defaultValue: 'Deactivate',
                              })}
                            >
                              <IconButton
                                size="small"
                                onClick={() =>
                                  runAction(
                                    () => deleteConnectorProfile(profile.id),
                                    t('connector_profile_deactivated', {
                                      defaultValue: 'Profile deactivated.',
                                    }),
                                  )
                                }
                              >
                                <ToggleOnIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          ) : (
                            <Tooltip
                              title={t('connector_profile_reactivate', {
                                defaultValue: 'Reactivate',
                              })}
                            >
                              <IconButton
                                size="small"
                                onClick={() =>
                                  runAction(
                                    () => reactivateConnectorProfile(profile.id),
                                    t('connector_profile_reactivated', {
                                      defaultValue: 'Profile reactivated.',
                                    }),
                                  )
                                }
                              >
                                <ToggleOffIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                          <Tooltip
                            title={t('connector_profile_delete', {
                              defaultValue: 'Delete permanently',
                            })}
                          >
                            <IconButton
                              size="small"
                              onClick={() => setPendingDelete(profile)}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
      )}

      <Dialog open={!!pendingDelete} onClose={() => setPendingDelete(null)}>
        <DialogTitle>
          {t('connector_profile_delete_title', {
            defaultValue: 'Delete this profile permanently?',
          })}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('connector_profile_delete_body', {
              defaultValue:
                'This removes "{{name}}" and its stored credentials. Any process model that still selects this profile will fail when it runs. Deactivate instead if you may need it again.',
              name: pendingDelete?.display_name ?? '',
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingDelete(null)}>
            {t('cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const target = pendingDelete;
              setPendingDelete(null);
              if (target) {
                runAction(
                  () => deleteConnectorProfile(target.id, true),
                  t('connector_profile_deleted', {
                    defaultValue: 'Profile deleted.',
                  }),
                );
              }
            }}
          >
            {t('delete', { defaultValue: 'Delete' })}
          </Button>
        </DialogActions>
      </Dialog>

      {successMessage ? (
        <Notification
          title={successMessage}
          onClose={() => setSuccessMessage(null)}
        />
      ) : null}
    </Box>
  );
}
