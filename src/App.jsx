import { useState, useCallback, useMemo } from 'react';
import { useBackend } from './hooks/useBackend';
import { useMovement } from './hooks/useMovement';
import { useFavorites } from './hooks/useFavorites';
import { MapWidget } from './components/MapWidget';
import { DevicePanel } from './components/DevicePanel';
import { ControlPanel } from './components/ControlPanel';
import { FavoritesManager } from './components/FavoritesManager';
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
    cruiseStatus,
    error,
    isLoading,
    isConnected,
    isBrowserMode,
    listDevices,
    selectDevice: selectDeviceRaw,
    setLocation,
    clearLocation,
    getLastLocation,
    startTunnel,
    stopTunnel,
    clearError,
    // Cruise operations (run in backend)
    startCruise: backendStartCruise,
    stopCruise: backendStopCruise,
    pauseCruise,
    resumeCruise,
    setCruiseSpeed,
  } = useBackend();

  // Wrap selectDevice to restore last location
  const selectDevice = useCallback(async (deviceId) => {
    const response = await selectDeviceRaw(deviceId);
    if (response?.result?.device) {
      // Try to restore last location for this device
      const lastLocResponse = await getLastLocation(deviceId);
      if (lastLocResponse?.result?.success) {
        const { latitude, longitude } = lastLocResponse.result;
        // Set it as pending location and fly to it
        setPendingLocation({ latitude, longitude });
        setFlyToLocation({ latitude, longitude, timestamp: Date.now() });
      }
    }
    return response;
  }, [selectDeviceRaw, getLastLocation]);

  // Joystick movement control (runs in frontend - requires real-time input)
  const {
    isMoving: isJoystickMoving,
    speed,
    updateJoystick,
    releaseJoystick,
    setSpeed,
  } = useMovement({ location, setLocation });

  // Derive cruise state from backend
  const isCruising = cruiseStatus?.state === 'running' || cruiseStatus?.state === 'paused';
  const isMoving = isJoystickMoving || isCruising;
  const cruiseTarget = cruiseStatus?.target || null;

  // Favorites management
  const {
    favorites,
    isLoading: favoritesLoading,
    addFavorite,
    updateFavorite,
    deleteFavorite,
    importFavorites,
  } = useFavorites();

  const [pendingLocation, setPendingLocation] = useState(null);
  const [showDebug, setShowDebug] = useState(false);
  const [showFavoritesManager, setShowFavoritesManager] = useState(false);
  const [flyToLocation, setFlyToLocation] = useState(null);

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

  const handleStartCruise = useCallback(async (target) => {
    if (!location) {
      console.warn('Cannot start cruise: no location set');
      return;
    }
    const response = await backendStartCruise(location, target, speed);
    if (response?.result?.success) {
      setPendingLocation(null); // Clear pending after starting cruise
    }
  }, [location, speed, backendStartCruise]);

  const handleStopCruise = useCallback(() => {
    backendStopCruise();
  }, [backendStopCruise]);

  const handlePauseCruise = useCallback(() => {
    pauseCruise();
  }, [pauseCruise]);

  const handleResumeCruise = useCallback(() => {
    resumeCruise();
  }, [resumeCruise]);

  // Update cruise speed when slider changes during cruise
  const handleSpeedChange = useCallback((newSpeed) => {
    setSpeed(newSpeed);
    if (isCruising) {
      setCruiseSpeed(newSpeed);
    }
  }, [setSpeed, isCruising, setCruiseSpeed]);

  // Favorites handlers
  const handleFavoriteSelect = useCallback((favorite) => {
    const loc = { latitude: favorite.latitude, longitude: favorite.longitude };
    setPendingLocation(loc);
    // Fly map to the selected favorite
    setFlyToLocation({ ...loc, timestamp: Date.now() });
  }, []);

  const handleSaveFavorite = useCallback(async () => {
    // Prefer saving selected (pending) location, fall back to current location
    const locToSave = pendingLocation || location;
    if (locToSave) {
      await addFavorite(locToSave.latitude, locToSave.longitude);
    }
  }, [pendingLocation, location, addFavorite]);

  // Calculate ETA for status bar
  const cruiseInfo = useMemo(() => {
    if (!isCruising || !cruiseStatus) return null;

    const distanceKm = cruiseStatus.remainingKm || 0;
    const speedKmh = cruiseStatus.speedKmh || speed;

    if (speedKmh <= 0) return null;

    const timeHours = distanceKm / speedKmh;
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

    const isPaused = cruiseStatus.state === 'paused';

    return { eta, distance: dist, isPaused };
  }, [isCruising, cruiseStatus, speed]);

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
        {isBrowserMode && (
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot"></span>
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        )}
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
                flyTo={flyToLocation}
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
                cruiseStatus={cruiseStatus}
                onSetLocation={handleSetLocation}
                onClearLocation={handleClearLocation}
                onStartCruise={handleStartCruise}
                onStopCruise={handleStopCruise}
                onPauseCruise={handlePauseCruise}
                onResumeCruise={handleResumeCruise}
                onJoystickMove={updateJoystick}
                onJoystickRelease={releaseJoystick}
                onSpeedChange={handleSpeedChange}
                onDirectInput={handleDirectInput}
                favorites={favorites}
                favoritesLoading={favoritesLoading}
                onFavoriteSelect={handleFavoriteSelect}
                onSaveFavorite={handleSaveFavorite}
                onManageFavorites={() => setShowFavoritesManager(true)}
                canSaveLocation={!!(pendingLocation || location)}
                hasSelectedLocation={!!pendingLocation}
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
            {isCruising && cruiseInfo && (
              <span>
                {cruiseInfo.isPaused ? 'Paused' : 'Cruising'}: {cruiseInfo.distance} remaining • ETA {cruiseInfo.eta} • {speed.toFixed(1)} km/h
              </span>
            )}
          </div>
        </>
      )}

      {/* Favorites Manager Modal */}
      <FavoritesManager
        isOpen={showFavoritesManager}
        onClose={() => setShowFavoritesManager(false)}
        favorites={favorites}
        isLoading={favoritesLoading}
        onUpdate={updateFavorite}
        onDelete={deleteFavorite}
        onImport={importFavorites}
      />
    </div>
  );
}

export default App;
