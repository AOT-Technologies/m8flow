import { ReactNode, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import QRCode from 'react-qr-code';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Paper,
  Typography,
} from '@mui/material';
import {
  Cable as CableIcon,
  Check as CheckIcon,
  Close as CloseIcon,
  DataObject as DataObjectIcon,
  ExpandMore as ExpandMoreIcon,
  Language as LanguageIcon,
  LockOutlined as LockOutlinedIcon,
  QrCode2 as QrCode2Icon,
  QueryStats as QueryStatsIcon,
  Sync as SyncIcon,
  Terminal as TerminalIcon,
} from '@mui/icons-material';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { useConfig } from '../utils/useConfig';
import CopyActionButton from '../components/CopyActionButton';

const monospaceUrl = {
  fontFamily: 'monospace',
  fontSize: '0.9375rem',
  lineHeight: 1.5,
  userSelect: 'all',
} as const;

const mcpActivityRows = [
  {
    status: 'success',
    tool: 'start_process_instance',
    detail: 'Invoice approval v3',
    client: 'Claude Code',
    latency: '380 ms',
    time: '2 min ago',
  },
  {
    status: 'success',
    tool: 'list_tasks',
    detail: '12 results',
    client: 'Cursor',
    latency: '210 ms',
    time: '9 min ago',
  },
  {
    status: 'error',
    tool: 'complete_task',
    detail: 'Permission denied',
    client: 'Cursor',
    latency: '95 ms',
    time: '14 min ago',
  },
  {
    status: 'running',
    tool: 'diagnose_workflow',
    detail: 'Running...',
    client: 'Claude Code',
    latency: '',
    time: 'now',
  },
] as const;

function ServerUrlRow({
  url,
  actions,
  urlTestId,
}: {
  url: string;
  actions: ReactNode;
  urlTestId?: string;
}) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <Typography
        data-testid={urlTestId}
        sx={{ ...monospaceUrl, flex: 1, minWidth: 0, overflowX: 'auto', whiteSpace: 'nowrap' }}
      >
        {url}
      </Typography>
      <Box sx={{ display: 'flex', gap: 1, flexShrink: 0 }}>{actions}</Box>
    </Box>
  );
}

function ClientCard({
  icon,
  name,
  description,
  action,
  testId,
}: {
  icon: ReactNode;
  name: string;
  description: string;
  action: ReactNode;
  testId: string;
}) {
  return (
    <Paper
      variant="outlined"
      data-testid={testId}
      sx={{
        p: 2,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        borderRadius: 2,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {icon}
        <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 600 }}>
          {name}
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }}>
        {description}
      </Typography>
      {action}
    </Paper>
  );
}

function ActivityStatusIcon({ status }: { status: 'success' | 'error' | 'running' }) {
  if (status === 'success') {
    return <CheckIcon sx={{ color: 'success.main', fontSize: 24 }} />;
  }

  if (status === 'error') {
    return <CloseIcon sx={{ color: 'error.main', fontSize: 24 }} />;
  }

  return (
    <SyncIcon
      sx={{
        color: 'primary.main',
        fontSize: 24,
        animation: 'mcpActivitySpin 1.2s linear infinite',
        '@keyframes mcpActivitySpin': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
      }}
    />
  );
}

function ActivityMetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'success';
}) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2,
        height: '100%',
        bgcolor: 'background.light',
        borderRadius: 2,
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography
        variant="h4"
        component="p"
        sx={{ mt: 1, fontWeight: 700, color: tone === 'success' ? 'success.dark' : 'text.primary' }}
      >
        {value}
      </Typography>
    </Paper>
  );
}

