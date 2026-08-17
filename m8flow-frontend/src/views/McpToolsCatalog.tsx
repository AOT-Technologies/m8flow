import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import {
  Build as BuildIcon,
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayArrowIcon,
  Search as SearchIcon,
  Sync as SyncIcon,
} from '@mui/icons-material';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import HttpService from '../services/HttpService';
import CopyActionButton from '../components/CopyActionButton';

interface McpToolParameter {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

type McpToolBadge = 'read' | 'write';

interface McpToolSummary {
  name: string;
  description: string;
  category: string;
  badge: McpToolBadge;
  parameters: McpToolParameter[];
}

interface McpToolsCatalogResponse {
  server_url: string;
  protocol_version: string;
  tool_count: number;
  tools: McpToolSummary[];
}

interface McpPingResponse {
  ok: boolean;
  latency_ms: number;
  protocol_version: string | null;
  authorized: boolean;
}

interface ExecutionState {
  running: boolean;
  result?: unknown;
  error?: string;
}

const ALL_CATEGORIES = '__all__';

/** "process-instances" -> "Process Instances". Categories come straight off each
 * tool's FastMCP tag, which is a lowercase-hyphenated slug, not display text. */
function humanizeCategory(category: string): string {
  if (!category) return category;
  return category
    .split('-')
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');
}

function badgeColor(badge: McpToolBadge): 'default' | 'warning' {
  if (badge === 'write') return 'warning';
  return 'default';
}

/** Best-effort per-parameter input value -> typed JSON value for the execute payload.
 * Returns `skip: true` for an empty, non-required field so it is simply omitted. */
function coerceArgumentValue(
  rawValue: string,
  type: string,
): { value?: unknown; skip?: boolean; invalid?: boolean } {
  const trimmed = rawValue.trim();
  if (trimmed === '') return { skip: true };

  if (type === 'object' || type === 'array') {
    try {
      return { value: JSON.parse(trimmed) };
    } catch {
      return { invalid: true };
    }
  }
  if (type === 'integer' || type === 'number') {
    const numeric = Number(trimmed);
    return Number.isNaN(numeric) ? { invalid: true } : { value: numeric };
  }
  if (type === 'boolean') {
    if (trimmed === 'true') return { value: true };
    if (trimmed === 'false') return { value: false };
    return { invalid: true };
  }
  return { value: trimmed };
}

function ToolTryIt({
  tool,
  execution,
  canExecute,
  onExecute,
}: {
  tool: McpToolSummary;
  execution?: ExecutionState;
  canExecute: boolean;
  onExecute: (toolName: string, args: Record<string, unknown>, confirm: boolean) => void;
}) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, string>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const buildArguments = (): Record<string, unknown> | null => {
    const args: Record<string, unknown> = {};
    for (const param of tool.parameters) {
      const raw = values[param.name] ?? '';
      const outcome = coerceArgumentValue(raw, param.type);
      if (outcome.invalid) {
        setValidationError(t('mcp_tools_invalid_json'));
        return null;
      }
      if (outcome.skip) {
        if (param.required) {
          setValidationError(t('mcp_tools_field_required'));
          return null;
        }
        continue;
      }
      args[param.name] = outcome.value;
    }
    setValidationError(null);
    return args;
  };

  const runExecute = (confirm: boolean) => {
    const args = buildArguments();
    if (args === null) return;
    onExecute(tool.name, args, confirm);
  };

  const handleExecuteClick = () => {
    if (tool.badge === 'write') {
      setConfirmOpen(true);
      return;
    }
    runExecute(false);
  };

