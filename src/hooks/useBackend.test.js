import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBackend } from './useBackend.js';

// Mock the browserBackend module
vi.mock('../utils/browserBackend', () => ({
  isBrowserMode: vi.fn(() => true),
}));

describe('useBackend', () => {
  beforeEach(() => {
    vi.useFakeTimers();

    // Set up a mock browser backend
    window.backend = {
      send: vi.fn().mockResolvedValue({ result: {} }),
      onEvent: vi.fn().mockReturnValue(() => {}),
      checkHealth: vi.fn().mockResolvedValue(true),
      isBrowserMode: true,
    };
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    delete window.backend;
  });

  describe('initial state', () => {
    it('initializes isConnected as true', () => {
      const { result } = renderHook(() => useBackend());

      // Before any effects run, isConnected should be true
      expect(result.current.isConnected).toBe(true);
    });

    it('sets isConnected to false when window.backend is undefined', async () => {
      delete window.backend;

      const { result } = renderHook(() => useBackend());

      // Just need a microtask tick, not running all timers (which causes infinite loop with intervals)
      await act(async () => {
        await Promise.resolve();
      });

      expect(result.current.isConnected).toBe(false);
      expect(result.current.error).toBe('Backend not available');
    });
  });

  describe('connection check (browser mode)', () => {
    it('checks connection health on mount', async () => {
      renderHook(() => useBackend());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(window.backend.checkHealth).toHaveBeenCalled();
    });

    it('sets isConnected to true when backend is healthy', async () => {
      window.backend.checkHealth.mockResolvedValue(true);

      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('sets isConnected to false when backend is not healthy', async () => {
      window.backend.checkHealth.mockResolvedValue(false);

      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(result.current.isConnected).toBe(false);
    });

    it('sets error message when backend is not healthy', async () => {
      window.backend.checkHealth.mockResolvedValue(false);

      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(result.current.error).toContain('Backend not running');
    });
  });

  describe('health check interval', () => {
    it('starts health check interval when disconnected', async () => {
      window.backend.checkHealth.mockResolvedValue(false);

      renderHook(() => useBackend());

      // Initial check - just flush promises, not all timers
      await act(async () => {
        await Promise.resolve();
      });

      expect(window.backend.checkHealth).toHaveBeenCalledTimes(1);

      // Advance timer by 5 seconds - should trigger another check
      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });

      expect(window.backend.checkHealth).toHaveBeenCalledTimes(2);

      // Advance another 5 seconds
      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });

      expect(window.backend.checkHealth).toHaveBeenCalledTimes(3);
    });

    it('does not run interval health checks when connected', async () => {
      window.backend.checkHealth.mockResolvedValue(true);

      renderHook(() => useBackend());

      // Initial check
      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(window.backend.checkHealth).toHaveBeenCalledTimes(1);

      // Advance timer by 10 seconds - should NOT trigger more checks
      await act(async () => {
        vi.advanceTimersByTime(10000);
        await vi.runAllTimersAsync();
      });

      // Should still be 1 (only initial check, no interval)
      expect(window.backend.checkHealth).toHaveBeenCalledTimes(1);
    });

    it('stops health check interval when connection is restored', async () => {
      // Start disconnected
      window.backend.checkHealth.mockResolvedValue(false);

      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      expect(result.current.isConnected).toBe(false);

      // Trigger one interval check
      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });

      // Now backend becomes healthy
      window.backend.checkHealth.mockResolvedValue(true);

      // Trigger reconnection check
      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });

      expect(result.current.isConnected).toBe(true);

      const callCountAfterReconnect = window.backend.checkHealth.mock.calls.length;

      // After reconnection, interval should stop - wait 15 more seconds
      await act(async () => {
        vi.advanceTimersByTime(15000);
        await Promise.resolve();
      });

      // No additional calls after reconnection
      expect(window.backend.checkHealth).toHaveBeenCalledTimes(callCountAfterReconnect);
    });

    it('cleans up interval on unmount', async () => {
      window.backend.checkHealth.mockResolvedValue(false);

      const { unmount } = renderHook(() => useBackend());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(window.backend.checkHealth).toHaveBeenCalled();

      unmount();

      // Advance timer - should not trigger more checks after unmount
      const callCount = window.backend.checkHealth.mock.calls.length;

      await act(async () => {
        vi.advanceTimersByTime(10000);
        await vi.runAllTimersAsync();
      });

      expect(window.backend.checkHealth).toHaveBeenCalledTimes(callCount);
    });
  });

  describe('Electron mode', () => {
    beforeEach(async () => {
      vi.resetModules();

      vi.doMock('../utils/browserBackend', () => ({
        isBrowserMode: vi.fn(() => false),
      }));

      // Re-setup backend without checkHealth (simulating Electron)
      window.backend = {
        send: vi.fn().mockResolvedValue({ result: {} }),
        onEvent: vi.fn().mockReturnValue(() => {}),
      };
    });

    it('assumes connected in Electron mode', async () => {
      const { useBackend: useBackendElectron } = await import('./useBackend.js');

      const { result } = renderHook(() => useBackendElectron());

      await act(async () => {
        await vi.runAllTimersAsync();
      });

      expect(result.current.isConnected).toBe(true);
    });
  });
});
