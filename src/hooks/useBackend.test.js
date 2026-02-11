import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBackend } from './useBackend.js';

// Mock the backendClient module
vi.mock('../utils/backendClient', () => ({
  isBrowserMode: vi.fn(() => true),
}));

describe('useBackend', () => {
  beforeEach(() => {
    vi.useFakeTimers();

    // Set up a mock backend
    window.backend = {
      send: vi.fn().mockResolvedValue({ result: {} }),
      onEvent: vi.fn().mockReturnValue(() => {}),
      checkHealth: vi.fn().mockResolvedValue(true),
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

  describe('connection check', () => {
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

  describe('SSE event filtering (multi-device)', () => {
    let eventHandler;

    beforeEach(() => {
      // Capture the SSE event handler when onEvent is called
      window.backend.onEvent = vi.fn((handler) => {
        eventHandler = handler;
        return () => {};
      });
    });

    it('updates badgeMap for cruise events on non-selected device', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Select device A
      window.backend.send.mockResolvedValueOnce({
        result: { location: null, cruise: null, route: null, routeCruise: null, tunnel: null },
      });
      await act(async () => {
        await result.current.selectDevice('device-A');
      });

      // Fire cruiseStarted for device B (non-selected)
      await act(async () => {
        eventHandler({
          event: 'cruiseStarted',
          data: { deviceId: 'device-B', state: 'running', speedKmh: 5 },
        });
      });

      // Badge map should have device-B as cruising
      expect(result.current.badgeMap['device-B']).toEqual(
        expect.objectContaining({ cruising: true, cruisePaused: false })
      );

      // Full cruiseStatus should NOT be updated (still null, device-B is not selected)
      expect(result.current.cruiseStatus).toBeNull();
    });

    it('updates full state for cruise events on selected device', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Select device A
      window.backend.send.mockResolvedValueOnce({
        result: { location: null, cruise: null, route: null, routeCruise: null, tunnel: null },
      });
      await act(async () => {
        await result.current.selectDevice('device-A');
      });

      // Fire cruiseStarted for device A (selected)
      const cruiseData = { deviceId: 'device-A', state: 'running', speedKmh: 10, remainingKm: 2 };
      await act(async () => {
        eventHandler({ event: 'cruiseStarted', data: cruiseData });
      });

      // Full cruiseStatus should be updated
      expect(result.current.cruiseStatus).toEqual(cruiseData);
      // Badge map should also be updated
      expect(result.current.badgeMap['device-A']).toEqual(
        expect.objectContaining({ cruising: true, cruisePaused: false })
      );
    });

    it('updates badgeMap for route events on non-selected device', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Select device A
      window.backend.send.mockResolvedValueOnce({
        result: { location: null, cruise: null, route: null, routeCruise: null, tunnel: null },
      });
      await act(async () => {
        await result.current.selectDevice('device-A');
      });

      // Fire routeStarted for device C (non-selected)
      await act(async () => {
        eventHandler({
          event: 'routeStarted',
          data: { deviceId: 'device-C', totalSegments: 5, currentSegmentIndex: 1 },
        });
      });

      // Badge should show route progress
      expect(result.current.badgeMap['device-C']).toEqual(
        expect.objectContaining({ routeCruising: true, routePaused: false, routeProgress: '1/5' })
      );

      // Full routeStatus should NOT update (device-C is not selected)
      expect(result.current.routeStatus).toBeNull();
    });

    it('clears badge on cruiseArrived for non-selected device', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Select device A
      window.backend.send.mockResolvedValueOnce({
        result: { location: null, cruise: null, route: null, routeCruise: null, tunnel: null },
      });
      await act(async () => {
        await result.current.selectDevice('device-A');
      });

      // Start cruise on device B
      await act(async () => {
        eventHandler({
          event: 'cruiseStarted',
          data: { deviceId: 'device-B', state: 'running' },
        });
      });
      expect(result.current.badgeMap['device-B']?.cruising).toBe(true);

      // Cruise arrives on device B
      await act(async () => {
        eventHandler({
          event: 'cruiseArrived',
          data: { deviceId: 'device-B', location: { latitude: 1, longitude: 2 } },
        });
      });
      expect(result.current.badgeMap['device-B']?.cruising).toBe(false);
    });
  });

  describe('device switch state population', () => {
    let eventHandler;

    beforeEach(() => {
      window.backend.onEvent = vi.fn((handler) => {
        eventHandler = handler;
        return () => {};
      });
    });

    it('populates all state from getDeviceState response', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Mock getDeviceState response with full state
      const deviceState = {
        location: { latitude: 25.0, longitude: 121.5 },
        tunnel: { status: 'connected', address: '127.0.0.1', port: 1234 },
        cruise: { state: 'running', speedKmh: 10, remainingKm: 5 },
        route: { waypoints: [{ lat: 25, lng: 121 }], segments: [] },
        routeCruise: { state: 'running', currentSegmentIndex: 1, totalSegments: 3, speedKmh: 8 },
      };
      window.backend.send.mockResolvedValueOnce({ result: deviceState });

      await act(async () => {
        await result.current.selectDevice('device-X');
      });

      expect(result.current.location).toEqual(deviceState.location);
      expect(result.current.tunnelStatus).toEqual(deviceState.tunnel);
      expect(result.current.cruiseStatus).toEqual(deviceState.cruise);
      expect(result.current.routeState).toEqual(deviceState.route);
      expect(result.current.routeStatus).toEqual(deviceState.routeCruise);
    });

    it('clears state when getDeviceState returns null fields', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // First select a device with active state
      window.backend.send.mockResolvedValueOnce({
        result: {
          location: { latitude: 10, longitude: 20 },
          cruise: { state: 'running', speedKmh: 5 },
          tunnel: { status: 'connected' },
          route: { waypoints: [] },
          routeCruise: { state: 'running' },
        },
      });
      await act(async () => {
        await result.current.selectDevice('device-active');
      });

      expect(result.current.location).toBeTruthy();
      expect(result.current.cruiseStatus).toBeTruthy();

      // Now switch to idle device (all null)
      window.backend.send.mockResolvedValueOnce({
        result: {
          location: null,
          cruise: null,
          tunnel: null,
          route: null,
          routeCruise: null,
        },
      });
      await act(async () => {
        await result.current.selectDevice('device-idle');
      });

      expect(result.current.location).toBeNull();
      expect(result.current.cruiseStatus).toBeNull();
      expect(result.current.tunnelStatus).toBeNull();
      expect(result.current.routeState).toBeNull();
      expect(result.current.routeStatus).toBeNull();
    });

    it('shows and hides deviceSwitchLoading during switch', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      let resolveSwitch;
      window.backend.send.mockReturnValueOnce(
        new Promise((resolve) => { resolveSwitch = resolve; })
      );

      // Start device switch (don't await yet)
      let switchPromise;
      act(() => {
        switchPromise = result.current.selectDevice('device-slow');
      });

      // Loading should be true while waiting
      expect(result.current.deviceSwitchLoading).toBe(true);

      // Resolve the request
      await act(async () => {
        resolveSwitch({ result: { location: null, cruise: null, tunnel: null, route: null, routeCruise: null } });
        await switchPromise;
      });

      expect(result.current.deviceSwitchLoading).toBe(false);
    });

    it('clears badge on disconnectDevice', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      // Seed badge map with getAllDeviceStates
      window.backend.send.mockResolvedValueOnce({
        result: { 'device-A': { cruising: true }, 'device-B': { routeCruising: true } },
      });
      await act(async () => {
        await result.current.seedBadges();
      });

      expect(result.current.badgeMap['device-A']).toBeTruthy();
      expect(result.current.badgeMap['device-B']).toBeTruthy();

      // Disconnect device A
      window.backend.send.mockResolvedValueOnce({ result: { success: true } });
      await act(async () => {
        await result.current.disconnectDevice('device-A');
      });

      // device-A badge should be cleared, device-B should remain
      expect(result.current.badgeMap['device-A']).toBeUndefined();
      expect(result.current.badgeMap['device-B']).toBeTruthy();
    });
  });

  describe('seedBadges', () => {
    it('seeds badgeMap from getAllDeviceStates on call', async () => {
      const { result } = renderHook(() => useBackend());

      await act(async () => {
        await Promise.resolve();
      });

      const badgeData = {
        'dev-1': { cruising: true, cruisePaused: false, routeCruising: false, routePaused: false },
        'dev-2': { cruising: false, cruisePaused: false, routeCruising: true, routePaused: true, routeProgress: '2/5' },
      };
      window.backend.send.mockResolvedValueOnce({ result: badgeData });

      await act(async () => {
        await result.current.seedBadges();
      });

      expect(result.current.badgeMap).toEqual(badgeData);
    });
  });
});
