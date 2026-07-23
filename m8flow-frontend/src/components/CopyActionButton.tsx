import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Tooltip } from '@mui/material';
import {
  Check as CheckIcon,
  ContentCopy as ContentCopyIcon,
} from '@mui/icons-material';

const srOnly = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  p: 0,
  m: '-1px',
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
  border: 0,
} as const;

export type CopyActionButtonProps = {
  value: string;
  label: string;
  testId: string;
  variant?: 'outlined' | 'contained';
  fullWidth?: boolean;
};

/**
 * Copy text to the clipboard, resolving to whether it succeeded (never throws).
 * Prefers the async Clipboard API (secure contexts) and falls back to a hidden
 * textarea + execCommand for HTTP/non-secure or older browsers where
 * navigator.clipboard is undefined or rejects.
 */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // fall through to the legacy fallback below
    }
  }

  try {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Copy-to-clipboard button with transient "copied" feedback. The label stays constant
 * (only the icon swaps) so the row does not reflow, and an aria-live region announces
 * the copy for screen readers.
 */
export default function CopyActionButton({
  value,
  label,
  testId,
  variant = 'outlined',
  fullWidth,
}: CopyActionButtonProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  const handleCopy = async () => {
    const succeeded = await copyText(value);
    if (succeeded) {
      setFailed(false);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } else {
      setCopied(false);
      setFailed(true);
      setTimeout(() => setFailed(false), 2000);
    }
  };

  return (
    <>
      <Tooltip
        title={failed ? t('copy_failed') : t('copied_to_clipboard')}
        open={copied || failed}
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
        {copied ? t('copied_to_clipboard') : failed ? t('copy_failed') : ''}
      </Box>
    </>
  );
}
