import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import type { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import { SiPostgresql, SiSalesforce, SiSlack, SiStripe } from 'react-icons/si';
import { FaGlobe, FaPlug } from 'react-icons/fa';
import { MdEmail } from 'react-icons/md';
import HttpService from '../services/HttpService';
import { useM8flowUriListForPermissions } from '../hooks/M8flowUriListForPermissions';

type ServiceTaskOperator = {
  id?: string;
  identifier?: string;
  name?: string;
  connector?: string;
  connector_id?: string;
  operator_id?: string;
};

function normalizeOperatorEntry(entry: unknown): ServiceTaskOperator[] {
  if (typeof entry === 'string') {
    return [{ id: entry }];
  }
  if (entry && typeof entry === 'object') {
    return [entry as ServiceTaskOperator];
  }
  return [];
}

function titleCase(value: string): string {
  const excludeUppercase = new Set([
    'mail',
    'file',
    'chat',
    'data',
    'push',
    'pull',
    'send',
    'read',
    'write',
    'list',
    'get',
    'put',
    'post',
    'patch',
    'head',
  ]);

  return value
    .split(' ')
    .map((part) => {
      const token = part.trim();
      if (!token) {
        return token;
      }

      const lower = token.toLowerCase();
      if (
        token.length <= 4 &&
        /^[a-z]+$/.test(lower) &&
        !excludeUppercase.has(lower)
      ) {
        return token.toUpperCase();
      }

      return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
    })
    .join(' ');
}

function formatConnectorName(rawConnectorName: string): string {
  const normalized = rawConnectorName
    .replace(/[_-]v\d+$/i, '')
    .replace(/[_-]+/g, ' ')
    .trim();
  return titleCase(normalized || rawConnectorName);
}

function extractOperatorIdentifier(
  operator: ServiceTaskOperator,
  index: number,
): string {
  return (
    operator.id ||
    operator.identifier ||
    operator.operator_id ||
    operator.name ||
    `operator-${index}`
  );
}

function extractConnectorKey(
  operator: ServiceTaskOperator,
  operatorIdentifier: string,
): string | null {
  const candidate =
    operator.connector || operator.connector_id || operatorIdentifier;
  if (!candidate) {
    return null;
  }
  if (candidate.startsWith('operator-')) {
    return null;
  }
  const slashIdx = candidate.indexOf('/');
  if (slashIdx > 0) {
    return candidate.slice(0, slashIdx);
  }
  return candidate;
}

function normalizeOperatorPayload(payload: unknown): ServiceTaskOperator[] {
  if (Array.isArray(payload)) {
    return payload.flatMap((entry) => normalizeOperatorEntry(entry));
  }

  if (payload && typeof payload === 'object') {
    const payloadObj = payload as Record<string, unknown>;

    if (Array.isArray(payloadObj.items)) {
      return payloadObj.items.flatMap((entry) =>
        normalizeOperatorEntry(entry),
      );
    }

    if (Array.isArray(payloadObj.results)) {
      return payloadObj.results.flatMap((entry) =>
        normalizeOperatorEntry(entry),
      );
    }

    return Object.entries(payloadObj).flatMap(([key, value]) => {
      if (Array.isArray(value)) {
        return value.flatMap((entry) => normalizeOperatorEntry(entry));
      }
      if (value && typeof value === 'object') {
        return [{ id: key, ...(value as ServiceTaskOperator) }];
      }
      if (typeof value === 'string') {
        return [{ id: value }];
      }
      return [];
    });
  }

  return [];
}

function failureStatusCode(errorOrJson: unknown): number | undefined {
  if (errorOrJson && typeof errorOrJson === 'object') {
    const o = errorOrJson as Record<string, unknown>;
    const code = o.status_code ?? o.statusCode;
    if (typeof code === 'number') {
      return code;
    }
    if (typeof code === 'string') {
      const n = parseInt(code, 10);
      if (!Number.isNaN(n)) {
        return n;
      }
    }
    const resp = o.response as { status?: number } | undefined;
    if (resp && typeof resp.status === 'number') {
      return resp.status;
    }
  }
  return undefined;
}

type ConnectorRow = {
  rawKey: string;
  name: string;
  operators: number;
};

function ConnectorCardIcon({ rawKey }: { rawKey: string }) {
  const k = rawKey.toLowerCase();
  const size = 28;
  const themed = (node: ReactNode) => (
    <Box
      sx={{ display: 'flex', alignItems: 'center', color: 'primary.main' }}
      aria-hidden
    >
      {node}
    </Box>
  );

  if (k.includes('slack')) {
    return <SiSlack size={size} color="#4A154B" aria-hidden />;
  }
  if (k.includes('salesforce')) {
    return <SiSalesforce size={size} color="#00A1E0" aria-hidden />;
  }
  if (k.includes('postgres')) {
    return themed(<SiPostgresql size={size} />);
  }
  if (k.includes('smtp') || k.includes('email') || k.includes('mail')) {
    return themed(<MdEmail size={size} />);
  }
  if (k.includes('stripe')) {
    return <SiStripe size={size} color="#635BFF" aria-hidden />;
  }
  if (k.includes('http') || k.includes('rest') || k.includes('api')) {
    return themed(<FaGlobe size={size} />);
  }
  return themed(<FaPlug size={size} />);
}

export default function ConnectorsList() {
  const { t } = useTranslation();
  const { targetUris } = useM8flowUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {
    [targetUris.secretListPath]: ['GET'],
  };
  const { ability } = usePermissionFetcher(permissionRequestData);
  const [operators, setOperators] = useState<ServiceTaskOperator[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErrorMessage(null);
    HttpService.makeCallToBackend({
      path: targetUris.serviceTaskListPath,
      successCallback: (result: unknown) => {
        setOperators(normalizeOperatorPayload(result));
        setLoading(false);
      },
      failureCallback: (errorOrJson: unknown) => {
        const status = failureStatusCode(errorOrJson);
        if (status === 401 || status === 403) {
          setErrorMessage(t('connectors_unauthorized'));
        } else if (status === 503 || status === 502) {
          setErrorMessage(t('connectors_unavailable'));
        } else {
          setErrorMessage(t('unable_to_load_connectors'));
        }
        setLoading(false);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per API path; avoid refetch when i18n changes
  }, [targetUris.serviceTaskListPath]);

  const connectorRows = useMemo(() => {
    const connectorMap = new Map<string, ConnectorRow>();

    operators.forEach((operator, index) => {
      const operatorIdentifier = extractOperatorIdentifier(operator, index);
      const key = extractConnectorKey(operator, operatorIdentifier);
      if (!key) {
        return;
      }

      if (!connectorMap.has(key)) {
        connectorMap.set(key, {
          rawKey: key,
          name: formatConnectorName(key),
          operators: 0,
        });
      }

      const current = connectorMap.get(key);
      if (current) {
        current.operators += 1;
      }
    });

    return Array.from(connectorMap.values()).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [operators]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, width: '100%', boxSizing: 'border-box' }}>
      <Box sx={{ maxWidth: 1200 }}>
        <Typography variant="h1" sx={{ mb: 0.5 }}>
          {t('connectors')}
        </Typography>
        <Typography sx={{ mb: 3 }} variant="body2" color="text.secondary">
          {t('connectors_description')}
        </Typography>

        {errorMessage && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage}
          </Alert>
        )}

        {!errorMessage && connectorRows.length === 0 && (
          <Alert severity="info">{t('no_connectors_available')}</Alert>
        )}

        {!errorMessage && connectorRows.length > 0 && (
          <Grid container spacing={2}>
            {connectorRows.map((row) => (
              <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }} key={row.rawKey}>
                <Card
                  variant="outlined"
                  sx={{ height: '100%', borderRadius: 1.5 }}
                >
                  <CardContent>
                    <Stack spacing={1.5}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <ConnectorCardIcon rawKey={row.rawKey} />
                        <Typography variant="h6" component="h2">
                          {row.name}
                        </Typography>
                      </Stack>
                      <Chip
                        size="small"
                        label={t('available_operations_count', {
                          count: row.operators,
                        })}
                        color="primary"
                        variant="outlined"
                      />
                      <Typography variant="body2" color="text.secondary">
                        {t('connector_usage_hint')}
                      </Typography>
                    </Stack>
                    <CardActions sx={{ pt: 0, pl: 0 }}>
                      {ability.can('GET', targetUris.secretListPath) ? (
                        <Button
                          size="small"
                          variant="outlined"
                          component={Link}
                          to="/configuration/secrets"
                          data-testid={`connector-configure-${row.rawKey}`}
                        >
                          {t('configure')}
                        </Button>
                      ) : null}
                    </CardActions>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Box>
  );
}
