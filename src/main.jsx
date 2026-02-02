import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { initBrowserBackend } from './utils/browserBackend';

// Initialize browser backend if not running in Electron
initBrowserBackend();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
