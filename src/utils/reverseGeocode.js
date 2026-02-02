/**
 * Reverse geocoding utility using Nominatim (OpenStreetMap).
 */

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse';

/**
 * Get a location name from coordinates using reverse geocoding.
 *
 * @param {number} latitude
 * @param {number} longitude
 * @returns {Promise<string>} Location name in "Country / City / District" format
 */
export async function reverseGeocode(latitude, longitude) {
  try {
    const params = new URLSearchParams({
      lat: latitude.toString(),
      lon: longitude.toString(),
      format: 'json',
      zoom: 14, // City/suburb level detail
    });

    const response = await fetch(`${NOMINATIM_URL}?${params}`, {
      headers: {
        'Accept-Language': navigator.language || 'en',
        'User-Agent': 'LocationSimulator/1.0',
      },
    });

    if (!response.ok) {
      throw new Error(`Nominatim API error: ${response.status}`);
    }

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    return formatLocationName(data.address);
  } catch (error) {
    console.warn('[ReverseGeocode] Failed:', error.message);
    // Fallback to coordinates
    return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
  }
}

/**
 * Format address components into a readable location name.
 *
 * @param {Object} address - Nominatim address object
 * @returns {string} Formatted location name
 */
function formatLocationName(address) {
  if (!address) {
    return 'Unknown Location';
  }

  // Extract relevant parts (priority order)
  const district =
    address.suburb ||
    address.neighbourhood ||
    address.quarter ||
    address.village ||
    address.town ||
    address.hamlet;

  const city =
    address.city ||
    address.municipality ||
    address.county ||
    address.state_district;

  const country =
    address.country;

  // Build name from available parts
  const parts = [country, city, district].filter(Boolean);

  if (parts.length === 0) {
    // Last resort: use display_name or any available field
    return address.display_name || 'Unknown Location';
  }

  return parts.join(' / ');
}

export default reverseGeocode;
