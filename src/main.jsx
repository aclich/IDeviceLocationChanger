import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { initBackend } from './utils/backendClient';

// Initialize unified backend client (HTTP + SSE)
// Works for both Electron and Browser modes
// Must await since Electron URL retrieval is async
initBackend().then(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