function ActivityRow({
  row,
}: {
  row: (typeof mcpActivityRows)[number];
}) {
  const meta = row.latency
    ? `${row.client} · ${row.latency} · ${row.time}`
    : `${row.client} · ${row.time}`;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '24px minmax(0, 1fr)', md: '24px minmax(0, 1fr) auto' },
        gap: { xs: 1, md: 1.5 },
        alignItems: 'center',
        py: 1.75,
        borderTop: '1px solid',
        borderColor: 'divider',
      }}
    >
      <ActivityStatusIcon status={row.status} />
      <Box sx={{ minWidth: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography
            component="span"
            sx={{
              fontFamily: 'monospace',
              fontSize: '1rem',
              lineHeight: 1.4,
              color: 'text.primary',
              wordBreak: 'break-word',
            }}
          >
            {row.tool}
          </Typography>
          {row.status === 'error' ? (
            <Box
              component="span"
              sx={{
                px: 1,
                py: 0.25,
                bgcolor: 'rgba(211, 47, 47, 0.12)',
                borderRadius: 999,
                color: 'error.dark',
                fontSize: '0.875rem',
                lineHeight: 1.4,
                fontWeight: 600,
              }}
            >
              {row.detail}
            </Box>
          ) : (
            <Typography component="span" color="text.secondary" sx={{ fontWeight: 600 }}>
              {row.detail}
            </Typography>
          )}
        </Box>
      </Box>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{
          gridColumn: { xs: '2', md: 'auto' },
          justifySelf: { xs: 'start', md: 'end' },
          fontWeight: 600,
          whiteSpace: { xs: 'normal', md: 'nowrap' },
        }}
      >
        {meta}
      </Typography>
    </Box>
  );
}

