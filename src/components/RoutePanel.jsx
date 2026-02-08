import { useMemo } from 'react';

export function RoutePanel({
  routeMode,
  onToggleRouteMode,
  isRouteCruising,
  isRoutePaused,
  waypoints,
  segments,
  loopMode,
  totalDistanceKm,
  hasRoute,
  progressInfo,
  speed,
  onStartRoute,
  onPauseRoute,
  onResumeRoute,
  onStopRoute,
  onClearRoute,
  onUndoWaypoint,
  onToggleLoopMode,
  selectedDevice,
  routeLoading,
}) {
  // Format distance
  const formatDistance = (km) => {
    if (km < 1) return `${(km * 1000).toFixed(0)}m`;
    return `${km.toFixed(1)}km`;
  };

  // Calculate ETA
  const eta = useMemo(() => {
    if (!isRouteCruising || !progressInfo || speed <= 0) return null;
    const timeHours = progressInfo.remainingKm / speed;
    const timeSeconds = timeHours * 3600;

    if (timeSeconds < 60) return `${Math.ceil(timeSeconds)}s`;
    if (timeSeconds < 3600) {
      const mins = Math.floor(timeSeconds / 60);
      const secs = Math.ceil(timeSeconds % 60);
      return `${mins}m ${secs}s`;
    }
    const hours = Math.floor(timeHours);
    const mins = Math.ceil((timeHours - hours) * 60);
    return `${hours}h ${mins}m`;
  }, [isRouteCruising, progressInfo, speed]);

  if (!routeMode) return null;

  return (
    <div className="route-panel">
      <div className="route-panel-header">
        <h3>Route Mode</h3>
        <label className="route-toggle">
          <input
            type="checkbox"
            checked={loopMode}
            onChange={onToggleLoopMode}
          />
          Loop
        </label>
      </div>

      {/* Route info */}
      <div className="route-info">
        <span>{waypoints.length > 0 ? waypoints.length - 1 : 0} waypoints</span>
        <span>{formatDistance(totalDistanceKm)}</span>
        {loopMode && <span className="loop-badge">Loop</span>}
      </div>

      {/* Progress when cruising */}
      {isRouteCruising && progressInfo && (
        <div className="route-progress">
          <div className="progress-row">
            <span>Segment {progressInfo.currentSegment}/{progressInfo.totalSegments}</span>
            <span>{formatDistance(progressInfo.remainingKm)} remaining</span>
          </div>
          {eta && (
            <div className="progress-row">
              <span>ETA: {eta}</span>
              <span>{formatDistance(progressInfo.traveledKm)} traveled</span>
            </div>
          )}
          {loopMode && progressInfo.loopsCompleted > 0 && (
            <div className="progress-row">
              <span>Loop {progressInfo.loopsCompleted + 1}</span>
            </div>
          )}
          {isRoutePaused && (
            <div className="progress-row paused-indicator">
              <span>PAUSED</span>
            </div>
          )}
        </div>
      )}

      {/* Control buttons */}
      <div className="route-buttons">
        {isRouteCruising ? (
          <>
            <button
              className={`btn ${isRoutePaused ? 'btn-primary' : 'btn-secondary'}`}
              onClick={isRoutePaused ? onResumeRoute : onPauseRoute}
            >
              {isRoutePaused ? 'Resume' : 'Pause'}
            </button>
            <button className="btn btn-danger" onClick={onStopRoute}>
              Stop
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-primary"
              onClick={() => onStartRoute(speed)}
              disabled={!selectedDevice || !hasRoute}
            >
              Start Route
            </button>
            <button
              className="btn btn-secondary"
              onClick={onUndoWaypoint}
              disabled={waypoints.length === 0 || isRouteCruising}
            >
              Undo
            </button>
            <button
              className="btn btn-secondary"
              onClick={onClearRoute}
              disabled={waypoints.length === 0 || isRouteCruising}
            >
              Clear
            </button>
          </>
        )}
      </div>

      {/* Loading spinner */}
      {routeLoading && (
        <div className="route-loading">
          <div className="spinner"></div>
          <span>Calculating route...</span>
        </div>
      )}

      {/* Hints */}
      {!isRouteCruising && !routeLoading && (
        <p className="route-hint">
          {waypoints.length === 0
            ? 'Click on the map to set waypoints'
            : !hasRoute
            ? 'Click map to add a destination waypoint'
            : 'Click map to add more waypoints, or start route'}
        </p>
      )}
    </div>
  );
}
