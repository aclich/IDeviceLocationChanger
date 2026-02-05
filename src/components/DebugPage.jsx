import { useState, useRef, useEffect, useCallback } from 'react';

export function DebugPage() {
  const [input, setInput] = useState('{"method": "listDevices", "params": {}}');
  const [outputs, setOutputs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const outputRef = useRef(null);
  const logRef = useRef(null);
  const requestIdRef = useRef(0);

  // Backend address configuration
  const [backendHost, setBackendHost] = useState('127.0.0.1');
  const [backendPort, setBackendPort] = useState('8765');
  const [isCustomBackend, setIsCustomBackend] = useState(false);

  // Check backend connection and load saved backend address
  useEffect(() => {
    setIsConnected(!!window.backend);

    // Load current backend URL
    if (window.backend?.getBaseUrl) {
      try {
        const currentUrl = window.backend.getBaseUrl();
        const url = new URL(currentUrl);
        setBackendHost(url.hostname);
        setBackendPort(url.port || '8765');
        // Check if it's a custom URL (stored in localStorage)
        const storedUrl = window.localStorage.getItem('backendUrl');
        setIsCustomBackend(!!storedUrl);
      } catch (e) {
        console.error('Failed to parse backend URL:', e);
      }
    }
  }, []);

  // Auto-scroll outputs and logs
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputs]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  // Listen for backend events
  useEffect(() => {
    if (!window.backend) return;

    const cleanup = window.backend.onEvent((message) => {
      const timestamp = new Date().toLocaleTimeString();
      setLogs(prev => [...prev, {
        time: timestamp,
        type: 'event',
        content: message
      }]);
    });

    return cleanup;
  }, []);

  const addLog = useCallback((type, content) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { time: timestamp, type, content }]);
  }, []);

  const handleSend = useCallback(async () => {
    if (!window.backend) {
      addLog('error', 'Backend not connected');
      return;
    }

    let request;
    try {
      request = JSON.parse(input);
    } catch (e) {
      addLog('error', `Invalid JSON: ${e.message}`);
      return;
    }

    const { method, params = {} } = request;
    if (!method) {
      addLog('error', 'Missing "method" field');
      return;
    }

    const requestId = ++requestIdRef.current;
    const timestamp = new Date().toLocaleTimeString();

    // Log the request
    addLog('request', { method, params });

    // Add to output
    setOutputs(prev => [...prev, {
      id: requestId,
      time: timestamp,
      type: 'request',
      method,
      params,
      response: null,
      pending: true
    }]);

    try {
      const startTime = performance.now();
      const response = await window.backend.send(method, params);
      const duration = Math.round(performance.now() - startTime);

      // Log the response
      addLog('response', { method, duration: `${duration}ms`, response });

      // Update output with response
      setOutputs(prev => prev.map(item =>
        item.id === requestId
          ? { ...item, response, duration, pending: false }
          : item
      ));
    } catch (error) {
      addLog('error', { method, error: error.message });

      setOutputs(prev => prev.map(item =>
        item.id === requestId
          ? { ...item, response: { error: error.message }, pending: false }
          : item
      ));
    }
  }, [input, addLog]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSend();
    }
  }, [handleSend]);

  const clearOutputs = useCallback(() => setOutputs([]), []);
  const clearLogs = useCallback(() => setLogs([]), []);

  // Handle backend address change
  const handleBackendConnect = useCallback(() => {
    if (!window.backend?.setBaseUrl) {
      addLog('error', 'Backend client does not support URL change');
      return;
    }

    const newUrl = `http://${backendHost}:${backendPort}`;
    window.backend.setBaseUrl(newUrl);
    setIsCustomBackend(true);
    addLog('info', `Connected to ${newUrl}`);

    // Test connection
    window.backend.checkHealth().then((healthy) => {
      if (healthy) {
        addLog('info', 'Backend health check passed');
        setIsConnected(true);
      } else {
        addLog('error', 'Backend health check failed');
        setIsConnected(false);
      }
    });
  }, [backendHost, backendPort, addLog]);

  const handleBackendReset = useCallback(() => {
    if (window.backend?.clearCustomUrl) {
      window.backend.clearCustomUrl();
      addLog('info', 'Custom backend URL cleared. Reload the page to use default.');
      setIsCustomBackend(false);
    }
  }, [addLog]);

  const presetCommands = [
    { label: 'List Devices', cmd: '{"method": "listDevices", "params": {}}' },
    { label: 'Select Device', cmd: '{"method": "selectDevice", "params": {"deviceId": "DEVICE_ID_HERE"}}' },
    { label: 'Set Location', cmd: '{"method": "setLocation", "params": {"latitude": 25.0330, "longitude": 121.5654}}' },
    { label: 'Clear Location', cmd: '{"method": "clearLocation", "params": {}}' },
    { label: 'Start Tunnel', cmd: '{"method": "startTunnel", "params": {}}' },
    { label: 'Stop Tunnel', cmd: '{"method": "stopTunnel", "params": {}}' },
    { label: 'Tunnel Status', cmd: '{"method": "getTunnelStatus", "params": {}}' },
  ];

  return (
    <div className="debug-page">
      <div className="debug-header">
        <h2>Debug Console</h2>
        <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Backend Address Configuration */}
      <div className="debug-backend-config">
        <label>Backend:</label>
        <input
          type="text"
          className="backend-host-input"
          value={backendHost}
          onChange={(e) => setBackendHost(e.target.value)}
          placeholder="Host"
        />
        <span className="backend-port-separator">:</span>
        <input
          type="text"
          className="backend-port-input"
          value={backendPort}
          onChange={(e) => setBackendPort(e.target.value)}
          placeholder="Port"
        />
        <button className="backend-connect-btn" onClick={handleBackendConnect}>
          Connect
        </button>
        {isCustomBackend && (
          <button className="backend-reset-btn" onClick={handleBackendReset}>
            Reset
          </button>
        )}
      </div>

      {/* Preset Commands */}
      <div className="debug-presets">
        {presetCommands.map((preset, i) => (
          <button
            key={i}
            className="preset-btn"
            onClick={() => setInput(preset.cmd)}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* Input Section */}
      <div className="debug-input-section">
        <label>Request JSON:</label>
        <textarea
          className="debug-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder='{"method": "methodName", "params": {}}'
          rows={4}
        />
        <div className="debug-input-actions">
          <button className="send-btn" onClick={handleSend}>
            Send (Cmd+Enter)
          </button>
        </div>
      </div>

      {/* Output Section */}
      <div className="debug-output-section">
        <div className="section-header">
          <label>Responses:</label>
          <button className="clear-btn" onClick={clearOutputs}>Clear</button>
        </div>
        <div className="debug-output" ref={outputRef}>
          {outputs.length === 0 ? (
            <div className="empty-state">No requests yet</div>
          ) : (
            outputs.map((item) => (
              <div key={item.id} className={`output-item ${item.pending ? 'pending' : ''}`}>
                <div className="output-header">
                  <span className="output-time">{item.time}</span>
                  <span className="output-method">{item.method}</span>
                  {item.duration && <span className="output-duration">{item.duration}ms</span>}
                  {item.pending && <span className="output-pending">pending...</span>}
                </div>
                <div className="output-request">
                  <span className="label">Request:</span>
                  <pre>{JSON.stringify(item.params, null, 2)}</pre>
                </div>
                {item.response && (
                  <div className={`output-response ${item.response.error ? 'error' : 'success'}`}>
                    <span className="label">Response:</span>
                    <pre>{JSON.stringify(item.response, null, 2)}</pre>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Log Section */}
      <div className="debug-log-section">
        <div className="section-header">
          <label>Logs & Events:</label>
          <button className="clear-btn" onClick={clearLogs}>Clear</button>
        </div>
        <div className="debug-log" ref={logRef}>
          {logs.length === 0 ? (
            <div className="empty-state">No logs yet</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className={`log-item log-${log.type}`}>
                <span className="log-time">{log.time}</span>
                <span className={`log-type ${log.type}`}>{log.type.toUpperCase()}</span>
                <span className="log-content">
                  {typeof log.content === 'string'
                    ? log.content
                    : JSON.stringify(log.content)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
