import { useEffect } from 'react';

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
          <span className={`status-dot ${tunnelStatus.running ? 'active' : ''}`} />
          <span className="status-text">
            {tunnelStatus.running
              ? `Running (${tunnelStatus.address}:${tunnelStatus.port})`
              : tunnelStatus.message || 'Not started'}
          </span>
        </div>
        <button
          className={`btn ${tunnelStatus.running ? 'btn-danger' : 'btn-primary'}`}
          onClick={tunnelStatus.running ? onStopTunnel : () => onStartTunnel(selectedDevice?.id)}
          disabled={isLoading}
        >
          {tunnelStatus.running ? 'Stop Tunnel' : `Start Tunnel${selectedDevice ? ` (${selectedDevice.name})` : ''}`}
        </button>
        {!selectedDevice && !tunnelStatus.running && (
          <div className="tunnel-hint">Select a device first, or start tunnel for all devices</div>
        )}
      </div>
    </div>
  );
}
