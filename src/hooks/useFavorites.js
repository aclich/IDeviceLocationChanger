import { useState, useEffect, useCallback } from 'react';
import reverseGeocode from '../utils/reverseGeocode';

/**
 * Hook for managing favorite locations.
 * Communicates with Python backend for persistence.
 */
export function useFavorites() {
  const [favorites, setFavorites] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load favorites on mount
  useEffect(() => {
    loadFavorites();
  }, []);

  const loadFavorites = useCallback(async () => {
    if (!window.backend) return;

    setIsLoading(true);
    try {
      const response = await window.backend.send('getFavorites', {});
      if (response.result?.favorites) {
        setFavorites(response.result.favorites);
      } else if (response.error) {
        setError(response.error.message);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const addFavorite = useCallback(async (latitude, longitude, name = null) => {
    if (!window.backend) return { success: false, error: 'Backend not available' };

    setIsLoading(true);
    setError(null);

    try {
      // If no name provided, try reverse geocoding
      let locationName = name;
      if (!locationName) {
        locationName = await reverseGeocode(latitude, longitude);
      }

      const response = await window.backend.send('addFavorite', {
        latitude,
        longitude,
        name: locationName,
      });

      if (response.result?.success) {
        // Reload to get updated list
        await loadFavorites();
        return { success: true, favorite: response.result.favorite };
      } else {
        const errorMsg = response.result?.error || response.error?.message || 'Failed to add favorite';
        setError(errorMsg);
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setIsLoading(false);
    }
  }, [loadFavorites]);

  const updateFavorite = useCallback(async (index, name) => {
    if (!window.backend) return { success: false, error: 'Backend not available' };

    setIsLoading(true);
    setError(null);

    try {
      const response = await window.backend.send('updateFavorite', { index, name });

      if (response.result?.success) {
        await loadFavorites();
        return { success: true };
      } else {
        const errorMsg = response.result?.error || response.error?.message || 'Failed to update favorite';
        setError(errorMsg);
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setIsLoading(false);
    }
  }, [loadFavorites]);

  const deleteFavorite = useCallback(async (index) => {
    if (!window.backend) return { success: false, error: 'Backend not available' };

    setIsLoading(true);
    setError(null);

    try {
      const response = await window.backend.send('deleteFavorite', { index });

      if (response.result?.success) {
        await loadFavorites();
        return { success: true };
      } else {
        const errorMsg = response.result?.error || response.error?.message || 'Failed to delete favorite';
        setError(errorMsg);
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setIsLoading(false);
    }
  }, [loadFavorites]);

  const importFavorites = useCallback(async (filePath) => {
    if (!window.backend) return { success: false, error: 'Backend not available' };

    setIsLoading(true);
    setError(null);

    try {
      const response = await window.backend.send('importFavorites', { filePath });

      if (response.result?.success) {
        await loadFavorites();
        return { success: true, imported: response.result.imported };
      } else {
        const errorMsg = response.result?.error || response.error?.message || 'Failed to import favorites';
        setError(errorMsg);
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setIsLoading(false);
    }
  }, [loadFavorites]);

  return {
    favorites,
    isLoading,
    error,
    loadFavorites,
    addFavorite,
    updateFavorite,
    deleteFavorite,
    importFavorites,
    clearError: () => setError(null),
  };
}
