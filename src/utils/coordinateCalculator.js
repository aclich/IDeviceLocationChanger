/**
 * Coordinate calculation utilities using Haversine formula.
 * Ported from Python backend for frontend cruise/joystick calculations.
 */

const EARTH_RADIUS_KM = 6371.0;

/**
 * Normalize latitude and longitude to valid ranges.
 * Latitude: clamp to [-90, 90]
 * Longitude: wrap to [-180, 180]
 *
 * @param {number} lat - Latitude in degrees
 * @param {number} lng - Longitude in degrees
 * @returns {[number, number]} [normalizedLat, normalizedLng]
 */
export function normalizeCoordinates(lat, lng) {
  const normalizedLat = Math.max(-90, Math.min(90, lat));
  const normalizedLng = ((lng % 360) + 540) % 360 - 180;
  return [normalizedLat, normalizedLng];
}

/**
 * Calculate new position after moving in a direction.
 *
 * @param {number} lat - Starting latitude in degrees
 * @param {number} lon - Starting longitude in degrees
 * @param {number} directionDegrees - Bearing (0 = North, 90 = East)
 * @param {number} speedKmh - Speed in km/h
 * @param {number} durationSeconds - Duration of movement
 * @returns {[number, number]} [newLatitude, newLongitude]
 */
export function moveLocation(lat, lon, directionDegrees, speedKmh, durationSeconds) {
  const latRad = (lat * Math.PI) / 180;
  const lonRad = (lon * Math.PI) / 180;
  const bearingRad = (directionDegrees * Math.PI) / 180;

  const speedMps = (speedKmh * 1000) / 3600;
  const distanceKm = (speedMps * durationSeconds) / 1000;
  const angularDistance = distanceKm / EARTH_RADIUS_KM;

  const newLatRad = Math.asin(
    Math.sin(latRad) * Math.cos(angularDistance) +
    Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearingRad)
  );

  const newLonRad = lonRad + Math.atan2(
    Math.sin(bearingRad) * Math.sin(angularDistance) * Math.cos(latRad),
    Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(newLatRad)
  );

  const rawLat = (newLatRad * 180) / Math.PI;
  const rawLng = (newLonRad * 180) / Math.PI;
  return normalizeCoordinates(rawLat, rawLng);
}

/**
 * Convert joystick offset to compass bearing.
 *
 * @param {number} dx - X offset
 * @param {number} dy - Y offset
 * @returns {number} Direction in degrees (0-360)
 */
export function directionFromOffset(dx, dy) {
  const angle = Math.atan2(dx, -dy);
  let degrees = (angle * 180) / Math.PI;
  if (degrees < 0) {
    degrees += 360;
  }
  return degrees;
}

/**
 * Calculate speed multiplier based on joystick distance from center.
 *
 * @param {number} dx - X offset
 * @param {number} dy - Y offset
 * @param {number} maxDistance - Maximum joystick distance
 * @returns {number} Speed multiplier (0-1)
 */
export function speedMultiplier(dx, dy, maxDistance) {
  const distance = Math.sqrt(dx * dx + dy * dy);
  return maxDistance > 0 ? Math.min(distance / maxDistance, 1.0) : 0;
}

/**
 * Calculate bearing from point A to point B.
 *
 * @param {number} lat1 - Start latitude
 * @param {number} lon1 - Start longitude
 * @param {number} lat2 - End latitude
 * @param {number} lon2 - End longitude
 * @returns {number} Bearing in degrees (0-360)
 */
export function bearingTo(lat1, lon1, lat2, lon2) {
  const lat1Rad = (lat1 * Math.PI) / 180;
  const lat2Rad = (lat2 * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;

  const y = Math.sin(dLon) * Math.cos(lat2Rad);
  const x = Math.cos(lat1Rad) * Math.sin(lat2Rad) -
            Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);

  let bearing = (Math.atan2(y, x) * 180) / Math.PI;
  return (bearing + 360) % 360;
}

/**
 * Calculate distance between two points using Haversine formula.
 *
 * @param {number} lat1 - Start latitude
 * @param {number} lon1 - Start longitude
 * @param {number} lat2 - End latitude
 * @param {number} lon2 - End longitude
 * @returns {number} Distance in kilometers
 */
export function distanceBetween(lat1, lon1, lat2, lon2) {
  const lat1Rad = (lat1 * Math.PI) / 180;
  const lat2Rad = (lat2 * Math.PI) / 180;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;

  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1Rad) * Math.cos(lat2Rad) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return EARTH_RADIUS_KM * c;
}
