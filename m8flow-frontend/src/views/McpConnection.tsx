import { ReactNode, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import {
  Alert,
  Box,
  CircularProgress,
  IconButton,
  Paper,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Check as CheckIcon,
  ContentCopy as ContentCopyIcon,
  HelpOutline as HelpOutlineIcon,
} from '@mui/icons-material';
import { PermissionsToCheck } from '@spiffworkflow-frontend/interfaces';
import { usePermissionFetcher } from '@spiffworkflow-frontend/hooks/PermissionService';
import { setPageTitle } from '../helpers';
import { useM8flowUriListForPermissions as useUriListForPermissions } from '../hooks/M8flowUriListForPermissions';
import { useConfig } from '../utils/useConfig';

function CopyButton({ value, testId }: { value: string; testId: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Tooltip
      title={copied ? t('copied_to_clipboard') : t('copy_to_clipboard')}
      arrow
    >
      <IconButton
        size="small"
        onClick={handleCopy}
        aria-label={t('copy_to_clipboard')}
        data-testid={testId}
      >
        {copied ? (
          <CheckIcon fontSize="small" color="success" />
        ) : (
          <ContentCopyIcon fontSize="small" />
        )}
      </IconButton>
    </Tooltip>
  );
}

function CodeBlock({ code, testId }: { code: string; testId: string }) {
  return (
    <Paper
      variant="outlined"
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 1,
        p: 1.5,
        bgcolor: 'action.hover',
        borderRadius: 2,
      }}
    >
      <Box
        component="pre"
        data-testid={testId}
        sx={{
          m: 0,
          flex: 1,
          minWidth: 0,
          overflowX: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.8125rem',
          lineHeight: 1.6,
        }}
      >
        {code}
      </Box>
      <CopyButton value={code} testId={`${testId}-copy`} />
    </Paper>
  );
}

function ClientSection({
  title,
  steps,
  children,
  testId,
}: {
  title: string;
  steps: string[];
  children?: ReactNode;
  testId: string;
}) {
  return (
    <Paper
      elevation={0}
      data-testid={testId}
      sx={{
        p: 2.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
      }}
    >
      <Typography variant="h6" component="h3" sx={{ fontWeight: 600, mb: 1 }}>
        {title}
      </Typography>
      <Box component="ol" sx={{ m: 0, mb: children ? 1.5 : 0, pl: 2.5 }}>
        {steps.map((step) => (
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
      {children}
    </Paper>
  );
}

export default function McpConnection() {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { MCP_SERVER_URL } = useConfig();

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

  const mcpJsonSnippet = JSON.stringify(
    { mcpServers: { m8flow: { url: MCP_SERVER_URL } } },
    null,
    2,
  );
  const claudeCodeCommand = `claude mcp add --transport http m8flow ${MCP_SERVER_URL}`;
  const mcpRemoteSnippet = JSON.stringify(
    {
      mcpServers: {
        m8flow: { command: 'npx', args: ['mcp-remote', MCP_SERVER_URL] },
      },
    },
    null,
    2,
  );

  return (
    <Box sx={{ p: 3, maxWidth: 900 }} data-testid="mcp-connection-page">
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
        <Typography variant="h4" sx={{ fontWeight: 700 }}>
          {t('mcp_connection')}
        </Typography>
        <Tooltip title={t('mcp_connection_help_tooltip')} arrow>
          <HelpOutlineIcon
            fontSize="small"
            color="action"
            sx={{ cursor: 'help' }}
          />
        </Tooltip>
      </Box>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        {t('mcp_connection_subtitle')}
      </Typography>

      {!MCP_SERVER_URL ? (
        <Alert severity="warning" data-testid="mcp-not-configured">
          {t('mcp_not_configured')}
        </Alert>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
          <Paper
            elevation={0}
            sx={{
              p: 2.5,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 2,
            }}
          >
            <Typography
              variant="h6"
              component="h2"
              sx={{ fontWeight: 600, mb: 0.5 }}
            >
              {t('mcp_server_url')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t('mcp_server_url_description')}
            </Typography>
            <Paper
              variant="outlined"
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 1,
                px: 1.5,
                py: 1,
                bgcolor: 'action.hover',
                borderRadius: 2,
              }}
            >
              <Typography
                data-testid="mcp-server-url"
                sx={{
                  flex: 1,
                  minWidth: 0,
                  fontFamily: 'monospace',
                  fontSize: '0.9375rem',
                  lineHeight: 1.5,
                  overflowX: 'auto',
                  whiteSpace: 'nowrap',
                }}
              >
                {MCP_SERVER_URL}
              </Typography>
              <CopyButton value={MCP_SERVER_URL} testId="mcp-server-url-copy" />
            </Paper>
          </Paper>

          <Alert severity="info" data-testid="mcp-auth-note">
            {t('mcp_auth_note')}
          </Alert>

          <Typography variant="h5" component="h2" sx={{ fontWeight: 600 }}>
            {t('mcp_setup_title')}
          </Typography>

          <ClientSection
            title="Cursor"
            testId="mcp-client-cursor"
            steps={[
              t('mcp_cursor_step_1'),
              t('mcp_cursor_step_2'),
              t('mcp_cursor_step_3'),
            ]}
          >
            <CodeBlock code={mcpJsonSnippet} testId="mcp-snippet-cursor" />
          </ClientSection>

          <ClientSection
            title="Claude Code"
            testId="mcp-client-claude-code"
            steps={[t('mcp_claude_code_step_1'), t('mcp_claude_code_step_2')]}
          >
            <CodeBlock code={claudeCodeCommand} testId="mcp-snippet-claude-code" />
          </ClientSection>

          <ClientSection
            title={t('mcp_other_clients')}
            testId="mcp-client-other"
            steps={[t('mcp_other_clients_description')]}
          >
            <CodeBlock code={mcpRemoteSnippet} testId="mcp-snippet-other" />
          </ClientSection>
        </Box>
      )}
    </Box>
  );
}
