"""Tests for FavoritesService."""

import pytest
import tempfile
from pathlib import Path

from services.favorites_service import Favorite, FavoritesService


class TestFavorite:
    """Tests for Favorite dataclass."""

    def test_to_dict(self):
        fav = Favorite(latitude=25.033, longitude=121.565, name="Taipei 101")
        result = fav.to_dict()

        assert result == {
            "latitude": 25.033,
            "longitude": 121.565,
            "name": "Taipei 101",
        }

    def test_to_line(self):
        fav = Favorite(latitude=25.033, longitude=121.565, name="Taipei 101")
        result = fav.to_line()

        assert result == "25.033,121.565,Taipei 101"

    def test_from_line_with_name(self):
        fav = Favorite.from_line("25.033,121.565,Taipei 101")

        assert fav is not None
        assert fav.latitude == 25.033
        assert fav.longitude == 121.565
        assert fav.name == "Taipei 101"

    def test_from_line_without_name(self):
        fav = Favorite.from_line("25.033,121.565")

        assert fav is not None
        assert fav.latitude == 25.033
        assert fav.longitude == 121.565
        assert fav.name == "25.033, 121.565"

    def test_from_line_with_spaces(self):
        fav = Favorite.from_line("  25.033 , 121.565 , My Location  ")

        assert fav is not None
        assert fav.latitude == 25.033
        assert fav.longitude == 121.565
        assert fav.name == "My Location"

    def test_from_line_with_commas_in_name(self):
        fav = Favorite.from_line("25.033,121.565,Tokyo, Japan")

        assert fav is not None
        assert fav.name == "Tokyo, Japan"

    def test_from_line_empty(self):
        assert Favorite.from_line("") is None
        assert Favorite.from_line("   ") is None

    def test_from_line_invalid_format(self):
        assert Favorite.from_line("not a coordinate") is None
        assert Favorite.from_line("25.033") is None

    def test_from_line_invalid_latitude(self):
        assert Favorite.from_line("91,121.565,Invalid") is None
        assert Favorite.from_line("-91,121.565,Invalid") is None

    def test_from_line_invalid_longitude(self):
        assert Favorite.from_line("25,181,Invalid") is None
        assert Favorite.from_line("25,-181,Invalid") is None