  const running = execution?.running ?? false;

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('mcp_tools_try_it')}
      </Typography>
      {tool.parameters.map((param) => {
        const isMultiline = param.type === 'object' || param.type === 'array';
        return (
          <TextField
            key={param.name}
            size="small"
            fullWidth
            label={`${param.name}${param.required ? ' *' : ''}`}
            helperText={param.description || param.type}
            placeholder={param.type}
            multiline={isMultiline}
            minRows={isMultiline ? 3 : undefined}
            value={values[param.name] ?? ''}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, [param.name]: e.target.value }))
            }
            sx={{ mb: 1.5 }}
            data-testid={`mcp-tool-param-${tool.name}-${param.name}`}
          />
        );
      })}
      {validationError && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {validationError}
        </Alert>
      )}
      <Button
        variant="contained"
        size="small"
        startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
        disabled={running || !canExecute}
        onClick={handleExecuteClick}
        data-testid={`mcp-tool-execute-${tool.name}`}
      >
        {running ? t('mcp_tools_executing') : t('mcp_tools_execute')}
      </Button>

      {execution?.error && (
        <Alert severity="error" sx={{ mt: 1.5 }} data-testid={`mcp-tool-error-${tool.name}`}>
          {execution.error}
        </Alert>
      )}
      {execution?.result !== undefined && !execution.error && (
        <Paper
          variant="outlined"
          sx={{ mt: 1.5, p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}
          data-testid={`mcp-tool-result-${tool.name}`}
        >
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
            {t('mcp_tools_result_label')}
          </Typography>
          <Box
            component="pre"
            sx={{
              m: 0,
              mt: 0.5,
              fontFamily: 'monospace',
              fontSize: '0.8125rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 320,
              overflowY: 'auto',
            }}
          >
            {JSON.stringify(execution.result, null, 2)}
          </Box>
        </Paper>
      )}

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        data-testid={`mcp-tool-confirm-${tool.name}`}
      >
        <DialogTitle>{t('mcp_tools_confirm_write_title', { name: tool.name })}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('mcp_tools_confirm_write_body')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>{t('close')}</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => {
              setConfirmOpen(false);
              runExecute(true);
            }}
            data-testid={`mcp-tool-confirm-run-${tool.name}`}
          >
            {t('mcp_tools_confirm_write_confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function ToolAccordion({
  tool,
  execution,
  canExecute,
  onExecute,
}: {
  tool: McpToolSummary;
  execution?: ExecutionState;
  canExecute: boolean;
  onExecute: (toolName: string, args: Record<string, unknown>, confirm: boolean) => void;
}) {
  const { t } = useTranslation();

  return (
    <Accordion
      disableGutters
      elevation={0}
      data-testid={`mcp-tool-${tool.name}`}
      sx={{
        border: '1px solid',
        borderColor: 'divider',
        '&:not(:last-child)': { mb: 1 },
        '&::before': { display: 'none' },
        borderRadius: 1,
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap', minWidth: 0 }}>
          <Chip
            label={t(`mcp_tools_badge_${tool.badge}`)}
            size="small"
            color={badgeColor(tool.badge)}
            variant={tool.badge === 'read' ? 'outlined' : 'filled'}
          />
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{tool.name}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }}>
            {tool.description}
          </Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        {!tool.parameters.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            {t('no_parameters')}
          </Typography>
        ) : (
          <Box
            component="table"
            sx={{
              width: '100%',
              borderCollapse: 'collapse',
              mb: 1.5,
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
                <th>{t('name')}</th>
                <th>{t('mcp_tools_param_type_label')}</th>
                <th>{t('description')}</th>
                <th>{t('required')}</th>
              </tr>
            </thead>
            <tbody>
              {tool.parameters.map((param) => (
                <tr key={param.name}>
                  <td>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {param.name}
                    </Typography>
                  </td>
                  <td>
                    <Typography variant="body2" color="text.secondary">
                      {param.type || '—'}
                    </Typography>
                  </td>
                  <td>
                    <Typography variant="body2" color="text.secondary">
                      {param.description || '—'}
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

        <ToolTryIt tool={tool} execution={execution} canExecute={canExecute} onExecute={onExecute} />
      </AccordionDetails>
    </Accordion>
  );
}

export default function McpToolsCatalog() {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.m8flowMcpToolsCatalogPath]: ['GET'],
    [targetUris.m8flowMcpToolsExecutePath]: ['POST'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(permissionRequestData);
  const canAccessMcpToolsCatalog = ability.can('GET', targetUris.m8flowMcpToolsCatalogPath);
  const canExecuteMcpTools = ability.can('POST', targetUris.m8flowMcpToolsExecutePath);

  const [catalog, setCatalog] = useState<McpToolsCatalogResponse | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [ping, setPing] = useState<McpPingResponse | null>(null);
  const [pingLoading, setPingLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [category, setCategory] = useState<string>(ALL_CATEGORIES);
  const [executions, setExecutions] = useState<Record<string, ExecutionState>>({});

  const loadCatalog = () => {
    setCatalogLoading(true);
    setCatalogError(null);
    HttpService.makeCallToBackend({
      path: '/m8flow/mcp-tools',
      successCallback: (result: unknown) => {
        setCatalog(result as McpToolsCatalogResponse);
        setCatalogLoading(false);
      },
      failureCallback: () => {
        setCatalog(null);
        setCatalogError(t('mcp_tools_catalog_load_failed'));
        setCatalogLoading(false);
      },
    });
  };

  const loadPing = () => {
    setPingLoading(true);
    HttpService.makeCallToBackend({
      path: '/m8flow/mcp-tools/ping',
      successCallback: (result: unknown) => {
        setPing(result as McpPingResponse);
        setPingLoading(false);
      },
      failureCallback: () => {
        setPing(null);
        setPingLoading(false);
      },
    });
  };

  useEffect(() => {
    setPageTitle([t('mcp_tools_catalog')]);
  }, [t]);

  useEffect(() => {
    if (!permissionsLoaded || !canAccessMcpToolsCatalog) return;
    loadCatalog();
    loadPing();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [permissionsLoaded, canAccessMcpToolsCatalog]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    (catalog?.tools ?? []).forEach((tool) => set.add(tool.category));
    return Array.from(set).sort();
  }, [catalog]);

  const filteredToolsByCategory = useMemo(() => {
    const tools = catalog?.tools ?? [];
    const needle = searchText.trim().toLowerCase();
    const filtered = tools.filter((tool) => {
      if (category !== ALL_CATEGORIES && tool.category !== category) return false;
      if (!needle) return true;
      return (
        tool.name.toLowerCase().includes(needle) ||
        tool.description.toLowerCase().includes(needle)
      );
    });
    const grouped = new Map<string, McpToolSummary[]>();
    filtered.forEach((tool) => {
      const list = grouped.get(tool.category) ?? [];
      list.push(tool);
      grouped.set(tool.category, list);
    });
    return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [catalog, searchText, category]);

  const handleExecute = (toolName: string, args: Record<string, unknown>, confirm: boolean) => {
    setExecutions((prev) => ({ ...prev, [toolName]: { running: true } }));
    HttpService.makeCallToBackend({
      path: '/m8flow/mcp-tools/execute',
      httpMethod: 'POST',
      postBody: { tool_name: toolName, arguments: args, confirm },
      successCallback: (result: unknown) => {
        const payload = result as { result?: unknown };
        setExecutions((prev) => ({
          ...prev,
          [toolName]: { running: false, result: payload?.result },
        }));
      },
      failureCallback: (error: unknown) => {
        const message =
          (error as { message?: string })?.message || t('mcp_tools_execute_failed');
        setExecutions((prev) => ({ ...prev, [toolName]: { running: false, error: message } }));
      },
    });
  };

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canAccessMcpToolsCatalog) {
    return <Navigate to="/" replace />;
  }

  return (
    <Box
      sx={{
        p: { xs: 2, md: 3 },
        width: '100%',
        maxWidth: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
      data-testid="mcp-tools-catalog-page"
    >
      <Paper
        elevation={0}
        sx={{
          p: 3,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          mb: 2,
          maxWidth: '100%',
          boxSizing: 'border-box',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
            <Box
              sx={{
                width: 40,
                height: 40,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 2,
                bgcolor: 'background.light',
                color: 'primary.main',
                flexShrink: 0,
              }}
            >
              <BuildIcon />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
                {t('mcp_tools_catalog')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('mcp_tools_catalog_subtitle')}
              </Typography>
            </Box>
          </Box>
          <Button
            variant="outlined"
            size="small"
            startIcon={pingLoading ? <CircularProgress size={16} /> : <SyncIcon />}
            disabled={pingLoading}
            onClick={loadPing}
            data-testid="mcp-tools-test-connection"
          >
            {t('mcp_tools_test_connection')}
          </Button>
        </Box>

        {catalog && (
          <Box
            sx={{
              mt: 2.5,
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flexWrap: 'wrap',
              color: 'text.secondary',
            }}
          >
            <Typography
              variant="body2"
              sx={{ fontFamily: 'monospace', userSelect: 'all' }}
              data-testid="mcp-tools-server-url"
            >
              {catalog.server_url}
            </Typography>
            <CopyActionButton
              value={catalog.server_url}
              label={t('copy_to_clipboard')}
              testId="mcp-tools-server-url-copy"
            />
            <Typography variant="body2">·</Typography>
            <Typography variant="body2" data-testid="mcp-tools-protocol-version">
              {t('mcp_tools_protocol_version', { version: catalog.protocol_version })}
            </Typography>
            <Typography variant="body2">·</Typography>
            <Typography variant="body2" data-testid="mcp-tools-tool-count">
              {t('mcp_tools_tool_count', { count: catalog.tool_count })}
            </Typography>
            {ping && (
              <>
                <Typography variant="body2">·</Typography>
                <Typography variant="body2" data-testid="mcp-tools-ping-status">
                  {ping.ok
                    ? t('mcp_tools_ping_ok', { latency: ping.latency_ms })
                    : t('mcp_tools_ping_failed')}
                </Typography>
                <Chip
                  size="small"
                  label={ping.authorized ? t('mcp_tools_authorized') : t('mcp_tools_unauthorized')}
                  color={ping.authorized ? 'success' : 'error'}
                  variant="outlined"
                  data-testid="mcp-tools-authorized-chip"
                />
              </>
            )}
          </Box>
        )}
      </Paper>

      {!canExecuteMcpTools && (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="mcp-tools-read-only-notice">
          {t('mcp_tools_read_only_access_notice')}
        </Alert>
      )}

      {catalogError && (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="mcp-tools-catalog-error">
          <Typography sx={{ fontWeight: 600 }}>{catalogError}</Typography>
          <Typography variant="body2">{t('mcp_tools_catalog_unavailable_subtitle')}</Typography>
        </Alert>
      )}

      {catalogLoading && !catalog ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        catalog && (
          <>
            <Paper
              elevation={0}
              sx={{
                p: 2,
                mb: 2,
                display: 'flex',
                gap: 2,
                flexWrap: 'wrap',
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 2,
              }}
            >
              <Box sx={{ flexGrow: 1, minWidth: 200 }}>
                <TextField
                  size="small"
                  fullWidth
                  variant="outlined"
                  placeholder={t('mcp_tools_search_placeholder')}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  data-testid="mcp-tools-search-input"
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <SearchIcon fontSize="small" />
                      </InputAdornment>
                    ),
                  }}
                />
              </Box>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel>{t('mcp_tools_category_label')}</InputLabel>
                <Select
                  value={category}
                  label={t('mcp_tools_category_label')}
                  data-testid="mcp-tools-category-select"
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <MenuItem value={ALL_CATEGORIES}>{t('mcp_tools_all_categories')}</MenuItem>
                  {categories.map((cat) => (
                    <MenuItem key={cat} value={cat}>
                      {humanizeCategory(cat)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Paper>

            {filteredToolsByCategory.length === 0 ? (
              <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                {t('mcp_tools_no_tools_match')}
              </Typography>
            ) : (
              filteredToolsByCategory.map(([cat, tools]) => (
                <Box key={cat} sx={{ mb: 3 }}>
                  <Typography
                    variant="subtitle1"
                    component="h2"
                    sx={{ fontWeight: 600, mb: 1.5 }}
                    data-testid={`mcp-tools-category-heading-${cat}`}
                  >
                    {humanizeCategory(cat)}
                  </Typography>
                  {tools.map((tool) => (
                    <ToolAccordion
                      key={tool.name}
                      tool={tool}
                      execution={executions[tool.name]}
                      canExecute={canExecuteMcpTools}
                      onExecute={handleExecute}
                    />
                  ))}
                </Box>
              ))
            )}
          </>
        )
      )}
    </Box>
  );
}
