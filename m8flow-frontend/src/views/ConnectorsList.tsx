import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import HttpService from '../services/HttpService';

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
  return value
    .split(' ')
    .map((part) => {
      if (part.toLowerCase() === 'http') return 'HTTP';
      if (part.toLowerCase() === 'smtp') return 'SMTP';
      if (part.toLowerCase() === 'api') return 'API';
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
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
      return payloadObj.items as ServiceTaskOperator[];
    }

    if (Array.isArray(payloadObj.results)) {
      return payloadObj.results as ServiceTaskOperator[];
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

export default function ConnectorsList() {
  const [operators, setOperators] = useState<ServiceTaskOperator[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    HttpService.makeCallToBackend({
      path: '/service-tasks',
      successCallback: (result: unknown) => {
        setOperators(normalizeOperatorPayload(result));
        setLoading(false);
      },
      failureCallback: () => {
        setErrorMessage('Unable to load connectors.');
        setLoading(false);
      },
    });
  }, []);

  const connectorRows = useMemo(() => {
    const connectorMap = new Map<string, { name: string; operators: number }>();

    operators.forEach((operator, index) => {
      const operatorIdentifier = extractOperatorIdentifier(operator, index);
      const key = extractConnectorKey(operator, operatorIdentifier);
      if (!key) {
        return;
      }

      if (!connectorMap.has(key)) {
        connectorMap.set(key, {
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
          Connectors
        </Typography>
        <Typography sx={{ mb: 3 }} variant="body2" color="text.secondary">
          Use these connectors via Service Tasks in a process model.
        </Typography>

        {errorMessage && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errorMessage}
          </Alert>
        )}

        {!errorMessage && connectorRows.length === 0 && (
          <Alert severity="info">No connectors are currently available.</Alert>
        )}

        {!errorMessage && connectorRows.length > 0 && (
          <TableContainer
            component={Paper}
            sx={{ borderRadius: 1.5, overflow: 'hidden' }}
          >
            <Table>
              <TableHead>
                <TableRow sx={{ bgcolor: 'background.default' }}>
                  <TableCell>Connector</TableCell>
                  <TableCell>Available Operations</TableCell>
                  <TableCell>Usage</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {connectorRows.map((row) => (
                  <TableRow key={row.name}>
                    <TableCell>{row.name}</TableCell>
                    <TableCell sx={{ fontWeight: 500 }}>{row.operators}</TableCell>
                    <TableCell>
                      Use in a Service Task in your process model.
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>
    </Box>
  );
}
