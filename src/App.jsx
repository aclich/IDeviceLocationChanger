import { useState, useCallback, useMemo } from 'react';
import { useBackend } from './hooks/useBackend';
import { useMovement } from './hooks/useMovement';
import { MapWidget } from './components/MapWidget';
import { DevicePanel } from './components/DevicePanel';
import { ControlPanel } from './components/ControlPanel';
import { DebugPage } from './components/DebugPage';
import { distanceBetween } from './utils/coordinateCalculator';
import './styles/App.css';
import './styles/DebugPage.css';

function App() {
  // Backend communication
  const {
    devices,
    selectedDevice,
    location,
    tunnelStatus,
    error,
    isLoading,
    listDevices,
    selectDevice,
    setLocation,
    clearLocation,
    startTunnel,
    stopTunnel,
    clearError,
  } = useBackend();

  // Movement control (cruise/joystick) - runs in frontend
  const {
    isMoving,
    speed,
    cruiseTarget,
    startCruise,
    stopCruise,
    updateJoystick,
    releaseJoystick,
    setSpeed,
  } = useMovement({ location, setLocation });

  const [pendingLocation, setPendingLocation] = useState(null);
  const [showDebug, setShowDebug] = useState(false);

  const handleMapClick = useCallback((lat, lng) => {
    setPendingLocation({ latitude: lat, longitude: lng });
  }, []);

  const handleSetLocation = useCallback(async () => {
    if (pendingLocation) {
      await setLocation(pendingLocation.latitude, pendingLocation.longitude);
      setPendingLocation(null);
    }
  }, [pendingLocation, setLocation]);

  const handleClearLocation = useCallback(async () => {
    await clearLocation();
    setPendingLocation(null);
  }, [clearLocation]);

  const handleDirectInput = useCallback(async (lat, lng) => {
    await setLocation(lat, lng);
  }, [setLocation]);

  const handleStartCruise = useCallback((target) => {
    if (startCruise(target)) {
      setPendingLocation(null); // Clear pending after starting cruise
    }
  }, [startCruise]);

  const handleStopCruise = useCallback(() => {
    stopCruise();
  }, [stopCruise]);

  // Calculate ETA for status bar
  const cruiseInfo = useMemo(() => {
    if (!isMoving || !location || !cruiseTarget || speed <= 0) return null;

    const distanceKm = distanceBetween(
      location.latitude,
      location.longitude,
      cruiseTarget.latitude,
      cruiseTarget.longitude
    );

    const timeHours = distanceKm / speed;
    const timeSeconds = timeHours * 3600;

    let eta;
    if (timeSeconds < 60) {
      eta = `${Math.ceil(timeSeconds)}s`;
    } else if (timeSeconds < 3600) {
      const mins = Math.floor(timeSeconds / 60);
      const secs = Math.ceil(timeSeconds % 60);
      eta = `${mins}m ${secs}s`;
    } else {
      const hours = Math.floor(timeHours);
      const mins = Math.ceil((timeHours - hours) * 60);
      eta = `${hours}h ${mins}m`;
    }

    const dist = distanceKm < 1 ? `${(distanceKm * 1000).toFixed(0)}m` : `${distanceKm.toFixed(2)}km`;

    return { eta, distance: dist };
  }, [isMoving, location, cruiseTarget, speed]);

  return (
    <div className="app">
      {/* Titlebar drag region for macOS */}
      <div className="titlebar">
        <div className="titlebar-tabs">
          <button
            className={`titlebar-tab ${!showDebug ? 'active' : ''}`}
            onClick={() => setShowDebug(false)}
          >
            Simulator
          </button>
          <button
            className={`titlebar-tab ${showDebug ? 'active' : ''}`}
            onClick={() => setShowDebug(true)}
          >
            Debug
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={clearError}>×</button>
        </div>
      )}

      {showDebug ? (
        <DebugPage />
      ) : (
        <>
          <div className="main-content">
            {/* Left side - Map */}
            <div className="map-container">
              <MapWidget
                location={location}
                pendingLocation={pendingLocation}
                cruiseTarget={cruiseTarget}
                onLocationSelect={handleMapClick}
              />
            </div>

            {/* Right side - Controls */}
            <div className="sidebar">
              <DevicePanel
                devices={devices}
                selectedDevice={selectedDevice}
                onSelectDevice={selectDevice}
                onRefresh={listDevices}
                isLoading={isLoading}
                tunnelStatus={tunnelStatus}
                onStartTunnel={startTunnel}
                onStopTunnel={stopTunnel}
              />

              <ControlPanel
                location={location}
                pendingLocation={pendingLocation}
                selectedDevice={selectedDevice}
                isMoving={isMoving}
                speed={speed}
                cruiseTarget={cruiseTarget}
                onSetLocation={handleSetLocation}
                onClearLocation={handleClearLocation}
                onStartCruise={handleStartCruise}
                onStopCruise={handleStopCruise}
                onJoystickMove={updateJoystick}
                onJoystickRelease={releaseJoystick}
                onSpeedChange={setSpeed}
                onDirectInput={handleDirectInput}
              />
            </div>
          </div>

          {/* Status bar */}
          <div className="status-bar">
            <span>
              {selectedDevice
                ? `Selected: ${selectedDevice.name}`
                : 'No device selected'}
            </span>
            {location && (
              <span>
                Location: {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}
              </span>
            )}
            {isMoving && cruiseInfo && (
              <span>
                Cruising: {cruiseInfo.distance} remaining • ETA {cruiseInfo.eta} • {speed.toFixed(1)} km/h
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default App;
