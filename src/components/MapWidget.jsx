import { useEffect, useRef, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix Leaflet default marker icon issue
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

export function MapWidget({ location, onLocationSelect, pendingLocation, cruiseTarget }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const mapInstance = useRef(null);
  const markerRef = useRef(null);
  const pendingMarkerRef = useRef(null);
  const targetMarkerRef = useRef(null);
  const routeLineRef = useRef(null);

  const handleCenterLocation = useCallback(() => {
    if (!mapInstance.current || !location) return;
    mapInstance.current.setView([location.latitude, location.longitude], mapInstance.current.getZoom());
  }, [location]);

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    // Default to Taipei 101
    mapInstance.current = L.map(mapRef.current).setView([25.033, 121.565], 15);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(mapInstance.current);

    // Click handler
    mapInstance.current.on('click', (e) => {
      const { lat, lng } = e.latlng;
      onLocationSelect?.(lat, lng);
    });

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, []);

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

    mapInstance.current.panTo([latitude, longitude]);
  }, [location]);

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

  // Update cruise target marker and route line
  useEffect(() => {
    if (!mapInstance.current) return;

    if (cruiseTarget) {
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
  }, [cruiseTarget, location]);

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
    </div>
  );
}
