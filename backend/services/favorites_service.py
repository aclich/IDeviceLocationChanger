"""Favorites management service."""

import logging
import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Favorite:
    """A favorite location."""
    latitude: float
    longitude: float
    name: str

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "name": self.name,
        }

    def to_line(self) -> str:
        """Convert to file line format: latitude,longitude,name"""
        return f"{self.latitude},{self.longitude},{self.name}"

    @classmethod
    def from_line(cls, line: str) -> Optional["Favorite"]:
        """Parse a line from favorites file. Returns None if invalid."""
        line = line.strip()
        if not line:
            return None

        parts = line.split(",", 2)  # Split into at most 3 parts
        if len(parts) < 2:
            return None

        try:
            latitude = float(parts[0].strip())
            longitude = float(parts[1].strip())
            name = parts[2].strip() if len(parts) > 2 else f"{latitude}, {longitude}"

            # Validate coordinates
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                return None

            return cls(latitude=latitude, longitude=longitude, name=name)
        except (ValueError, IndexError):
            return None


class FavoritesService:
    """Manages favorite locations stored in a text file."""

    DEFAULT_FILENAME = "favorites.txt"

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the favorites service.

        Args:
            data_dir: Directory to store favorites file. Defaults to ~/.location-simulator/
        """
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            self._data_dir = Path.home() / ".location-simulator"

        self._file_path = self._data_dir / self.DEFAULT_FILENAME
        self._favorites: List[Favorite] = []

        # Ensure directory exists and load favorites
        self._ensure_file_exists()
        self._load()

    @property
    def file_path(self) -> Path:
        """Get the favorites file path."""
        return self._file_path

    def _ensure_file_exists(self) -> None:
        """Create data directory and empty favorites file if they don't exist."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            if not self._file_path.exists():
                self._file_path.touch()
                logger.info(f"Created favorites file: {self._file_path}")
        except OSError as e:
            logger.error(f"Failed to create favorites file: {e}")

    def _load(self) -> None:
        """Load favorites from file."""
        self._favorites = []
        try:
            if self._file_path.exists():
                with open(self._file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        favorite = Favorite.from_line(line)
                        if favorite:
                            self._favorites.append(favorite)
                logger.info(f"Loaded {len(self._favorites)} favorites from {self._file_path}")
        except OSError as e:
            logger.error(f"Failed to load favorites: {e}")

    def _save(self) -> bool:
        """Save favorites to file."""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                for favorite in self._favorites:
                    f.write(favorite.to_line() + "\n")
            logger.debug(f"Saved {len(self._favorites)} favorites")
            return True
        except OSError as e:
            logger.error(f"Failed to save favorites: {e}")
            return False

    def get_all(self) -> List[Favorite]:
        """Get all favorites."""
        return self._favorites.copy()

    def add(self, latitude: float, longitude: float, name: str) -> dict:
        """
        Add a new favorite.

        Returns:
            dict with 'success' and optionally 'error' or 'favorite'
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            return {"success": False, "error": "Invalid latitude (must be -90 to 90)"}
        if not (-180 <= longitude <= 180):
            return {"success": False, "error": "Invalid longitude (must be -180 to 180)"}

        name = name.strip() if name else f"{latitude}, {longitude}"

        favorite = Favorite(latitude=latitude, longitude=longitude, name=name)
        self._favorites.append(favorite)

        if self._save():
            return {"success": True, "favorite": favorite.to_dict()}
        else:
            # Rollback
            self._favorites.pop()
            return {"success": False, "error": "Failed to save favorites file"}

    def update(self, index: int, name: str) -> dict:
        """
        Update (rename) a favorite by index.

        Returns:
            dict with 'success' and optionally 'error' or 'favorite'
        """
        if index < 0 or index >= len(self._favorites):
            return {"success": False, "error": f"Invalid index: {index}"}

        name = name.strip()
        if not name:
            return {"success": False, "error": "Name cannot be empty"}

        old_name = self._favorites[index].name
        self._favorites[index].name = name

        if self._save():
            return {"success": True, "favorite": self._favorites[index].to_dict()}
        else:
            # Rollback
            self._favorites[index].name = old_name
            return {"success": False, "error": "Failed to save favorites file"}

    def delete(self, index: int) -> dict:
        """
        Delete a favorite by index.

        Returns:
            dict with 'success' and optionally 'error'
        """
        if index < 0 or index >= len(self._favorites):
            return {"success": False, "error": f"Invalid index: {index}"}

        removed = self._favorites.pop(index)

        if self._save():
            return {"success": True}
        else:
            # Rollback
            self._favorites.insert(index, removed)
            return {"success": False, "error": "Failed to save favorites file"}

    def import_from_file(self, file_path: str) -> dict:
        """
        Import favorites from another file (appends to existing).

        Returns:
            dict with 'success', 'imported' count, and optionally 'error'
        """
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        imported = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    favorite = Favorite.from_line(line)
                    if favorite:
                        imported.append(favorite)
        except OSError as e:
            return {"success": False, "error": f"Failed to read file: {e}"}

        if not imported:
            return {"success": False, "error": "No valid favorites found in file"}

        self._favorites.extend(imported)

        if self._save():
            return {"success": True, "imported": len(imported)}
        else:
            # Rollback
            for _ in imported:
                self._favorites.pop()
            return {"success": False, "error": "Failed to save favorites file"}

    def reload(self) -> None:
        """Reload favorites from file."""
        self._load()
