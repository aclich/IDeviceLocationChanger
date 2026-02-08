import { useState, useCallback, useMemo } from 'react';
import { Joystick } from './Joystick';
import { FavoritesDropdown } from './FavoritesDropdown';
import { distanceBetween } from '../utils/coordinateCalculator';

const MODES = {
  DIRECT: 'direct',
  JOYSTICK: 'joystick',
  CRUISE: 'cruise',
  ROUTE: 'route',
};

export function ControlPanel({
  location,
  pendingLocation,
  selectedDevice,
  onSetLocation,
  onClearLocation,
  onStartCruise,
  onStopCruise,
  onPauseCruise,
  onResumeCruise,
  onJoystickMove,
  onJoystickRelease,
  onSpeedChange,
  onDirectInput,
  isMoving,
  cruiseTarget,
  cruiseStatus,
  onModeChange,
  // Favorites
  favorites,
  favoritesLoading,
  onFavoriteSelect,
  onSaveFavorite,
  onManageFavorites,
  canSaveLocation,
  hasSelectedLocation,
}) {
  const [mode, setMode] = useState(MODES.DIRECT);
  const [speed, setSpeed] = useState(5);
  const [coordInput, setCoordInput] = useState('');
  const [inputError, setInputError] = useState(null);
  const [customSpeedEnabled, setCustomSpeedEnabled] = useState(false);
  const [customMaxSpeed, setCustomMaxSpeed] = useState(100);

  // Calculate effective max speed based on custom speed setting
  const effectiveMaxSpeed = customSpeedEnabled ? customMaxSpeed : 50;

  // Parse coordinate input like "24.953683, 121.551809"
  const parseCoordinates = useCallback((input) => {
    const trimmed = input.trim();
    if (!trimmed) return null;

    // Try parsing "lat, lng" format
    const match = trimmed.match(/^(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)$/);
    if (match) {
      const lat = parseFloat(match[1]);
      const lng = parseFloat(match[2]);
      if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
        return { latitude: lat, longitude: lng };
      }
    }
    return null;
  }, []);

  const handleCoordInputChange = (e) => {
    const value = e.target.value;
    setCoordInput(value);
    setInputError(null);
  };

  const handleCoordSubmit = () => {
    const coords = parseCoordinates(coordInput);
    if (coords) {
      onDirectInput?.(coords.latitude, coords.longitude);
      setInputError(null);
    } else {
      setInputError('Invalid format. Use: lat, lng (e.g., 24.953683, 121.551809)');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleCoordSubmit();
    }
  };

  const handleSpeedChange = (e) => {
    const newSpeed = parseFloat(e.target.value);
    setSpeed(newSpeed);
    onSpeedChange?.(newSpeed);
  };

  const handleModeChange = (newMode) => {
    setMode(newMode);
    onModeChange?.(newMode);
  };

  // Cruise state helpers
  const isCruising = cruiseStatus?.state === 'running' || cruiseStatus?.state === 'paused';
  const isPaused = cruiseStatus?.state === 'paused';

  const handleCruiseToggle = () => {
    if (isCruising) {
      onStopCruise?.();
    } else if (pendingLocation) {
      onStartCruise?.(pendingLocation);
    }
  };

  const handlePauseResume = () => {
    if (isPaused) {
      onResumeCruise?.();
    } else {
      onPauseCruise?.();
    }
  };

  const formatLocation = (loc) => {
    if (!loc) return 'Not set';
    const latDir = loc.latitude >= 0 ? 'N' : 'S';
    const lonDir = loc.longitude >= 0 ? 'E' : 'W';
    return `${Math.abs(loc.latitude).toFixed(6)}° ${latDir}, ${Math.abs(loc.longitude).toFixed(6)}° ${lonDir}`;
  };

  // Calculate ETA for cruise mode - use cruiseStatus if available (more accurate)
  const cruiseETA = useMemo(() => {
    // When cruising, use backend-provided remaining distance
    if (isCruising && cruiseStatus?.remainingKm !== undefined) {
      const distanceKm = cruiseStatus.remainingKm;
      const speedKmh = cruiseStatus.speedKmh || speed;
      if (speedKmh <= 0) return null;

      const timeHours = distanceKm / speedKmh;
      const timeSeconds = timeHours * 3600;

      if (timeSeconds < 60) {
        return `${Math.ceil(timeSeconds)}s`;
      } else if (timeSeconds < 3600) {
        const mins = Math.floor(timeSeconds / 60);
        const secs = Math.ceil(timeSeconds % 60);
        return `${mins}m ${secs}s`;
      } else {
        const hours = Math.floor(timeHours);
        const mins = Math.ceil((timeHours - hours) * 60);
        return `${hours}h ${mins}m`;
      }
    }

    // Fallback for preview (before cruise starts)
    if (!location || !cruiseTarget || speed <= 0) return null;

    const distanceKm = distanceBetween(
      location.latitude,
      location.longitude,
      cruiseTarget.latitude,
      cruiseTarget.longitude
    );

    const timeHours = distanceKm / speed;
    const timeSeconds = timeHours * 3600;

    if (timeSeconds < 60) {
      return `${Math.ceil(timeSeconds)}s`;
    } else if (timeSeconds < 3600) {
      const mins = Math.floor(timeSeconds / 60);
      const secs = Math.ceil(timeSeconds % 60);
      return `${mins}m ${secs}s`;
    } else {
      const hours = Math.floor(timeHours);
      const mins = Math.ceil((timeHours - hours) * 60);
      return `${hours}h ${mins}m`;
    }
  }, [isCruising, cruiseStatus, location, cruiseTarget, speed]);

  // Calculate distance to target
  const distanceToTarget = useMemo(() => {
    // When cruising, use backend-provided remaining distance
    if (isCruising && cruiseStatus?.remainingKm !== undefined) {
      const distanceKm = cruiseStatus.remainingKm;
      if (distanceKm < 1) {
        return `${(distanceKm * 1000).toFixed(0)}m`;
      }
      return `${distanceKm.toFixed(2)}km`;
    }

    // Fallback for preview
    if (!location || !cruiseTarget) return null;

    const distanceKm = distanceBetween(
      location.latitude,
      location.longitude,
      cruiseTarget.latitude,
      cruiseTarget.longitude
    );

    if (distanceKm < 1) {
      return `${(distanceKm * 1000).toFixed(0)}m`;
    }
    return `${distanceKm.toFixed(2)}km`;
  }, [isCruising, cruiseStatus, location, cruiseTarget]);

  return (
    <div className="control-panel">
      {/* Mode selector */}
      <div className="mode-selector">
        {Object.entries(MODES).map(([key, value]) => (
          <button
            key={key}
            className={`mode-btn ${mode === value ? 'active' : ''}`}
            onClick={() => handleModeChange(value)}
          >
            {key.charAt(0) + key.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Favorites dropdown */}
      <FavoritesDropdown
        favorites={favorites || []}
        isLoading={favoritesLoading}
        onSelect={onFavoriteSelect}
        onSaveCurrent={onSaveFavorite}
        onManage={onManageFavorites}
        canSaveCurrent={canSaveLocation}
        hasSelectedLocation={hasSelectedLocation}
      />

      {/* Location info */}
      <div className="location-info">
        <div className="info-row">
          <span className="label">Current:</span>
          <span className="value">{formatLocation(location)}</span>
        </div>
        {pendingLocation && (
          <div className="info-row pending">
            <span className="label">{mode === MODES.CRUISE ? 'Target:' : 'Selected:'}</span>
            <span className="value">{formatLocation(pendingLocation)}</span>
          </div>
        )}
        {isMoving && cruiseTarget && (
          <div className="info-row moving">
            <span className="label">Moving to:</span>
            <span className="value">{formatLocation(cruiseTarget)}</span>
          </div>
        )}
      </div>

      {/* Direct mode controls */}
      {mode === MODES.DIRECT && (
        <div className="direct-controls">
          {/* Coordinate input */}
          <div className="coord-input-section">
            <div className="coord-input-row">
              <input
                type="text"
                className="coord-input"
                placeholder="lat, lng (e.g., 24.953683, 121.551809)"
                value={coordInput}
                onChange={handleCoordInputChange}
                onKeyDown={handleKeyDown}
              />
              <button
                className="btn btn-primary"
                onClick={handleCoordSubmit}
                disabled={!selectedDevice || !coordInput.trim()}
              >
                Go
              </button>
            </div>
            {inputError && <div className="input-error">{inputError}</div>}
          </div>

          {/* Map selection buttons */}
          <div className="direct-buttons">
            <button
              className="btn btn-primary"
              onClick={onSetLocation}
              disabled={!selectedDevice || !pendingLocation}
            >
              Set Selected
            </button>
            <button
              className="btn btn-secondary"
              onClick={onClearLocation}
              disabled={!selectedDevice}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Movement settings (for joystick, cruise, and route) */}
      {(mode === MODES.JOYSTICK || mode === MODES.CRUISE || mode === MODES.ROUTE) && (
        <div className="settings-section">
          <div className="custom-speed-row">
            <label className="custom-speed-label">
              <input
                type="checkbox"
                checked={customSpeedEnabled}
                onChange={(e) => setCustomSpeedEnabled(e.target.checked)}
              />
              Custom max speed
            </label>
            {customSpeedEnabled && (
              <input
                type="number"
                className="custom-speed-input"
                value={customMaxSpeed}
                min="1"
                max="1000"
                onChange={(e) => {
                  const val = Math.max(1, parseInt(e.target.value) || 1);
                  setCustomMaxSpeed(val);
                  // If current speed exceeds new max, adjust it
                  if (speed > val) {
                    setSpeed(val);
                    onSpeedChange?.(val);
                  }
                }}
              />
            )}
          </div>
          <div className="setting-row">
            <label>Speed: {speed.toFixed(1)} km/h</label>
            <input
              type="range"
              min="1"
              max={effectiveMaxSpeed}
              step="0.5"
              value={speed}
              onChange={handleSpeedChange}
            />
          </div>
        </div>
      )}

      {/* Joystick mode */}
      {mode === MODES.JOYSTICK && (
        <div className="joystick-container">
          <Joystick
            onMove={onJoystickMove}
            onRelease={onJoystickRelease}
            size={150}
          />
          <p className="joystick-hint">Drag to move</p>
        </div>
      )}

      {/* Cruise mode */}
      {mode === MODES.CRUISE && (
        <div className="cruise-controls">
          <p className="cruise-instruction">
            {isCruising
              ? (isPaused ? 'Cruise paused' : 'Moving towards destination...')
              : 'Click on the map to select a destination'}
          </p>

          {/* ETA display when cruising */}
          {isCruising && cruiseTarget && cruiseETA && (
            <div className={`cruise-eta ${isPaused ? 'paused' : ''}`}>
              <div className="eta-row">
                <span className="eta-label">Distance:</span>
                <span className="eta-value">{distanceToTarget}</span>
              </div>
              <div className="eta-row">
                <span className="eta-label">ETA:</span>
                <span className="eta-value">{cruiseETA}</span>
              </div>
              {isPaused && (
                <div className="eta-row paused-indicator">
                  <span className="eta-label">Status:</span>
                  <span className="eta-value paused">PAUSED</span>
                </div>
              )}
            </div>
          )}

          {/* ETA preview before starting */}
          {!isCruising && pendingLocation && location && (
            <div className="cruise-eta preview">
              <div className="eta-row">
                <span className="eta-label">Distance:</span>
                <span className="eta-value">
                  {(() => {
                    const d = distanceBetween(location.latitude, location.longitude, pendingLocation.latitude, pendingLocation.longitude);
                    return d < 1 ? `${(d * 1000).toFixed(0)}m` : `${d.toFixed(2)}km`;
                  })()}
                </span>
              </div>
              <div className="eta-row">
                <span className="eta-label">ETA:</span>
                <span className="eta-value">
                  {(() => {
                    const d = distanceBetween(location.latitude, location.longitude, pendingLocation.latitude, pendingLocation.longitude);
                    const timeHours = d / speed;
                    const timeSeconds = timeHours * 3600;
                    if (timeSeconds < 60) return `${Math.ceil(timeSeconds)}s`;
                    if (timeSeconds < 3600) return `${Math.floor(timeSeconds / 60)}m ${Math.ceil(timeSeconds % 60)}s`;
                    return `${Math.floor(timeHours)}h ${Math.ceil((timeHours % 1) * 60)}m`;
                  })()}
                </span>
              </div>
            </div>
          )}

          {/* Cruise control buttons */}
          <div className="cruise-buttons">
            {isCruising ? (
              <>
                <button
                  className={`btn ${isPaused ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={handlePauseResume}
                >
                  {isPaused ? 'Resume' : 'Pause'}
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleCruiseToggle}
                >
                  Stop
                </button>
              </>
            ) : (
              <button
                className="btn btn-primary"
                onClick={handleCruiseToggle}
                disabled={!selectedDevice || !location || !pendingLocation}
              >
                Start Cruise
              </button>
            )}
          </div>

          {!location && !isCruising && (
            <p className="cruise-hint">Set a starting location first</p>
          )}
          {location && !pendingLocation && !isCruising && (
            <p className="cruise-hint">Click on the map to select destination</p>
          )}
        </div>
      )}
    </div>
  );
}
