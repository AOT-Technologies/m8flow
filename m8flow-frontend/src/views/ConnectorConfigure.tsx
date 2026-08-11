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
  Link,
  Typography,
} from '@mui/material';
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
import SecretFieldsForm from '../components/SecretFieldsForm';

/**
 * Compose the Secret key for a connector config field.
 *
 * Prefers the field's explicit `secretKey` (the canonical name the sample
 * templates reference, e.g. GITHUB_PAT_TOKEN). Falls back to
 * `{connectorId}_{fieldId}` when none is declared. The result is normalized to
 * word characters only: the runtime resolver matches
 * `M8FLOW_SECRET:(?P<name>\w+)` and `\w` excludes "-", so any non-word char in a
 * connector/field id (or a malformed explicit key) would otherwise produce a
 * secret that can never be resolved. The replace is a no-op for the existing
 * all-uppercase explicit keys.
 */
export const secretKeyFor = (
  connectorId: string,
  field: ConnectorConfigField,
): string =>
  (field.secretKey ?? `${connectorId}_${field.id}`).replace(/\W/g, '_');

/**
 * Connector-specific configuration form.
 *
 * Reached via /connectors/:connectorId/configure for connectors that declare
 * `configFields` in the backend connector metadata. Saves/updates each field as
 * a Secret record through the standard /v1.0/secrets endpoints. Connectors with
 * no configurable fields never route here (the Connectors page redirects them to
 * Configuration > Secrets instead).
 *
 * The form itself lives in SecretFieldsForm, shared with the external form email
 * settings page; this view only resolves which fields to render.
 *
 * Access is intentionally gated on secret WRITE (POST) permission: this is a
 * credential-entry form whose only purpose is to create/update secrets, and the
 * Connectors page only surfaces the "Configure" action to POST-capable users.
 * Users without write access are redirected away rather than shown a read-only
 * view.
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
  const [showSuccess, setShowSuccess] = useState(false);

  const configFields: ConnectorConfigField[] = useMemo(
    () => connector?.configFields ?? [],
    [connector],
  );

  const secretKeyOf = useCallback(
    (field: ConnectorConfigField) => secretKeyFor(connectorId ?? '', field),
    [connectorId],
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

    // Load the connector definition (the field schema lives here). Which fields
    // already have a saved secret is resolved by SecretFieldsForm.
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
        setLoading(false);
      },
      failureCallback: () => {
        setLoadError(t('connector_config_load_failed'));
        setLoading(false);
      },
    });
  }, [permissionsLoaded, canManageSecrets, connectorId, t]);

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

          <SecretFieldsForm
            fields={configFields}
            secretKeyOf={secretKeyOf}
            showResolverHint
            onSaved={() => setShowSuccess(true)}
            secondaryAction={
              <Button
                variant="outlined"
                onClick={() => navigate('/connectors')}
                data-testid="connector-config-cancel"
              >
                {t('cancel')}
              </Button>
            }
          />
        </>
      ) : null}
    </Box>
  );
}
