import React from 'react';
import ReactDOM from 'react-dom/client';
import { i18nReady } from './i18n';
import App from './app/App';
import './styles/index.css';

// Wait for a saved es/de choice to load its strings, so the first paint isn't English.
void i18nReady.then(() => {
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
