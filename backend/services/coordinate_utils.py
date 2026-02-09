"""Coordinate calculation utilities using Haversine formula.

Ported from src/utils/coordinateCalculator.js for backend cruise mode.
"""

import math

EARTH_RADIUS_KM = 6371.0


def move_location(
    lat: float,
    lon: float,
    bearing_degrees: float,
    speed_kmh: float,
    duration_seconds: float
) -> tuple[float, float]:
    """Calculate new position after moving in a direction.

    Args:
        lat: Starting latitude in degrees
        lon: Starting longitude in degrees
        bearing_degrees: Bearing (0 = North, 90 = East)
        speed_kmh: Speed in km/h
        duration_seconds: Duration of movement

    Returns:
        Tuple of (new_latitude, new_longitude)
    """
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_degrees)

    speed_mps = (speed_kmh * 1000) / 3600
    distance_km = (speed_mps * duration_seconds) / 1000
    angular_distance = distance_km / EARTH_RADIUS_KM

    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance) +
        math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )

    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )

    return (math.degrees(new_lat_rad), math.degrees(new_lon_rad))


def bearing_to(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """Calculate bearing from point A to point B.

    Args:
        lat1: Start latitude
        lon1: Start longitude
        lat2: End latitude
        lon2: End longitude

    Returns:
        Bearing in degrees (0-360)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)

    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon))

    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def distance_between(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """Calculate distance between two points using Haversine formula.

    Args:
        lat1: Start latitude
        lon1: Start longitude
        lat2: End latitude
        lon2: End longitude

    Returns:
        Distance in kilometers
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (math.sin(d_lat / 2) * math.sin(d_lat / 2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(d_lon / 2) * math.sin(d_lon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c