export default function McpConnection() {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { MCP_SERVER_URL } = useConfig();
  const [claudeAiStepsOpen, setClaudeAiStepsOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);

  const permissionRequestData: PermissionsToCheck = {
    [targetUris.m8flowMcpConnectionPath]: ['GET'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );
  const canAccessMcpConnection = ability.can(
    'GET',
    targetUris.m8flowMcpConnectionPath,
  );

  useEffect(() => {
    setPageTitle([t('mcp_connection')]);
  }, [t]);

  if (!permissionsLoaded) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!canAccessMcpConnection) {
    return <Navigate to="/" replace />;
  }

  const cursorConfigSnippet = JSON.stringify(
    { mcpServers: { m8flow: { url: MCP_SERVER_URL } } },
    null,
    2,
  );
  const claudeCodeCommand = `claude mcp add --transport http m8flow ${MCP_SERVER_URL}`;

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
      data-testid="mcp-connection-page"
    >
      <Paper
        elevation={0}
        sx={{
          p: 3,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          maxWidth: '100%',
          boxSizing: 'border-box',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
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
            <CableIcon />
          </Box>
          <Box>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              {t('mcp_connection')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('mcp_connection_subtitle')}
            </Typography>
          </Box>
        </Box>

        {!MCP_SERVER_URL ? (
          <Alert severity="warning" sx={{ mt: 2.5 }} data-testid="mcp-not-configured">
            {t('mcp_not_configured')}
          </Alert>
        ) : (
          <>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                mt: 2.5,
                bgcolor: 'action.hover',
                borderRadius: 2,
              }}
            >
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mb: 0.5, fontWeight: 600 }}
              >
                {t('mcp_server_url')}
              </Typography>
              <ServerUrlRow
                url={MCP_SERVER_URL}
                urlTestId="mcp-server-url"
                actions={
                  <>
                    <CopyActionButton
                      value={MCP_SERVER_URL}
                      label={t('copy_to_clipboard')}
                      testId="mcp-server-url-copy"
                      variant="contained"
                    />
                    {/* <Button
                      variant="outlined"
                      size="small"
                      onClick={() => setQrOpen(true)}
                      startIcon={<QrCode2Icon fontSize="small" />}
                      data-testid="mcp-qr-button"
                      sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
                    >
                      {t('mcp_qr')}
                    </Button> */}
                  </>
                }
              />
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  mt: 1,
                  color: 'text.secondary',
                }}
              >
                <LockOutlinedIcon sx={{ fontSize: '0.875rem' }} />
                <Typography variant="caption" data-testid="mcp-auth-note">
                  {t('mcp_auth_caption')}
                </Typography>
              </Box>
            </Paper>

            <Typography
              variant="subtitle1"
              component="h2"
              sx={{ fontWeight: 600, mt: 3, mb: 1.5 }}
            >
              {t('mcp_setup_title')}
            </Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 4 }}>
                <ClientCard
                  icon={<TerminalIcon fontSize="small" color="action" />}
                  name="Claude Code"
                  description={t('mcp_claude_code_description')}
                  testId="mcp-client-claude-code"
                  action={
                    <CopyActionButton
                      value={claudeCodeCommand}
                      label={t('mcp_copy_command')}
                      testId="mcp-copy-command"
                      fullWidth
                    />
                  }
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }}>
                <ClientCard
                  icon={<DataObjectIcon fontSize="small" color="action" />}
                  name="Cursor"
                  description={t('mcp_cursor_description')}
                  testId="mcp-client-cursor"
                  action={
                    <CopyActionButton
                      value={cursorConfigSnippet}
                      label={t('mcp_copy_config')}
                      testId="mcp-copy-config"
                      fullWidth
                    />
                  }
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }}>
                <ClientCard
                  icon={<LanguageIcon fontSize="small" color="action" />}
                  name="Claude.ai"
                  description={t('mcp_claude_ai_description')}
                  testId="mcp-client-claude-ai"
                  action={
                    <Button
                      variant="outlined"
                      size="small"
                      fullWidth
                      onClick={() => setClaudeAiStepsOpen(true)}
                      data-testid="mcp-view-steps"
                    >
                      {t('mcp_view_steps')}
                    </Button>
                  }
                />
              </Grid>
            </Grid>

            {/* <Paper
              variant="outlined"
              data-testid="mcp-activity-panel"
              sx={{
                p: { xs: 2, md: 2.5 },
                mt: 3,
                borderRadius: 2,
                maxWidth: '100%',
                boxSizing: 'border-box',
                overflow: 'hidden',
              }}
            >
              <Box
                sx={{
                  display: 'flex',
                  alignItems: { xs: 'flex-start', sm: 'center' },
                  justifyContent: 'space-between',
                  gap: 2,
                  flexDirection: { xs: 'column', sm: 'row' },
                  mb: 2,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <QueryStatsIcon sx={{ color: 'text.primary' }} />
                  <Typography variant="h5" component="h2" sx={{ fontWeight: 700 }}>
                    {t('mcp_activity')}
                  </Typography>
                </Box>
                <Box
                  sx={{
                    display: 'flex',
                    gap: 1,
                    flexWrap: 'wrap',
                    width: { xs: '100%', sm: 'auto' },
                  }}
                >
                  <Button
                    variant="outlined"
                    color="inherit"
                    endIcon={<ExpandMoreIcon />}
                    sx={{ justifyContent: 'space-between', minWidth: 150 }}
                  >
                    {t('mcp_activity_all_clients')}
                  </Button>
                  <Button
                    variant="outlined"
                    color="inherit"
                    endIcon={<ExpandMoreIcon />}
                    sx={{ justifyContent: 'space-between', minWidth: 150 }}
                  >
                    {t('mcp_activity_last_hour')}
                  </Button>
                </Box>
              </Box>

              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <ActivityMetricCard
                    label={t('mcp_activity_tool_calls_today')}
                    value="128"
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <ActivityMetricCard
                    label={t('mcp_activity_success_rate')}
                    value="97%"
                    tone="success"
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <ActivityMetricCard
                    label={t('mcp_activity_median_latency')}
                    value="420 ms"
                  />
                </Grid>
              </Grid>

              <Box data-testid="mcp-activity-list">
                {mcpActivityRows.map((row) => (
                  <ActivityRow key={`${row.tool}-${row.time}`} row={row} />
                ))}
              </Box>
            </Paper> */}

            <Dialog
              open={claudeAiStepsOpen}
              onClose={() => setClaudeAiStepsOpen(false)}
              maxWidth="sm"
              fullWidth
              data-testid="mcp-claude-ai-dialog"
            >
              <DialogTitle sx={{ fontWeight: 600 }}>
                {t('mcp_claude_ai_dialog_title')}
              </DialogTitle>
              <DialogContent>
                <Box component="ol" sx={{ m: 0, pl: 2.5 }}>
                  {[
                    t('mcp_claude_ai_step_1'),
                    t('mcp_claude_ai_step_2'),
                    t('mcp_claude_ai_step_3'),
                  ].map((step) => (
                    <Typography
                      key={step}
                      component="li"
                      variant="body2"
                      sx={{ mb: 0.5 }}
                    >
                      {step}
                    </Typography>
                  ))}
                </Box>
                <Paper
                  variant="outlined"
                  sx={{
                    p: 1.5,
                    mt: 1.5,
                    bgcolor: 'action.hover',
                    borderRadius: 2,
                  }}
                >
                  <ServerUrlRow
                    url={MCP_SERVER_URL}
                    actions={
                      <CopyActionButton
                        value={MCP_SERVER_URL}
                        label={t('copy_to_clipboard')}
                        testId="mcp-dialog-url-copy"
                      />
                    }
                  />
                </Paper>
              </DialogContent>
              <DialogActions>
                <Button
                  onClick={() => setClaudeAiStepsOpen(false)}
                  data-testid="mcp-dialog-close"
                >
                  {t('close')}
                </Button>
              </DialogActions>
            </Dialog>

            <Dialog
              open={qrOpen}
              onClose={() => setQrOpen(false)}
              maxWidth="xs"
              fullWidth
              aria-labelledby="mcp-qr-dialog-title"
              data-testid="mcp-qr-dialog"
              slotProps={{
                paper: {
                  sx: {
                    borderRadius: 2,
                    overflow: 'hidden',
                  },
                },
              }}
            >
              <DialogTitle
                id="mcp-qr-dialog-title"
                sx={{ px: 2.5, pt: 2.5, pb: 1.5 }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                  <Box
                    sx={{
                      width: 36,
                      height: 36,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: 2,
                      bgcolor: 'background.light',
                      color: 'primary.main',
                      flexShrink: 0,
                    }}
                  >
                    <QrCode2Icon fontSize="small" />
                  </Box>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      variant="h6"
                      component="span"
                      sx={{ fontWeight: 700 }}
                    >
                      {t('mcp_qr_dialog_title')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('mcp_qr_hint')}
                    </Typography>
                  </Box>
                </Box>
              </DialogTitle>
              <DialogContent
                sx={{ px: 2.5, pt: 0, pb: 2.5, overflow: 'visible' }}
              >
                {/* QR keeps a white surface in both themes so scanners get the
                    contrast they need. */}
                <Box
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 2,
                  }}
                >
                  <Box
                    sx={{
                      width: { xs: 232, sm: 244 },
                      p: 1.5,
                      bgcolor: '#ffffff',
                      borderRadius: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                      boxSizing: 'border-box',
                      boxShadow: '0 1px 2px rgba(16, 24, 40, 0.08)',
                    }}
                  >
                    <QRCode
                      value={MCP_SERVER_URL}
                      size={220}
                      bgColor="#ffffff"
                      fgColor="#000000"
                      data-testid="mcp-qr-code"
                      style={{
                        display: 'block',
                        height: 'auto',
                        maxWidth: '100%',
                        width: '100%',
                      }}
                    />
                  </Box>
                  <Paper
                    variant="outlined"
                    sx={{
                      width: '100%',
                      maxWidth: '100%',
                      p: 1.5,
                      bgcolor: 'action.hover',
                      borderRadius: 2,
                      boxSizing: 'border-box',
                      overflow: 'hidden',
                    }}
                  >
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: 'block', mb: 0.5, fontWeight: 600 }}
                    >
                      {t('mcp_server_url')}
                    </Typography>
                    <ServerUrlRow
                      url={MCP_SERVER_URL}
                      urlTestId="mcp-qr-url"
                      actions={
                        <CopyActionButton
                          value={MCP_SERVER_URL}
                          label={t('mcp_copy_url')}
                          testId="mcp-qr-url-copy"
                        />
                      }
                    />
                  </Paper>
                </Box>
              </DialogContent>
              <DialogActions sx={{ px: 2.5, py: 1.5, pt: 0 }}>
                <Button
                  onClick={() => setQrOpen(false)}
                  data-testid="mcp-qr-close"
                >
                  {t('close')}
                </Button>
              </DialogActions>
            </Dialog>
          </>
        )}
      </Paper>
    </Box>
  );
}
