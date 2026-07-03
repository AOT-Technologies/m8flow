import { ReactNode, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
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
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Cable as CableIcon,
  Check as CheckIcon,
  ContentCopy as ContentCopyIcon,
  DataObject as DataObjectIcon,
  Language as LanguageIcon,
  LockOutlined as LockOutlinedIcon,
  Terminal as TerminalIcon,
} from '@mui/icons-material';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { useConfig } from '../utils/useConfig';

const srOnly = {
  position: 'absolute',
  width: 1,
  height: 1,
  p: 0,
  m: '-1px',
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
  border: 0,
} as const;

const monospaceUrl = {
  fontFamily: 'monospace',
  fontSize: '0.9375rem',
  lineHeight: 1.5,
  userSelect: 'all',
} as const;

function CopyActionButton({
  value,
  label,
  testId,
  variant = 'outlined',
  fullWidth,
}: {
  value: string;
  label: string;
  testId: string;
  variant?: 'outlined' | 'contained';
  fullWidth?: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <>
      <Tooltip
        title={t('copied_to_clipboard')}
        open={copied}
        arrow
        disableHoverListener
        disableFocusListener
        disableTouchListener
      >
        <Button
          variant={variant}
          size="small"
          color="primary"
          fullWidth={fullWidth}
          onClick={handleCopy}
          startIcon={
            copied ? (
              <CheckIcon
                fontSize="small"
                color={variant === 'contained' ? 'inherit' : 'success'}
              />
            ) : (
              <ContentCopyIcon fontSize="small" />
            )
          }
          data-testid={testId}
          // Constant label + fixed min-width: swapping the icon (not the text)
          // gives feedback without reflowing the row.
          sx={{ flexShrink: 0, whiteSpace: 'nowrap', minWidth: fullWidth ? undefined : 96 }}
        >
          {label}
        </Button>
      </Tooltip>
      <Box component="span" role="status" aria-live="polite" sx={srOnly}>
        {copied ? t('copied_to_clipboard') : ''}
      </Box>
    </>
  );
}

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

export default function McpConnection() {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { MCP_SERVER_URL } = useConfig();
  const [claudeAiStepsOpen, setClaudeAiStepsOpen] = useState(false);

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
    <Box sx={{ p: 3, maxWidth: 900 }} data-testid="mcp-connection-page">
      <Paper
        elevation={0}
        sx={{
          p: 3,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
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
          </>
        )}
      </Paper>
    </Box>
  );
}
