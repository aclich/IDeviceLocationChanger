import { useEffect } from 'react';

// Tunnel status constants matching backend TunnelStatus enum
const TUNNEL_STATUS = {
  NO_TUNNEL: 'no_tunnel',
  DISCOVERING: 'discovering',
  CONNECTED: 'connected',
  STALE: 'stale',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

export function DevicePanel({
  devices,
  selectedDevice,
  onSelectDevice,
  onRefresh,
  isLoading,
  tunnelStatus,
  onStartTunnel,
  onStopTunnel,
}) {
  // Auto-refresh devices on mount
  useEffect(() => {
    onRefresh();
  }, []);

  const getDeviceIcon = (device) => {
    if (device.type === 'simulator') return '📱';
    if (device.connectionType === 'WiFi') return '📶';
    return '🔌';
  };

  const getDeviceSubtitle = (device) => {
    if (device.type === 'simulator') return 'Simulator';
    return `${device.productName || device.productType || 'Physical'} (${device.connectionType})`;
  };

  // Get address and port from tunnelStatus (handles both legacy and new formats)
  const getAddressPort = () => {
    // New format: tunnelInfo is nested object
    if (tunnelStatus.tunnelInfo) {
      return {
        address: tunnelStatus.tunnelInfo.address,
        port: tunnelStatus.tunnelInfo.port,
      };
    }
    // Legacy format: address and port at top level
    return {
      address: tunnelStatus.address,
      port: tunnelStatus.port,
    };
  };

  // Get tunnel status display info
  const getTunnelStatusInfo = () => {
    const status = tunnelStatus.status || (tunnelStatus.running ? TUNNEL_STATUS.CONNECTED : TUNNEL_STATUS.NO_TUNNEL);
    const { address, port } = getAddressPort();

    switch (status) {
      case TUNNEL_STATUS.CONNECTED:
        return {
          className: 'active',
          text: address && port ? `Connected (${address}:${port})` : 'Connected',
          color: '#4ade80', // green
        };
      case TUNNEL_STATUS.DISCOVERING:
        return {
          className: 'discovering',
          text: 'Discovering...',
          color: '#fbbf24', // yellow
        };
      case TUNNEL_STATUS.STALE:
        return {
          className: 'stale',
          text: 'Reconnecting...',
          color: '#fbbf24', // yellow
        };
      case TUNNEL_STATUS.DISCONNECTED:
        return {
          className: 'disconnected',
          text: tunnelStatus.error || 'Disconnected',
          color: '#f87171', // red
        };
      case TUNNEL_STATUS.ERROR:
        return {
          className: 'error',
          text: tunnelStatus.error || 'Error',
          color: '#f87171', // red
        };
      case TUNNEL_STATUS.NO_TUNNEL:
      default:
        return {
          className: '',
          text: tunnelStatus.message || 'Not started',
          color: '#6b7280', // gray
        };
    }
  };

  const statusInfo = getTunnelStatusInfo();
  const isConnected = tunnelStatus.status === TUNNEL_STATUS.CONNECTED ||
    (tunnelStatus.running && !tunnelStatus.status);

  return (
    <div className="device-panel">
      <div className="panel-header">
        <h3>Devices</h3>
        <button onClick={onRefresh} disabled={isLoading} className="btn-icon">
          {isLoading ? '⏳' : '🔄'}
        </button>
      </div>

      <div className="device-list">
        {devices.length === 0 ? (
          <div className="empty-state">
            {isLoading ? 'Scanning...' : 'No devices found'}
          </div>
        ) : (
          devices.map((device) => (
            <div
              key={device.id}
              className={`device-item ${selectedDevice?.id === device.id ? 'selected' : ''}`}
              onClick={() => onSelectDevice(device.id)}
            >
              <span className="device-icon">{getDeviceIcon(device)}</span>
              <div className="device-info">
                <div className="device-name">{device.name}</div>
                <div className="device-subtitle">{getDeviceSubtitle(device)}</div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="tunnel-section">
        <div className="panel-header">
          <h4>iOS 17+ Tunnel</h4>
        </div>
        <div className="tunnel-status">
          <span
            className={`status-dot ${statusInfo.className}`}
            style={{ backgroundColor: statusInfo.color }}
          />
          <span className="status-text">{statusInfo.text}</span>
        </div>
        <div className="tunnel-buttons">
          <button
            className={`btn ${isConnected ? 'btn-danger' : 'btn-primary'}`}
            onClick={isConnected ? () => onStopTunnel(selectedDevice?.id) : () => onStartTunnel(selectedDevice?.id)}
            disabled={isLoading}
          >
            {isConnected ? 'Stop Tunnel' : `Start Tunnel${selectedDevice ? ` (${selectedDevice.name})` : ''}`}
          </button>
        </div>
        {!selectedDevice && !isConnected && (
          <div className="tunnel-hint">Select a device first, or start tunnel for all devices</div>
        )}
      </div>
    </div>
  );
}
