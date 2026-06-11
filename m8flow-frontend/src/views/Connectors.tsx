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
  InputAdornment,
  Paper,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Search as SearchIcon,
  CheckCircleOutline as CheckCircleOutlineIcon,
  HelpOutline as HelpOutlineIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import Link from '@mui/material/Link';
import { Can } from '@casl/react';
import HttpService from '../services/HttpService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { ConnectorNameAvatar } from '../utils/connectorCardDisplay';
import ConnectorOperationsModal, {
  type ConnectorGroup,
} from '../components/ConnectorOperationsModal';

export default function Connectors() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.connectorsGroupedPath]: ['GET'],
    [targetUris.secretListPath]: ['POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canAccessConnectors = ability.can('GET', targetUris.connectorsGroupedPath);

  const [connectors, setConnectors] = useState<ConnectorGroup[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [modalConnector, setModalConnector] = useState<ConnectorGroup | null>(null);

  useEffect(() => {
    setPageTitle([t('connectors')]);
  }, [t]);

  useEffect(() => {
    if (!permissionsLoaded || !canAccessConnectors) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    HttpService.makeCallToBackend({
      path: '/m8flow/connectors-grouped',
      successCallback: (result: unknown) => {
        const list = Array.isArray(result) ? (result as ConnectorGroup[]) : [];
        setConnectors(list);
        setLoading(false);
      },
      failureCallback: () => {
        setConnectors([]);
        setLoadError(t('connectors_load_failed'));
        setLoading(false);
      },
    });
  }, [permissionsLoaded, canAccessConnectors, t]);

  const filtered = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return connectors;
    return connectors.filter((c) => {
      if (c.name.toLowerCase().includes(term)) return true;
      if (c.description.toLowerCase().includes(term)) return true;
      return c.operations.some(
        (op) =>
          op.name.toLowerCase().includes(term) ||
          op.id.toLowerCase().includes(term),
      );
    });
  }, [connectors, searchTerm]);

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canAccessConnectors) {
    return <Navigate to="/" replace />;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <Typography variant="h4" sx={{ fontWeight: 700 }}>
          {t('connectors')}
        </Typography>
        <Tooltip title={t('connectors_help_tooltip')} arrow>
          <HelpOutlineIcon
            fontSize="small"
            color="action"
            sx={{ cursor: 'help' }}
          />
        </Tooltip>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3, flexWrap: 'wrap' }}>
        <Typography variant="body1" color="text.secondary">
          {t('connectors_subtitle')}
        </Typography>
        <Link
          href="https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy#m8flow-connector-proxy"
          target="_blank"
          rel="noopener noreferrer"
          variant="body2"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
        >
          {t('connectors_docs_link')}
          <OpenInNewIcon sx={{ fontSize: '0.875rem' }} />
        </Link>
      </Box>

      {loadError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      )}

      {!loading && connectors.length > 0 && (
        <TextField
          size="small"
          placeholder={t('connectors_search_placeholder')}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          sx={{ mb: 3, maxWidth: 420, width: '100%' }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" color="action" />
                </InputAdornment>
              ),
            },
          }}
          data-testid="connectors-search"
        />
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : connectors.length === 0 ? (
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
      ) : filtered.length === 0 ? (
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
            {t('no_matching_connectors')}
          </Typography>
        </Paper>
      ) : (
        <Grid container spacing={2}>
          {filtered.map((connector) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={connector.id}>
              <Paper
                elevation={0}
                sx={{
                  p: 2.5,
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  transition: 'border-color 0.15s',
                  '&:hover': { borderColor: 'primary.main' },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                  <ConnectorNameAvatar
                    displayName={connector.name}
                    pluginKey={connector.id}
                  />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography
                      variant="h6"
                      component="h2"
                      sx={{ fontWeight: 600, lineHeight: 1.3 }}
                    >
                      {connector.name}
                    </Typography>
                  </Box>
                </Box>

                <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 1.5 }}>
                  <Chip
                    label={
                      connector.operationCount === 1
                        ? `1 ${t('operation')}`
                        : `${connector.operationCount} ${t('operations')}`
                    }
                    size="small"
                    variant="outlined"
                    color="primary"
                  />
                  <Chip
                    icon={<CheckCircleOutlineIcon />}
                    label={t('available')}
                    size="small"
                    color="success"
                    variant="outlined"
                  />
                </Box>

                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 2, flexGrow: 1 }}
                >
                  {connector.description || t('use_via_service_task')}
                </Typography>

                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => setModalConnector(connector)}
                    data-testid={`connector-view-ops-${connector.id}`}
                  >
                    {t('view_operations')}
                  </Button>
                  <Can I="POST" a={targetUris.secretListPath} ability={ability}>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => navigate('/configuration/secrets')}
                      data-testid={`connector-configure-${connector.id}`}
                    >
                      {t('configure')}
                    </Button>
                  </Can>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      <ConnectorOperationsModal
        open={modalConnector !== null}
        onClose={() => setModalConnector(null)}
        connector={modalConnector}
      />
    </Box>
  );
}
