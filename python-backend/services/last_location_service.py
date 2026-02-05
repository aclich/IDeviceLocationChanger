"""Last location persistence service.

Persists the last set location per device to disk, allowing locations
to be restored when the app restarts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LastLocationService:
    """Persists last location per device to disk."""

    DEFAULT_FILENAME = "last_locations.json"

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the last location service.

        Args:
            data_dir: Directory to store data file. Defaults to ~/.location-simulator/
        """
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            self._data_dir = Path.home() / ".location-simulator"

        self._file_path = self._data_dir / self.DEFAULT_FILENAME
        self._locations: Dict[str, dict] = {}  # device_id -> {"lat": float, "lon": float}

        # Ensure directory exists and load data
        self._ensure_dir_exists()
        self._load()

    @property
    def file_path(self) -> Path:
        """Get the data file path."""
        return self._file_path

    def _ensure_dir_exists(self) -> None:
        """Create data directory if it doesn't exist."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create data directory: {e}")

    def _load(self) -> None:
        """Load last locations from file."""
        self._locations = {}
        try:
            if self._file_path.exists():
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate data structure
                    if isinstance(data, dict):
                        for device_id, loc in data.items():
                            if isinstance(loc, dict) and "lat" in loc and "lon" in loc:
                                self._locations[device_id] = {
                                    "lat": float(loc["lat"]),
                                    "lon": float(loc["lon"]),
                                }
                logger.info(f"Loaded last locations for {len(self._locations)} devices")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load last locations: {e}")

    def _save(self) -> bool:
        """Save last locations to file."""
        try:
            self._ensure_dir_exists()
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._locations, f, indent=2)
            logger.debug(f"Saved last locations for {len(self._locations)} devices")
            return True
        except OSError as e:
            logger.error(f"Failed to save last locations: {e}")
            return False

    def update(self, device_id: str, lat: float, lon: float) -> bool:
        """
        Update the last location for a device.

        Args:
            device_id: The device identifier
            lat: Latitude
            lon: Longitude

        Returns:
            True if saved successfully, False otherwise
        """
        self._locations[device_id] = {"lat": lat, "lon": lon}
        return self._save()

    def get(self, device_id: str) -> Optional[dict]:
        """
        Get the last location for a device.

        Args:
            device_id: The device identifier

        Returns:
            Dict with "lat" and "lon" keys, or None if not found
        """
        return self._locations.get(device_id)

    def get_all(self) -> Dict[str, dict]:
        """
        Get all stored last locations.

        Returns:
            Dict mapping device_id to location dict
        """
        return self._locations.copy()

    def delete(self, device_id: str) -> bool:
        """
        Delete the last location for a device.

        Args:
            device_id: The device identifier

        Returns:
            True if saved successfully, False otherwise
        """
        if device_id in self._locations:
            del self._locations[device_id]
            return self._save()
        return True

    def reload(self) -> None:
        """Reload last locations from file."""
        self._load()
