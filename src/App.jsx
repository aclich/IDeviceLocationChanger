import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
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
import { getEmojiPool, pickEmoji } from './utils/statusEmoji';
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
    badgeMap,
    deviceSwitchLoading,
    seedBadges,
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

  // Seed badge map on initial load
  useEffect(() => {
    seedBadges();
  }, [seedBadges]);

  const [pendingLocation, setPendingLocation] = useState(null);
  const [showDebug, setShowDebug] = useState(false);
  const [showFavoritesManager, setShowFavoritesManager] = useState(false);
  const [flyToLocation, setFlyToLocation] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [controlPanelMode, setControlPanelMode] = useState(null);

  // Wrap selectDevice to handle auto-mode switch, speed, and map fly
  const selectDevice = useCallback(async (deviceId) => {
    const response = await selectDeviceRaw(deviceId);
    if (response?.result) {
      const state = response.result;

      // Auto UI mode switch based on device state
      if (state.route || state.routeCruise) {
        setRouteMode(true);
        setControlPanelMode('route');
      } else if (state.cruise) {
        setRouteMode(false);
        setControlPanelMode('cruise');
      }
      // Idle device → keep current mode (no change)

      // Update speed from device's active speed
      if (state.cruise?.speedKmh) {
        setSpeed(state.cruise.speedKmh);
      } else if (state.routeCruise?.speedKmh) {
        setSpeed(state.routeCruise.speedKmh);
      }
      // Else: keep current slider value

      // Fly map to the device's location
      const loc = state.location;
      if (loc) {
        setFlyToLocation({ latitude: loc.latitude, longitude: loc.longitude, timestamp: Date.now() });
      }
    }
    return response;
  }, [selectDeviceRaw, setRouteMode, setSpeed]);

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
    setControlPanelMode(null); // Clear forced mode on manual change

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

  // Determine status bar mode for emoji selection
  const statusMode = useMemo(() => {
    if (!selectedDevice) return 'noDevice';
    if (isRouteCruising && isRoutePaused) return 'routePaused';
    if (isRouteCruising) return 'routeCruising';
    if (isCruising && cruiseInfo?.isPaused) return 'paused';
    if (isCruising) return 'cruising';
    if (location) return 'idleWithLocation';
    return 'idle';
  }, [selectedDevice, isRouteCruising, isRoutePaused, isCruising, cruiseInfo?.isPaused, location]);

  // Get current emoji pool and compute a stable pool key for change detection
  const emojiPool = useMemo(() => getEmojiPool(statusMode, speed, location?.latitude ?? 0), [statusMode, speed, location?.latitude]);
  const poolKey = useMemo(() => emojiPool.join(''), [emojiPool]);

  // Emoji state with 30s rotation
  const [statusEmoji, setStatusEmoji] = useState(() => pickEmoji(getEmojiPool('noDevice')));
  const poolKeyRef = useRef(poolKey);

  useEffect(() => {
    // Pick new emoji immediately when pool changes
    if (poolKeyRef.current !== poolKey) {
      poolKeyRef.current = poolKey;
      setStatusEmoji(pickEmoji(emojiPool));
    }
    // Set up 30s rotation
    const timer = setInterval(() => {
      setStatusEmoji(pickEmoji(emojiPool));
    }, 30000);
    return () => clearInterval(timer);
  }, [poolKey, emojiPool]);

  // Build contextual status bar text
  const statusBarText = useMemo(() => {
    const name = selectedDevice?.name;
    switch (statusMode) {
      case 'noDevice':
        return 'No device selected';
      case 'idle':
        return name;
      case 'idleWithLocation':
        return `${name} · ${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)}`;
      case 'cruising':
        return cruiseInfo
          ? `${name} · ${cruiseInfo.distance} rem · ETA ${cruiseInfo.eta} · ${speed.toFixed(1)} km/h`
          : name;
      case 'paused':
        return cruiseInfo
          ? `${name} · Paused · ${cruiseInfo.distance} rem · ETA ${cruiseInfo.eta} · ${speed.toFixed(1)} km/h`
          : name;
      case 'routeCruising':
        if (!routeProgressInfo) return name;
        return `${name} · Seg ${routeProgressInfo.currentSegment}/${routeProgressInfo.totalSegments} · ${routeProgressInfo.remainingKm < 1 ? `${(routeProgressInfo.remainingKm * 1000).toFixed(0)}m` : `${routeProgressInfo.remainingKm.toFixed(1)}km`} rem · ${speed.toFixed(1)} km/h`;
      case 'routePaused':
        if (!routeProgressInfo) return name;
        return `${name} · Route Paused · Seg ${routeProgressInfo.currentSegment}/${routeProgressInfo.totalSegments} · ${routeProgressInfo.remainingKm < 1 ? `${(routeProgressInfo.remainingKm * 1000).toFixed(0)}m` : `${routeProgressInfo.remainingKm.toFixed(1)}km`} rem · ${speed.toFixed(1)} km/h`;
      default:
        return name || 'No device selected';
    }
  }, [statusMode, selectedDevice?.name, location, cruiseInfo, speed, routeProgressInfo]);

  // Bounce-scroll: measure overflow and set CSS custom property
  const statusBarRef = useRef(null);
  const statusTextRef = useRef(null);

  useEffect(() => {
    const container = statusBarRef.current;
    const text = statusTextRef.current;
    if (!container || !text) return;

    const measure = () => {
      const overflow = text.scrollWidth - container.clientWidth;
      if (overflow > 0) {
        text.style.setProperty('--scroll-distance', `-${overflow}px`);
        text.classList.add('bounce-scroll');
      } else {
        text.classList.remove('bounce-scroll');
      }
    };

    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(container);
    observer.observe(text);

    return () => observer.disconnect();
  }, [statusBarText, statusEmoji]);

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
          {/* Loading overlay during device switch */}
          {deviceSwitchLoading && (
            <div className="device-switch-overlay">
              <div className="device-switch-spinner">Switching device...</div>
            </div>
          )}

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
              badgeMap={badgeMap}
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
              externalMode={controlPanelMode}
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
        <div className="status-bar" ref={statusBarRef}>
          <span className="status-bar-text" ref={statusTextRef}>
            {statusEmoji} {statusBarText}
          </span>
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
