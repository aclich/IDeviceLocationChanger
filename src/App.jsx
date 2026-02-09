import { useState, useCallback, useMemo } from 'react';
import { useBackend } from './hooks/useBackend';
import { useMovement } from './hooks/useMovement';
import { useFavorites } from './hooks/useFavorites';
import { useRouteCruise } from './hooks/useRouteCruise';
import { MapWidget } from './components/MapWidget';
import { DevicePanel } from './components/DevicePanel';
import { ControlPanel } from './components/ControlPanel';
import { RoutePanel } from './components/RoutePanel';
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
    tunneldState,
    cruiseStatus,
    error,
    isLoading,
    isConnected,
    isBrowserMode,
    listDevices,
    selectDevice: selectDeviceRaw,
    disconnectDevice,
    setLocation,
    clearLocation,
    getLastLocation,
    retryTunneld,
    clearError,
    // Cruise operations (run in backend)
    startCruise: backendStartCruise,
    stopCruise: backendStopCruise,
    pauseCruise,
    resumeCruise,
    setCruiseSpeed,
    // Route cruise operations
    routeStatus,
    routeState,
    addRouteWaypoint,
    undoRouteWaypoint,
    startRouteCruise,
    pauseRouteCruise: pauseRouteCruiseRaw,
    resumeRouteCruise: resumeRouteCruiseRaw,
    rerouteRouteCruise,
    stopRouteCruise,
    setRouteCruiseSpeed,
    clearRoute,
    setRouteLoopMode,
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

  // Route cruise mode
  const {
    routeMode,
    setRouteMode,
    routeLoading,
    isRouteCruising,
    isRoutePaused,
    waypoints: routeWaypoints,
    segments: routeSegments,
    loopMode,
    totalDistanceKm,
    hasRoute,
    progressInfo: routeProgressInfo,
    addWaypoint,
    undoWaypoint,
    startRoute,
    pauseRoute,
    resumeRoute,
    stopRoute,
    setRouteSpeed,
    toggleLoopMode,
    clearRoute: clearRouteAction,
  } = useRouteCruise({
    addRouteWaypoint,
    undoRouteWaypoint,
    startRouteCruise,
    pauseRouteCruise: pauseRouteCruiseRaw,
    resumeRouteCruise: resumeRouteCruiseRaw,
    rerouteRouteCruise,
    stopRouteCruise,
    setRouteCruiseSpeed,
    clearRoute,
    setRouteLoopMode,
    routeStatus,
    routeState,
    location,
    selectedDevice,
  });

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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

  // Handle mode changes from ControlPanel
  const handleModeChange = useCallback((newMode) => {
    const wasRouteMode = routeMode;
    setRouteMode(newMode === 'route');

    // Auto-pause route cruise when switching away from route mode
    if (wasRouteMode && newMode !== 'route' && isRouteCruising && !isRoutePaused) {
      pauseRoute();
    }
  }, [routeMode, setRouteMode, isRouteCruising, isRoutePaused, pauseRoute]);

  // Update cruise speed when slider changes during cruise
  const handleSpeedChange = useCallback((newSpeed) => {
    setSpeed(newSpeed);
    if (isCruising) {
      setCruiseSpeed(newSpeed);
    }
    if (isRouteCruising) {
      setRouteSpeed(newSpeed);
    }
  }, [setSpeed, isCruising, setCruiseSpeed, isRouteCruising, setRouteSpeed]);

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

      {/* Debug page - hidden when not active but stays mounted */}
      <div style={{ display: showDebug ? 'contents' : 'none' }}>
        <DebugPage />
      </div>

      {/* Simulator view - hidden when debug is active but stays mounted to preserve map state */}
      <div style={{ display: showDebug ? 'none' : 'contents' }}>
        <div className="main-content">
          {/* Left side - Map */}
          <div className="map-container">
            <MapWidget
              location={location}
              pendingLocation={pendingLocation}
              cruiseTarget={cruiseTarget}
              onLocationSelect={handleMapClick}
              flyTo={flyToLocation}
              routeMode={routeMode}
              routeState={routeState}
              onAddWaypoint={addWaypoint}
            />
          </div>

          {/* Right side - Controls */}
          <div className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
            <button
              className="sidebar-toggle"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            >
              {sidebarCollapsed ? '▲ Expand Controls' : '▼ Collapse Controls'}
            </button>
            <DevicePanel
              devices={devices}
              selectedDevice={selectedDevice}
              onSelectDevice={selectDevice}
              onDisconnectDevice={disconnectDevice}
              onRefresh={listDevices}
              isLoading={isLoading}
              tunnelStatus={tunnelStatus}
              tunneldState={tunneldState}
              onRetryTunneld={retryTunneld}
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
              onModeChange={handleModeChange}
              favorites={favorites}
              favoritesLoading={favoritesLoading}
              onFavoriteSelect={handleFavoriteSelect}
              onSaveFavorite={handleSaveFavorite}
              onManageFavorites={() => setShowFavoritesManager(true)}
              canSaveLocation={!!(pendingLocation || location)}
              hasSelectedLocation={!!pendingLocation}
            />

            <RoutePanel
              routeMode={routeMode}
              onToggleRouteMode={() => setRouteMode(!routeMode)}
              isRouteCruising={isRouteCruising}
              isRoutePaused={isRoutePaused}
              waypoints={routeWaypoints}
              segments={routeSegments}
              loopMode={loopMode}
              totalDistanceKm={totalDistanceKm}
              hasRoute={hasRoute}
              progressInfo={routeProgressInfo}
              speed={speed}
              onStartRoute={startRoute}
              onPauseRoute={pauseRoute}
              onResumeRoute={resumeRoute}
              onStopRoute={stopRoute}
              onClearRoute={clearRouteAction}
              onUndoWaypoint={undoWaypoint}
              onToggleLoopMode={toggleLoopMode}
              selectedDevice={selectedDevice}
              routeLoading={routeLoading}
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
          {isRouteCruising && routeProgressInfo && (
            <span>
              {isRoutePaused ? 'Route Paused' : 'Route Cruising'}: Seg {routeProgressInfo.currentSegment}/{routeProgressInfo.totalSegments} • {(routeProgressInfo.remainingKm < 1 ? `${(routeProgressInfo.remainingKm * 1000).toFixed(0)}m` : `${routeProgressInfo.remainingKm.toFixed(1)}km`)} remaining
            </span>
          )}
        </div>
      </div>

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
