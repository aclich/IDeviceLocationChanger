import { useEffect } from 'react';

export function DevicePanel({
  devices,
  selectedDevice,
  onSelectDevice,
  onDisconnectDevice,
  onRefresh,
  isLoading,
  tunnelStatus,
  tunneldState,
  onRetryTunneld,
  badgeMap = {},
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

  // Get tunnel status display info for the selected device
  const getTunnelStatusInfo = () => {
    if (!tunnelStatus) return null;

    switch (tunnelStatus.status) {
      case 'connected':
        return {
          text: tunnelStatus.address && tunnelStatus.port
            ? `Connected (${tunnelStatus.address} ${tunnelStatus.port})`
            : 'Connected',
          color: '#4ade80', // green
        };
      case 'no_tunnel':
        return {
          text: 'No tunnel',
          color: '#6b7280', // gray
        };
      case 'tunneld_not_running':
        return {
          text: 'tunneld not running',
          color: '#f87171', // red
        };
      default:
        return null;
    }
  };

  const getBadgeInfo = (deviceId) => {
    const badge = badgeMap[deviceId];
    if (!badge) return null;
    if (badge.routeCruising) {
      if (badge.routePaused) return { text: 'route paused', className: 'badge-paused' };
      return { text: `route ${badge.routeProgress || ''}`, className: 'badge-route' };
    }
    if (badge.cruising) {
      if (badge.cruisePaused) return { text: 'paused', className: 'badge-paused' };
      return { text: 'cruising...', className: 'badge-cruising' };
    }
    return null;
  };

  const handleDisconnect = (e, device) => {
    e.stopPropagation(); // Don't trigger device selection
    if (window.confirm(`This will disconnect location simulation for ${device.name}. Continue?`)) {
      onDisconnectDevice(device.id);
    }
  };

  const tunnelInfo = getTunnelStatusInfo();
  const showTunnelStatus = selectedDevice && selectedDevice.type !== 'simulator' && tunnelInfo;

  return (
    <div className="device-panel">
      {/* Tunneld error/starting banner */}
      {tunneldState?.state === 'error' && (
        <div className="tunneld-banner tunneld-error">
          <span>tunneld not running. Physical iOS 17+ devices won't work.</span>
          <button className="btn btn-small" onClick={onRetryTunneld}>Retry</button>
        </div>
      )}
      {tunneldState?.state === 'starting' && (
        <div className="tunneld-banner tunneld-starting">
          <span>Starting tunneld...</span>
          <span className="spinner">⏳</span>
        </div>
      )}

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
          devices.map((device) => {
            const isSelected = selectedDevice?.id === device.id;
            const badge = !isSelected ? getBadgeInfo(device.id) : null;
            return (
              <div
                key={device.id}
                className={`device-item ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectDevice(device.id)}
              >
                <span className="device-icon">{getDeviceIcon(device)}</span>
                <div className="device-info">
                  <div className="device-name">{device.name}</div>
                  <div className="device-subtitle">{getDeviceSubtitle(device)}</div>
                </div>
                {badge && (
                  <span className={`device-badge ${badge.className}`}>{badge.text}</span>
                )}
                {isSelected && (
                  <button
                    className="btn-disconnect"
                    onClick={(e) => handleDisconnect(e, device)}
                    title="Disconnect device"
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Read-only tunnel status (only for physical devices) */}
      {showTunnelStatus && (
        <div className="tunnel-section">
          <div className="tunnel-status">
            <span className="tunnel-label">Tunnel</span>
            <span
              className="status-dot"
              style={{ backgroundColor: tunnelInfo.color }}
            />
            <span className="status-text">{tunnelInfo.text}</span>
          </div>
        </div>
      )}
    </div>
  );
}
