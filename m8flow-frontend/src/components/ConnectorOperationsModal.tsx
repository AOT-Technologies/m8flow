import { useTranslation } from 'react-i18next';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { ConnectorNameAvatar } from '../utils/connectorCardDisplay';

export interface ConnectorOperationParam {
  id: string;
  type?: string;
  required?: boolean;
}

export interface ConnectorOperation {
  id: string;
  name: string;
  rawName: string;
  description: string;
  parameters: ConnectorOperationParam[];
}

export interface ConnectorGroup {
  id: string;
  name: string;
  description: string;
  status: string;
  icon: string;
  operationCount: number;
  operations: ConnectorOperation[];
  docsUrl?: string;
}

interface ConnectorOperationsModalProps {
  open: boolean;
  onClose: () => void;
  connector: ConnectorGroup | null;
}

export default function ConnectorOperationsModal({
  open,
  onClose,
  connector,
}: ConnectorOperationsModalProps) {
  const { t } = useTranslation();

  if (!connector) return null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      scroll="paper"
      data-testid="connector-operations-modal"
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <ConnectorNameAvatar
            displayName={connector.name}
            pluginKey={connector.id}
          />
          <Typography variant="h6" component="span" sx={{ fontWeight: 600 }}>
            {t('connector_operations', { name: connector.name })}
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        {connector.operations.length === 0 ? (
          <Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
            {t('no_connectors_available')}
          </Typography>
        ) : (
          connector.operations.map((op) => (
            <Accordion
              key={op.id}
              data-testid={`connector-operation-${op.id}`}
              disableGutters
              elevation={0}
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                '&:not(:last-child)': { mb: 1 },
                '&::before': { display: 'none' },
                borderRadius: 1,
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {op.name}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontFamily: 'monospace' }}
                  >
                    {op.id}
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {op.description && (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    {op.description}
                  </Typography>
                )}
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  {t('parameters')}
                </Typography>
                {!op.parameters?.length ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('no_parameters')}
                  </Typography>
                ) : (
                  <Box
                    component="table"
                    sx={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      '& th, & td': {
                        textAlign: 'left',
                        px: 1.5,
                        py: 0.75,
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        fontSize: '0.875rem',
                      },
                      '& th': {
                        fontWeight: 600,
                        color: 'text.secondary',
                        fontSize: '0.75rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                      },
                    }}
                  >
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {op.parameters.map((param) => (
                        <tr key={param.id}>
                          <td>
                            <Typography
                              variant="body2"
                              sx={{ fontFamily: 'monospace' }}
                            >
                              {param.id}
                            </Typography>
                          </td>
                          <td>
                            <Typography variant="body2" color="text.secondary">
                              {param.type || '—'}
                            </Typography>
                          </td>
                          <td>
                            <Chip
                              label={param.required ? t('required') : t('optional')}
                              size="small"
                              color={param.required ? 'warning' : 'default'}
                              variant="outlined"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))
        )}
      </DialogContent>
      <DialogActions>
        {connector.docsUrl && (
          <Button
            href={connector.docsUrl}
            target="_blank"
            rel="noopener noreferrer"
            startIcon={<OpenInNewIcon />}
            sx={{ mr: 'auto' }}
          >
            {t('connector_docs_link')}
          </Button>
        )}
        <Button onClick={onClose}>{t('close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
