import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useFavorites } from './useFavorites';

// Mock the reverseGeocode utility
vi.mock('../utils/reverseGeocode', () => ({
  default: vi.fn().mockResolvedValue('Taiwan / Taipei / Zhongzheng'),
}));

describe('useFavorites', () => {
  let mockBackend;

  beforeEach(() => {
    mockBackend = {
      send: vi.fn(),
    };
    window.backend = mockBackend;
  });

  afterEach(() => {
    delete window.backend;
    vi.clearAllMocks();
  });

  describe('initialization', () => {
    it('should initialize with empty favorites', async () => {
      mockBackend.send.mockResolvedValue({ result: { favorites: [] } });

      const { result } = renderHook(() => useFavorites());

      // Wait for initial load to complete
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.favorites).toEqual([]);
      expect(result.current.error).toBeNull();
    });

    it('should load favorites on mount', async () => {
      const mockFavorites = [
        { latitude: 24.9536, longitude: 121.5518, name: 'Home' },
        { latitude: 25.0330, longitude: 121.5654, name: 'Office' },
      ];
      mockBackend.send.mockResolvedValue({ result: { favorites: mockFavorites } });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.favorites).toEqual(mockFavorites);
      });

      expect(mockBackend.send).toHaveBeenCalledWith('getFavorites', {});
    });

    it('should handle load error', async () => {
      mockBackend.send.mockResolvedValue({
        error: { message: 'Failed to load' },
      });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.error).toBe('Failed to load');
      });
    });

    it('should not load if backend is not available', () => {
      delete window.backend;

      const { result } = renderHook(() => useFavorites());

      expect(result.current.favorites).toEqual([]);
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('addFavorite', () => {
    it('should add a favorite with provided name', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } }) // initial load
        .mockResolvedValueOnce({
          result: { success: true, favorite: { latitude: 24.9536, longitude: 121.5518, name: 'Home' } },
        })
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'Home' }] },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalledWith('getFavorites', {});
      });

      let addResult;
      await act(async () => {
        addResult = await result.current.addFavorite(24.9536, 121.5518, 'Home');
      });

      expect(addResult.success).toBe(true);
      expect(mockBackend.send).toHaveBeenCalledWith('addFavorite', {
        latitude: 24.9536,
        longitude: 121.5518,
        name: 'Home',
      });
    });

    it('should use reverse geocoding when no name provided', async () => {
      const reverseGeocode = (await import('../utils/reverseGeocode')).default;

      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } }) // initial load
        .mockResolvedValueOnce({
          result: { success: true, favorite: { latitude: 24.9536, longitude: 121.5518, name: 'Taiwan / Taipei / Zhongzheng' } },
        })
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'Taiwan / Taipei / Zhongzheng' }] },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalledWith('getFavorites', {});
      });

      await act(async () => {
        await result.current.addFavorite(24.9536, 121.5518);
      });

      expect(reverseGeocode).toHaveBeenCalledWith(24.9536, 121.5518);
      expect(mockBackend.send).toHaveBeenCalledWith('addFavorite', {
        latitude: 24.9536,
        longitude: 121.5518,
        name: 'Taiwan / Taipei / Zhongzheng',
      });
    });

    it('should return error if backend not available', async () => {
      delete window.backend;

      const { result } = renderHook(() => useFavorites());

      let addResult;
      await act(async () => {
        addResult = await result.current.addFavorite(24.9536, 121.5518);
      });

      expect(addResult.success).toBe(false);
      expect(addResult.error).toBe('Backend not available');
    });

    it('should handle add failure', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockResolvedValueOnce({
          result: { success: false, error: 'Duplicate location' },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let addResult;
      await act(async () => {
        addResult = await result.current.addFavorite(24.9536, 121.5518, 'Home');
      });

      expect(addResult.success).toBe(false);
      expect(addResult.error).toBe('Duplicate location');
      expect(result.current.error).toBe('Duplicate location');
    });

    it('should handle network error', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let addResult;
      await act(async () => {
        addResult = await result.current.addFavorite(24.9536, 121.5518, 'Home');
      });

      expect(addResult.success).toBe(false);
      expect(addResult.error).toBe('Network error');
    });
  });

  describe('updateFavorite', () => {
    it('should update a favorite name', async () => {
      mockBackend.send
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'Home' }] },
        })
        .mockResolvedValueOnce({ result: { success: true } })
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'My Home' }] },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.favorites.length).toBe(1);
      });

      let updateResult;
      await act(async () => {
        updateResult = await result.current.updateFavorite(0, 'My Home');
      });

      expect(updateResult.success).toBe(true);
      expect(mockBackend.send).toHaveBeenCalledWith('updateFavorite', { index: 0, name: 'My Home' });
    });

    it('should return error if backend not available', async () => {
      delete window.backend;

      const { result } = renderHook(() => useFavorites());

      let updateResult;
      await act(async () => {
        updateResult = await result.current.updateFavorite(0, 'New Name');
      });

      expect(updateResult.success).toBe(false);
      expect(updateResult.error).toBe('Backend not available');
    });

    it('should handle update failure', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockResolvedValueOnce({
          result: { success: false, error: 'Index out of range' },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let updateResult;
      await act(async () => {
        updateResult = await result.current.updateFavorite(99, 'Name');
      });

      expect(updateResult.success).toBe(false);
      expect(updateResult.error).toBe('Index out of range');
    });
  });

  describe('deleteFavorite', () => {
    it('should delete a favorite', async () => {
      mockBackend.send
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'Home' }] },
        })
        .mockResolvedValueOnce({ result: { success: true } })
        .mockResolvedValueOnce({ result: { favorites: [] } });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.favorites.length).toBe(1);
      });

      let deleteResult;
      await act(async () => {
        deleteResult = await result.current.deleteFavorite(0);
      });

      expect(deleteResult.success).toBe(true);
      expect(mockBackend.send).toHaveBeenCalledWith('deleteFavorite', { index: 0 });
    });

    it('should return error if backend not available', async () => {
      delete window.backend;

      const { result } = renderHook(() => useFavorites());

      let deleteResult;
      await act(async () => {
        deleteResult = await result.current.deleteFavorite(0);
      });

      expect(deleteResult.success).toBe(false);
      expect(deleteResult.error).toBe('Backend not available');
    });

    it('should handle delete failure', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockResolvedValueOnce({
          result: { success: false, error: 'Index out of range' },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let deleteResult;
      await act(async () => {
        deleteResult = await result.current.deleteFavorite(99);
      });

      expect(deleteResult.success).toBe(false);
      expect(deleteResult.error).toBe('Index out of range');
    });
  });

  describe('importFavorites', () => {
    it('should import favorites from file', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockResolvedValueOnce({ result: { success: true, imported: 5 } })
        .mockResolvedValueOnce({
          result: { favorites: [{ latitude: 24.9536, longitude: 121.5518, name: 'Location 1' }] },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let importResult;
      await act(async () => {
        importResult = await result.current.importFavorites('~/favorites.txt');
      });

      expect(importResult.success).toBe(true);
      expect(importResult.imported).toBe(5);
      expect(mockBackend.send).toHaveBeenCalledWith('importFavorites', { filePath: '~/favorites.txt' });
    });

    it('should return error if backend not available', async () => {
      delete window.backend;

      const { result } = renderHook(() => useFavorites());

      let importResult;
      await act(async () => {
        importResult = await result.current.importFavorites('~/favorites.txt');
      });

      expect(importResult.success).toBe(false);
      expect(importResult.error).toBe('Backend not available');
    });

    it('should handle import failure', async () => {
      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: [] } })
        .mockResolvedValueOnce({
          result: { success: false, error: 'File not found' },
        });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(mockBackend.send).toHaveBeenCalled();
      });

      let importResult;
      await act(async () => {
        importResult = await result.current.importFavorites('/nonexistent.txt');
      });

      expect(importResult.success).toBe(false);
      expect(importResult.error).toBe('File not found');
    });
  });

  describe('clearError', () => {
    it('should clear error state', async () => {
      mockBackend.send.mockResolvedValueOnce({
        error: { message: 'Test error' },
      });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.error).toBe('Test error');
      });

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('loadFavorites', () => {
    it('should reload favorites when called manually', async () => {
      const initialFavorites = [{ latitude: 24.9536, longitude: 121.5518, name: 'Home' }];
      const updatedFavorites = [
        { latitude: 24.9536, longitude: 121.5518, name: 'Home' },
        { latitude: 25.0330, longitude: 121.5654, name: 'Office' },
      ];

      mockBackend.send
        .mockResolvedValueOnce({ result: { favorites: initialFavorites } })
        .mockResolvedValueOnce({ result: { favorites: updatedFavorites } });

      const { result } = renderHook(() => useFavorites());

      await waitFor(() => {
        expect(result.current.favorites).toEqual(initialFavorites);
      });

      await act(async () => {
        await result.current.loadFavorites();
      });

      expect(result.current.favorites).toEqual(updatedFavorites);
      expect(mockBackend.send).toHaveBeenCalledTimes(2);
    });
  });
});
