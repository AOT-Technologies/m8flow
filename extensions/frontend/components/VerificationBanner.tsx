/**
 * Verification Banner Component
 * 
 * Dev-only banner that confirms M8Flow extensions are active
 */

import React, { useState } from 'react';
import { Alert, AlertTitle, IconButton, Collapse } from '@mui/material';
import { Close as CloseIcon } from '@mui/icons-material';

export const VerificationBanner: React.FC = () => {
  // Persist the closed state in localStorage so it doesn't reappear on navigation
  const [open, setOpen] = useState(() => {
    const stored = localStorage.getItem('m8flow-verification-banner-closed');
    return stored !== 'true'; // Show if not explicitly closed
  });
  
  // Only show in development
  if (import.meta.env.PROD) {
    return null;
  }
  
  const handleClose = () => {
    setOpen(false);
    localStorage.setItem('m8flow-verification-banner-closed', 'true');
  };
  
  return (
    <Collapse in={open}>
      <Alert
        severity="success"
        action={
          <IconButton
            aria-label="close"
            color="inherit"
            size="small"
            onClick={handleClose}
          >
            <CloseIcon fontSize="inherit" />
          </IconButton>
        }
        sx={{ mb: 2 }}
      >
        <AlertTitle>M8Flow Extensions Active!</AlertTitle>
        Extension system is loaded and working correctly.
      </Alert>
    </Collapse>
  );
};

export default VerificationBanner;
