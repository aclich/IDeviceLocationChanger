"""Brouter pathfinding service - calculates hiking routes between waypoints.

Calls the Brouter REST API to find optimal hiking paths. Falls back to
straight-line paths if the API is unavailable or fails.

Configuration:
    BROUTER_API_URL environment variable (default: https://brouter.de/brouter)
"""

import asyncio
import logging
import os
from typing import Optional

import aiohttp

from .coordinate_utils import distance_between

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BROUTER_URL = "https://brouter.de/brouter"
BROUTER_PROFILE = "trekking"
BROUTER_TIMEOUT_SECONDS = 10
BROUTER_MAX_RETRIES = 3


class BrouterService:
    """Service for calculating hiking routes via Brouter API."""

    def __init__(self):
        self._api_url = os.environ.get("BROUTER_API_URL", DEFAULT_BROUTER_URL)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=BROUTER_TIMEOUT_SECONDS)
            )
        return self._session

    async def get_route(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> dict:
        """Calculate a hiking route between two points.

        Args:
            start: (latitude, longitude) of start point
            end: (latitude, longitude) of end point

        Returns:
            dict with:
                path: list of [lat, lng] points
                distance_km: total path distance
                is_fallback: True if straight-line fallback was used
        """
        logger.info(
            f"Requesting route: ({start[0]:.5f},{start[1]:.5f}) -> "
            f"({end[0]:.5f},{end[1]:.5f})"
        )

        path = await self._fetch_route(start, end)

        if path is not None:
            dist = self._calculate_path_distance(path)
            logger.info(f"Brouter route: {len(path)} points, {dist:.2f} km")
            return {"path": path, "distance_km": dist, "is_fallback": False}

        # Fallback to straight line
        logger.warning("Brouter failed, using straight-line fallback")
        dist = distance_between(start[0], start[1], end[0], end[1])
        return {
            "path": [list(start), list(end)],
            "distance_km": dist,
            "is_fallback": True,
        }

    async def _fetch_route(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> Optional[list[list[float]]]:
        """Fetch route from Brouter API with retries.

        Returns list of [lat, lng] points or None on failure.
        """
        params = {
            "lonlats": f"{start[1]},{start[0]}|{end[1]},{end[0]}",
            "profile": BROUTER_PROFILE,
            "alternativeidx": "0",
            "format": "geojson",
        }

        for attempt in range(BROUTER_MAX_RETRIES):
            try:
                session = await self._get_session()
                logger.debug(
                    f"Brouter request attempt {attempt + 1}/{BROUTER_MAX_RETRIES}"
                )
                async with session.get(self._api_url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(
                            f"Brouter HTTP {resp.status}: {text[:200]}"
                        )
                        if attempt < BROUTER_MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                        continue

                    data = await resp.json()
                    coords = (
                        data.get("features", [{}])[0]
                        .get("geometry", {})
                        .get("coordinates", [])
                    )

                    if not coords:
                        logger.warning("Brouter returned empty coordinates")
                        return None

                    # Brouter returns [lng, lat]; convert to [lat, lng]
                    path = [[c[1], c[0]] for c in coords]
                    return path

            except asyncio.TimeoutError:
                logger.warning(
                    f"Brouter timeout (attempt {attempt + 1}/{BROUTER_MAX_RETRIES})"
                )
                if attempt < BROUTER_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(
                    f"Brouter error (attempt {attempt + 1}/{BROUTER_MAX_RETRIES}): {e}"
                )
                if attempt < BROUTER_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)

        return None

    def _calculate_path_distance(self, path: list[list[float]]) -> float:
        """Calculate total distance of a path in km."""
        total = 0.0
        for i in range(len(path) - 1):
            total += distance_between(
                path[i][0], path[i][1],
                path[i + 1][0], path[i + 1][1],
            )
        return total

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