class TestFavoritesService:
    """Tests for FavoritesService."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def service(self, temp_dir):
        """Create a FavoritesService with temp directory."""
        return FavoritesService(data_dir=temp_dir)

    def test_creates_file_on_init(self, temp_dir):
        service = FavoritesService(data_dir=temp_dir)

        assert service.file_path.exists()
        assert service.get_all() == []

    def test_loads_existing_favorites(self, temp_dir):
        # Create a favorites file first
        file_path = Path(temp_dir) / "favorites.txt"
        file_path.write_text("25.033,121.565,Taipei 101\n35.6762,139.6503,Tokyo Tower\n")

        service = FavoritesService(data_dir=temp_dir)

        favorites = service.get_all()
        assert len(favorites) == 2
        assert favorites[0].name == "Taipei 101"
        assert favorites[1].name == "Tokyo Tower"

    def test_skips_invalid_lines_on_load(self, temp_dir):
        file_path = Path(temp_dir) / "favorites.txt"
        file_path.write_text("25.033,121.565,Valid\ninvalid line\n35.6762,139.6503,Also Valid\n")

        service = FavoritesService(data_dir=temp_dir)

        favorites = service.get_all()
        assert len(favorites) == 2

    def test_add_favorite(self, service):
        result = service.add(25.033, 121.565, "Taipei 101")

        assert result["success"] is True
        assert result["favorite"]["name"] == "Taipei 101"

        favorites = service.get_all()
        assert len(favorites) == 1
        assert favorites[0].name == "Taipei 101"

    def test_add_favorite_persists_to_file(self, service):
        service.add(25.033, 121.565, "Taipei 101")

        # Create new service instance to verify persistence
        new_service = FavoritesService(data_dir=str(service.file_path.parent))
        favorites = new_service.get_all()

        assert len(favorites) == 1
        assert favorites[0].name == "Taipei 101"

    def test_add_favorite_with_empty_name_uses_coordinates(self, service):
        result = service.add(25.033, 121.565, "")

        assert result["success"] is True
        assert result["favorite"]["name"] == "25.033, 121.565"

    def test_add_favorite_invalid_latitude(self, service):
        result = service.add(91, 121.565, "Invalid")

        assert result["success"] is False
        assert "latitude" in result["error"].lower()

    def test_add_favorite_invalid_longitude(self, service):
        result = service.add(25, 181, "Invalid")

        assert result["success"] is False
        assert "longitude" in result["error"].lower()

    def test_update_favorite(self, service):
        service.add(25.033, 121.565, "Old Name")

        result = service.update(0, "New Name")

        assert result["success"] is True
        assert result["favorite"]["name"] == "New Name"
        assert service.get_all()[0].name == "New Name"

    def test_update_favorite_persists(self, service):
        service.add(25.033, 121.565, "Old Name")
        service.update(0, "New Name")

        new_service = FavoritesService(data_dir=str(service.file_path.parent))
        assert new_service.get_all()[0].name == "New Name"

    def test_update_favorite_invalid_index(self, service):
        result = service.update(0, "Name")

        assert result["success"] is False
        assert "index" in result["error"].lower()

    def test_update_favorite_empty_name(self, service):
        service.add(25.033, 121.565, "Name")

        result = service.update(0, "  ")

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    def test_delete_favorite(self, service):
        service.add(25.033, 121.565, "First")
        service.add(35.6762, 139.6503, "Second")

        result = service.delete(0)

        assert result["success"] is True
        favorites = service.get_all()
        assert len(favorites) == 1
        assert favorites[0].name == "Second"

    def test_delete_favorite_persists(self, service):
        service.add(25.033, 121.565, "First")
        service.add(35.6762, 139.6503, "Second")
        service.delete(0)

        new_service = FavoritesService(data_dir=str(service.file_path.parent))
        assert len(new_service.get_all()) == 1

    def test_delete_favorite_invalid_index(self, service):
        result = service.delete(0)

        assert result["success"] is False
        assert "index" in result["error"].lower()

    def test_import_from_file(self, service, temp_dir):
        # Create an import file
        import_path = Path(temp_dir) / "import.txt"
        import_path.write_text("25.033,121.565,Taipei\n35.6762,139.6503,Tokyo\n")

        result = service.import_from_file(str(import_path))

        assert result["success"] is True
        assert result["imported"] == 2
        assert len(service.get_all()) == 2

    def test_import_appends_to_existing(self, service, temp_dir):
        service.add(0, 0, "Existing")

        import_path = Path(temp_dir) / "import.txt"
        import_path.write_text("25.033,121.565,Imported\n")

        service.import_from_file(str(import_path))

        assert len(service.get_all()) == 2
        assert service.get_all()[0].name == "Existing"
        assert service.get_all()[1].name == "Imported"

    def test_import_file_not_found(self, service):
        result = service.import_from_file("/nonexistent/path.txt")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_import_empty_file(self, service, temp_dir):
        import_path = Path(temp_dir) / "empty.txt"
        import_path.write_text("")

        result = service.import_from_file(str(import_path))

        assert result["success"] is False
        assert "no valid" in result["error"].lower()

    def test_import_all_invalid_lines(self, service, temp_dir):
        import_path = Path(temp_dir) / "invalid.txt"
        import_path.write_text("invalid\nalso invalid\n")

        result = service.import_from_file(str(import_path))

        assert result["success"] is False

    def test_reload(self, service):
        service.add(25.033, 121.565, "Original")

        # Modify file directly
        service.file_path.write_text("35.6762,139.6503,Modified\n")

        # Reload
        service.reload()

        favorites = service.get_all()
        assert len(favorites) == 1
        assert favorites[0].name == "Modified"
