import React from 'react';
import * as ReactDOMClient from 'react-dom/client';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { wrapWithExtensions } from './runtime/wrapper';

// Import upstream App WITHOUT modifying it
import UpstreamApp from '@spiff/App';

// Import upstream styles
import '@spiff/index.scss';
import '@spiff/index.css';
import '@spiff/i18n';

/**
 * M8Flow Extensions Entry Point
 * 
 * This file wraps the upstream SpiffWorkflow App with M8Flow extensions
 * without modifying any upstream code.
 */

// @ts-expect-error TS(2345) FIXME: Argument of type 'HTMLElement | null' is not assig... Remove this comment to see the full error message
const root = ReactDOMClient.createRoot(document.getElementById('root'));

/**
 * MUI theme configuration (matching upstream)
 */
const defaultTheme = createTheme();
const overrideTheme = createTheme({
  components: {
    MuiTooltip: {
      styleOverrides: {
        arrow: {
          '&::before': {
            color: '#F5F5F5',
            border: '1px solid grey',
          },
        },
        tooltip: {
          fontSize: '.8em',
          color: 'black',
          backgroundColor: '#F5F5F5',
          padding: '5px',
          border: '1px solid  grey',
        },
      },
    },
  },
});

// Wrap the upstream app with M8Flow extensions
const M8FlowApp = wrapWithExtensions(UpstreamApp);

const doRender = () => {
  root.render(
    <React.StrictMode>
      <ThemeProvider theme={defaultTheme}>
        <ThemeProvider theme={overrideTheme}>
          <M8FlowApp />
        </ThemeProvider>
      </ThemeProvider>
    </React.StrictMode>,
  );
};

doRender();
