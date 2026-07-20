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
