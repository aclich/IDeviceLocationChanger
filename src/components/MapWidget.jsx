import { useEffect, useRef, useCallback, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix Leaflet default marker icon issue
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

export function MapWidget({ location, onLocationSelect, pendingLocation, cruiseTarget, flyTo, routeMode, routeState, onAddWaypoint }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const mapInstance = useRef(null);
  const markerRef = useRef(null);
  const pendingMarkerRef = useRef(null);
  const targetMarkerRef = useRef(null);
  const routeLineRef = useRef(null);
  const routePolylinesRef = useRef([]);
  const waypointMarkersRef = useRef([]);
  const routeModeRef = useRef(false);
  const onAddWaypointRef = useRef(null);

  // Map follow mode - when true, map auto-pans to follow location updates
  const [followLocation, setFollowLocation] = useState(true);

  // Fly to location when flyTo prop changes
  useEffect(() => {
    if (!mapInstance.current || !flyTo) return;
    mapInstance.current.flyTo([flyTo.latitude, flyTo.longitude], 15, {
      duration: 1,
    });
  }, [flyTo]);

  const handleCenterLocation = useCallback(() => {
    if (!mapInstance.current || !location) return;
    mapInstance.current.setView([location.latitude, location.longitude], mapInstance.current.getZoom());
  }, [location]);

  const handleToggleFollow = useCallback(() => {
    setFollowLocation((prev) => !prev);
  }, []);

  const handleGetDeviceLocation = useCallback(() => {
    console.log('[Geolocation] Requesting device location...');

    if (!navigator.geolocation) {
      alert('Geolocation is not supported by this browser.');
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        console.log('[Geolocation] Success:', {
          latitude,
          longitude,
          accuracy: position.coords.accuracy,
        });
        if (mapInstance.current) {
          mapInstance.current.setView([latitude, longitude], 15);
        }
        // Set as pending location if current location is empty
        if (!location) {
          console.log('[Geolocation] Setting as pending location');
          onLocationSelect?.(latitude, longitude);
        }
      },
      (error) => {
        console.log('[Geolocation] Error:', { code: error.code, message: error.message });

        let message = '';
        switch (error.code) {
          case 1: // PERMISSION_DENIED
            message = 'Location permission denied.\n\n' +
              'To enable location access:\n' +
              '• macOS: System Settings → Privacy & Security → Location Services → Enable for this app\n' +
              '• Windows: Settings → Privacy → Location → Allow apps to access your location\n\n' +
              'Note: In development mode, geolocation may not work due to missing app entitlements. ' +
              'It will work in the packaged production app.';
            break;
          case 2: // POSITION_UNAVAILABLE
            message = 'Location unavailable.\n\n' +
              'Please ensure:\n' +
              '• Location Services is enabled on your device\n' +
              '• You have an active internet connection\n' +
              '• Your device has location hardware (WiFi/GPS)';
            break;
          case 3: // TIMEOUT
            message = 'Location request timed out. Please try again.';
            break;
          default:
            message = `Failed to get location: ${error.message}`;
        }
        alert(message);
      },
      { timeout: 10000, enableHighAccuracy: false }
    );
  }, [location, onLocationSelect]);

  // Keep refs in sync to avoid stale closure in map click handler
  useEffect(() => {
    routeModeRef.current = routeMode;
  }, [routeMode]);

  useEffect(() => {
    onAddWaypointRef.current = onAddWaypoint;
  }, [onAddWaypoint]);

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    let isMounted = true;

    // Default to Taipei 101
    mapInstance.current = L.map(mapRef.current).setView([25.033, 121.565], 15);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(mapInstance.current);

    // Click handler - uses refs to avoid stale closure
    mapInstance.current.on('click', (e) => {
      const { lat, lng } = e.latlng;
      if (routeModeRef.current && onAddWaypointRef.current) {
        onAddWaypointRef.current(lat, lng);
      } else {
        onLocationSelect?.(lat, lng);
      }
    });

    // Try to get user's current location (silent failure on startup)
    if (navigator.geolocation) {
      console.log('[Geolocation] Requesting initial position...');
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (!isMounted) return;
          const { latitude, longitude } = position.coords;
          console.log('[Geolocation] Initial position success');
          if (mapInstance.current) {
            mapInstance.current.setView([latitude, longitude], 15);
          }
          // Set as pending location for easy first-time setup
          onLocationSelect?.(latitude, longitude);
        },
        (error) => {
          console.log('[Geolocation] Initial position failed:', error.code, error.message);
          // Silent failure - user can click the GPS button for detailed error
        },
        { timeout: 10000, enableHighAccuracy: false }
      );
    }

    return () => {
      isMounted = false;
      routePolylinesRef.current.forEach(p => p.remove());
      waypointMarkersRef.current.forEach(m => m.remove());
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, [onLocationSelect]);

  // Update marker when actual location changes
  useEffect(() => {
    if (!mapInstance.current || !location) return;

    const { latitude, longitude } = location;

    if (markerRef.current) {
      markerRef.current.setLatLng([latitude, longitude]);
    } else {
      markerRef.current = L.marker([latitude, longitude])
        .addTo(mapInstance.current)
        .bindPopup('Current Location');
    }

    // Only pan to location if follow mode is enabled
    if (followLocation) {
      mapInstance.current.panTo([latitude, longitude]);
    }
  }, [location, followLocation]);

  // Update pending marker when user clicks
  useEffect(() => {
    if (!mapInstance.current) return;

    if (pendingLocation) {
      const { latitude, longitude } = pendingLocation;

      if (pendingMarkerRef.current) {
        pendingMarkerRef.current.setLatLng([latitude, longitude]);
      } else {
        pendingMarkerRef.current = L.circleMarker([latitude, longitude], {
          radius: 10,
          color: '#3388ff',
          fillColor: '#3388ff',
          fillOpacity: 0.5,
        })
          .addTo(mapInstance.current)
          .bindPopup('Click "Set Location" to apply');
      }
    } else if (pendingMarkerRef.current) {
      pendingMarkerRef.current.remove();
      pendingMarkerRef.current = null;
    }
  }, [pendingLocation]);

  // Update cruise target marker and route line (hide during route mode)
  useEffect(() => {
    if (!mapInstance.current) return;

    if (cruiseTarget && !routeMode) {
      const { latitude, longitude } = cruiseTarget;

      // Target marker (destination)
      if (targetMarkerRef.current) {
        targetMarkerRef.current.setLatLng([latitude, longitude]);
      } else {
        targetMarkerRef.current = L.marker([latitude, longitude], {
          icon: L.divIcon({
            className: 'cruise-target-icon',
            html: '🎯',
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          }),
        })
          .addTo(mapInstance.current)
          .bindPopup('Cruise Destination');
      }

      // Route line from current location to target
      if (location) {
        const routeCoords = [
          [location.latitude, location.longitude],
          [latitude, longitude],
        ];

        if (routeLineRef.current) {
          routeLineRef.current.setLatLngs(routeCoords);
        } else {
          routeLineRef.current = L.polyline(routeCoords, {
            color: '#e94560',
            weight: 3,
            opacity: 0.7,
            dashArray: '10, 10',
          }).addTo(mapInstance.current);
        }
      }
    } else {
      // Remove target marker and route line
      if (targetMarkerRef.current) {
        targetMarkerRef.current.remove();
        targetMarkerRef.current = null;
      }
      if (routeLineRef.current) {
        routeLineRef.current.remove();
        routeLineRef.current = null;
      }
    }
  }, [cruiseTarget, location, routeMode]);

  // Draw route polylines and waypoint markers
  useEffect(() => {
    if (!mapInstance.current) return;

    // Clear old route polylines
    routePolylinesRef.current.forEach(p => p.remove());
    routePolylinesRef.current = [];

    // Clear old waypoint markers
    waypointMarkersRef.current.forEach(m => m.remove());
    waypointMarkersRef.current = [];

    if (!routeState) return;

    const { segments = [], waypoints = [] } = routeState;

    // Draw polylines for each segment
    segments.forEach(segment => {
      if (!segment.path || segment.path.length < 2) return;
      const latlngs = segment.path.map(p => [p[0], p[1]]);
      const polyline = L.polyline(latlngs, {
        color: segment.isClosure ? '#06b6d4' : '#14b8a6',
        weight: 4,
        opacity: 0.8,
        dashArray: segment.isClosure ? '8, 8' : null,
      }).addTo(mapInstance.current);
      routePolylinesRef.current.push(polyline);
    });

    // Draw waypoint markers
    waypoints.forEach((wp, i) => {
      const isStart = wp.name === 'START';
      const marker = L.circleMarker([wp.lat, wp.lng], {
        radius: isStart ? 10 : 7,
        color: isStart ? '#3b82f6' : '#f97316',
        fillColor: isStart ? '#3b82f6' : '#f97316',
        fillOpacity: 0.8,
        weight: 2,
      })
        .addTo(mapInstance.current)
        .bindTooltip(wp.name, { permanent: true, direction: 'top', offset: [0, -10], className: 'route-waypoint-tooltip' });
      waypointMarkersRef.current.push(marker);
    });
  }, [routeState]);

  return (
    <div
      ref={containerRef}
      className="map-widget-container"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '400px',
      }}
    >
      <div
        ref={mapRef}
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '8px',
          overflow: 'hidden',
        }}
      />
      {location && (
        <button
          className="map-center-btn"
          onClick={handleCenterLocation}
          title="Center to current location"
        >
          ⌖
        </button>
      )}
      <button
        className="map-gps-btn"
        onClick={handleGetDeviceLocation}
        title="Go to device GPS location"
      >
        📍
      </button>
      <button
        className={`map-follow-btn ${followLocation ? 'locked' : 'unlocked'}`}
        onClick={handleToggleFollow}
        title={followLocation ? 'Map follows location (click to unlock)' : 'Map unlocked (click to follow location)'}
      >
        {followLocation ? '🔒' : '🔓'}
      </button>
    </div>
  );
}
