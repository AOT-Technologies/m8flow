import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import App from './app/App';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
