import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Grid,
  Paper,
  Typography,
} from '@mui/material';
import { Can } from '@casl/react';
import HttpService from '../services/HttpService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import {
  ConnectorNameAvatar,
  displayNameForConnectorPlugin,
  pluginKeyFromOperatorId,
} from '../utils/connectorCardDisplay';

type ServiceTaskOperator = {
  id: string;
  parameters?: unknown[];
} & Record<string, unknown>;

export default function Connectors() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.serviceTaskListPath]: ['GET'],
    [targetUris.secretListPath]: ['POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );

  const [operators, setOperators] = useState<ServiceTaskOperator[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setPageTitle([t('connectors')]);
  }, [t]);

  useEffect(() => {
    if (!permissionsLoaded || !ability.can('GET', targetUris.serviceTaskListPath)) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    HttpService.makeCallToBackend({
      path: '/service-tasks',
      successCallback: (result: unknown) => {
        const list = Array.isArray(result) ? (result as ServiceTaskOperator[]) : [];
        setOperators(list);
        setLoading(false);
      },
      failureCallback: () => {
        setOperators([]);
        setLoadError(t('connectors_load_failed'));
        setLoading(false);
      },
    });
  }, [permissionsLoaded, ability, targetUris.serviceTaskListPath, t]);

  const grouped = useMemo(() => {
    if (!operators?.length) {
      return [];
    }
    const byPlugin = new Map<string, ServiceTaskOperator[]>();
    operators.forEach((op) => {
      if (!op?.id) {
        return;
      }
      const key = pluginKeyFromOperatorId(op.id);
      const existing = byPlugin.get(key) ?? [];
      existing.push(op);
      byPlugin.set(key, existing);
    });
    return Array.from(byPlugin.entries())
      .map(([pluginKey, ops]) => {
        const displayName = displayNameForConnectorPlugin(pluginKey, ops);
        return {
          pluginKey,
          displayName,
          count: ops.length,
        };
      })
      .sort((a, b) => a.displayName.localeCompare(b.displayName));
  }, [operators]);

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!ability.can('GET', targetUris.serviceTaskListPath)) {
    return <Navigate to="/" replace />;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        {t('connectors')}
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        {t('connectors_subtitle')}
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
      ) : grouped.length === 0 ? (
        <Paper
          elevation={0}
          sx={{
            p: 4,
            textAlign: 'center',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
          }}
        >
          <Typography variant="body1" color="text.secondary">
            {t('no_connectors_available')}
          </Typography>
        </Paper>
      ) : (
        <Grid container spacing={2}>
          {grouped.map(({ pluginKey, displayName, count }) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={pluginKey}>
              <Paper
                elevation={0}
                sx={{
                  p: 2,
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                  <ConnectorNameAvatar displayName={displayName} pluginKey={pluginKey} />
                  <Typography variant="h6" component="h2" sx={{ fontWeight: 600 }}>
                    {displayName}
                  </Typography>
                </Box>
                <Chip
                  label={
                    count === 1
                      ? `1 ${t('operation')}`
                      : `${count} ${t('operations')}`
                  }
                  size="small"
                  variant="outlined"
                  color="primary"
                  sx={{ alignSelf: 'flex-start', mb: 1.5 }}
                />
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2, flexGrow: 1 }}>
                  {t('use_via_service_task')}
                </Typography>
                <Can I="POST" a={targetUris.secretListPath} ability={ability}>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => navigate('/configuration/secrets')}
                    data-testid={`connector-configure-${pluginKey}`}
                  >
                    {t('configure')}
                  </Button>
                </Can>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
