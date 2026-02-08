import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRouteCruise } from './useRouteCruise.js';

describe('useRouteCruise', () => {
  let mockBackendFunctions;
  let mockRouteStatus;
  let mockRouteState;
  let mockLocation;
  let mockSelectedDevice;

  beforeEach(() => {
    // Mock all backend action functions
    mockBackendFunctions = {
      addRouteWaypoint: vi.fn().mockResolvedValue({ success: true }),
      undoRouteWaypoint: vi.fn().mockResolvedValue({ success: true }),
      startRouteCruise: vi.fn().mockResolvedValue({ success: true }),
      pauseRouteCruise: vi.fn().mockResolvedValue({ success: true }),
      resumeRouteCruise: vi.fn().mockResolvedValue({ success: true }),
      rerouteRouteCruise: vi.fn().mockResolvedValue({ success: true }),
      stopRouteCruise: vi.fn().mockResolvedValue({ success: true }),
      setRouteCruiseSpeed: vi.fn().mockResolvedValue({ success: true }),
      clearRoute: vi.fn().mockResolvedValue({ success: true }),
      setRouteLoopMode: vi.fn().mockResolvedValue({ success: true }),
    };

    // Mock state values
    mockRouteStatus = null;
    mockRouteState = {
      waypoints: [],
      segments: [],
      loopMode: false,
      totalDistanceKm: 0,
    };
    mockLocation = {
      latitude: 37.7749,
      longitude: -122.4194,
    };
    mockSelectedDevice = { id: 'test-device' };
  });

  const renderUseRouteCruise = (overrides = {}) => {
    return renderHook(() => useRouteCruise({
      ...mockBackendFunctions,
      routeStatus: mockRouteStatus,
      routeState: mockRouteState,
      location: mockLocation,
      selectedDevice: mockSelectedDevice,
      ...overrides,
    }));
  };

  describe('initial state', () => {
    it('initializes with routeMode false', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.routeMode).toBe(false);
    });

    it('initializes with empty waypoints and segments', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.waypoints).toEqual([]);
      expect(result.current.segments).toEqual([]);
    });

    it('initializes with loopMode false', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.loopMode).toBe(false);
    });

    it('initializes with totalDistanceKm 0', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.totalDistanceKm).toBe(0);
    });

    it('initializes with hasRoute false when no waypoints', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.hasRoute).toBe(false);
    });

    it('initializes with isRouteCruising false', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(false);
    });

    it('initializes with isRoutePaused false', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.isRoutePaused).toBe(false);
    });

    it('initializes with progressInfo null when not cruising', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toBeNull();
    });
  });

  describe('addWaypoint', () => {
    it('auto-sets START from device location when no waypoints exist', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.addWaypoint(40.7128, -74.0060); // NYC coords
      });

      // Should call addRouteWaypoint twice: once for START, once for clicked point
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenCalledTimes(2);
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenNthCalledWith(
        1,
        mockLocation.latitude,
        mockLocation.longitude
      );
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenNthCalledWith(
        2,
        40.7128,
        -74.0060
      );
    });

    it('does not auto-set START when waypoints already exist', async () => {
      mockRouteState = {
        waypoints: [{ lat: 37.7749, lng: -122.4194 }],
        segments: [],
        loopMode: false,
        totalDistanceKm: 0,
      };

      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.addWaypoint(40.7128, -74.0060);
      });

      // Should only call once for the new waypoint
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenCalledTimes(1);
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenCalledWith(40.7128, -74.0060);
    });

    it('does not auto-set START when device has no location', async () => {
      mockLocation = null;

      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.addWaypoint(40.7128, -74.0060);
      });

      // Should only call once (no auto-START)
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenCalledTimes(1);
      expect(mockBackendFunctions.addRouteWaypoint).toHaveBeenCalledWith(40.7128, -74.0060);
    });

    it('returns early when no device is selected', async () => {
      mockSelectedDevice = null;

      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.addWaypoint(40.7128, -74.0060);
      });

      expect(mockBackendFunctions.addRouteWaypoint).not.toHaveBeenCalled();
    });

    it('updates waypoint list after re-render with new routeState', async () => {
      const { result, rerender } = renderUseRouteCruise();

      // Add waypoint
      await act(async () => {
        await result.current.addWaypoint(40.7128, -74.0060);
      });

      // Simulate backend updating routeState
      mockRouteState = {
        waypoints: [
          { lat: 37.7749, lng: -122.4194 },
          { lat: 40.7128, lng: -74.0060 },
        ],
        segments: [{ start: 0, end: 1 }],
        loopMode: false,
        totalDistanceKm: 4132.5,
      };

      rerender();

      expect(result.current.waypoints).toHaveLength(2);
      expect(result.current.segments).toHaveLength(1);
      expect(result.current.hasRoute).toBe(true);
    });
  });

  describe('toggleLoopMode', () => {
    it('calls setRouteLoopMode with toggled value from false to true', async () => {
      mockRouteState.loopMode = false;

      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.toggleLoopMode();
      });

      expect(mockBackendFunctions.setRouteLoopMode).toHaveBeenCalledWith(true);
    });

    it('calls setRouteLoopMode with toggled value from true to false', async () => {
      mockRouteState.loopMode = true;

      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.toggleLoopMode();
      });

      expect(mockBackendFunctions.setRouteLoopMode).toHaveBeenCalledWith(false);
    });
  });

  describe('startRoute', () => {
    it('calls startRouteCruise with speed parameter', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.startRoute(50);
      });

      expect(mockBackendFunctions.startRouteCruise).toHaveBeenCalledWith(50);
    });

    it('returns the result from startRouteCruise', async () => {
      const mockResult = { success: true, sessionId: 'test-session' };
      mockBackendFunctions.startRouteCruise.mockResolvedValue(mockResult);

      const { result } = renderUseRouteCruise();

      let returnValue;
      await act(async () => {
        returnValue = await result.current.startRoute(30);
      });

      expect(returnValue).toEqual(mockResult);
    });
  });

  describe('pauseRoute', () => {
    it('calls pauseRouteCruise', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.pauseRoute();
      });

      expect(mockBackendFunctions.pauseRouteCruise).toHaveBeenCalled();
    });
  });

  describe('resumeRoute', () => {
    it('calls rerouteRouteCruise with current location when location is set', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.resumeRoute();
      });

      expect(mockBackendFunctions.rerouteRouteCruise).toHaveBeenCalledWith(
        mockLocation.latitude,
        mockLocation.longitude
      );
    });

    it('falls back to resumeRouteCruise when no location', async () => {
      mockLocation = null;
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.resumeRoute();
      });

      expect(mockBackendFunctions.resumeRouteCruise).toHaveBeenCalled();
      expect(mockBackendFunctions.rerouteRouteCruise).not.toHaveBeenCalled();
    });
  });

  describe('stopRoute', () => {
    it('calls stopRouteCruise', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.stopRoute();
      });

      expect(mockBackendFunctions.stopRouteCruise).toHaveBeenCalled();
    });
  });

  describe('setRouteSpeed', () => {
    it('calls setRouteCruiseSpeed with speed parameter', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.setRouteSpeed(75);
      });

      expect(mockBackendFunctions.setRouteCruiseSpeed).toHaveBeenCalledWith(75);
    });
  });

  describe('clearRoute', () => {
    it('calls backend clearRoute function', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.clearRoute();
      });

      expect(mockBackendFunctions.clearRoute).toHaveBeenCalled();
    });
  });

  describe('undoWaypoint', () => {
    it('calls undoRouteWaypoint', async () => {
      const { result } = renderUseRouteCruise();

      await act(async () => {
        await result.current.undoWaypoint();
      });

      expect(mockBackendFunctions.undoRouteWaypoint).toHaveBeenCalled();
    });
  });

  describe('isRouteCruising derivation', () => {
    it('is true when routeStatus.state is "running"', () => {
      mockRouteStatus = { state: 'running' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(true);
    });

    it('is true when routeStatus.state is "paused"', () => {
      mockRouteStatus = { state: 'paused' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(true);
    });

    it('is false when routeStatus.state is "idle"', () => {
      mockRouteStatus = { state: 'idle' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(false);
    });

    it('is false when routeStatus is null', () => {
      mockRouteStatus = null;

      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(false);
    });

    it('is false when routeStatus.state is undefined', () => {
      mockRouteStatus = {};

      const { result } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(false);
    });
  });

  describe('isRoutePaused derivation', () => {
    it('is true when routeStatus.state is "paused"', () => {
      mockRouteStatus = { state: 'paused' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRoutePaused).toBe(true);
    });

    it('is false when routeStatus.state is "running"', () => {
      mockRouteStatus = { state: 'running' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRoutePaused).toBe(false);
    });

    it('is false when routeStatus.state is "idle"', () => {
      mockRouteStatus = { state: 'idle' };

      const { result } = renderUseRouteCruise();

      expect(result.current.isRoutePaused).toBe(false);
    });

    it('is false when routeStatus is null', () => {
      mockRouteStatus = null;

      const { result } = renderUseRouteCruise();

      expect(result.current.isRoutePaused).toBe(false);
    });
  });

  describe('progressInfo computation', () => {
    it('computes correctly when route is running', () => {
      mockRouteStatus = {
        state: 'running',
        currentSegmentIndex: 2,
        totalSegments: 5,
        remainingDistanceKm: 15.3,
        distanceTraveledKm: 8.7,
        loopsCompleted: 0,
      };
      mockRouteState.segments = [{}, {}, {}, {}, {}]; // 5 segments

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toEqual({
        currentSegment: 3, // index 2 + 1
        totalSegments: 5,
        remainingKm: 15.3,
        traveledKm: 8.7,
        loopsCompleted: 0,
      });
    });

    it('computes correctly when route is paused', () => {
      mockRouteStatus = {
        state: 'paused',
        currentSegmentIndex: 0,
        totalSegments: 3,
        remainingDistanceKm: 20.5,
        distanceTraveledKm: 2.1,
        loopsCompleted: 1,
      };

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toEqual({
        currentSegment: 1, // index 0 + 1
        totalSegments: 3,
        remainingKm: 20.5,
        traveledKm: 2.1,
        loopsCompleted: 1,
      });
    });

    it('returns null when route is not cruising', () => {
      mockRouteStatus = { state: 'idle' };

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toBeNull();
    });

    it('returns null when routeStatus is null', () => {
      mockRouteStatus = null;

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toBeNull();
    });

    it('handles missing fields with default values', () => {
      mockRouteStatus = {
        state: 'running',
        // Missing all optional fields
      };

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo).toEqual({
        currentSegment: 1, // 0 + 1
        totalSegments: 0, // Falls back to segments.length (empty)
        remainingKm: 0,
        traveledKm: 0,
        loopsCompleted: 0,
      });
    });

    it('uses routeStatus.totalSegments over segments.length when available', () => {
      mockRouteStatus = {
        state: 'running',
        currentSegmentIndex: 1,
        totalSegments: 10, // Backend says 10 segments
        remainingDistanceKm: 5,
        distanceTraveledKm: 5,
        loopsCompleted: 0,
      };
      mockRouteState.segments = [{}, {}, {}]; // Only 3 in state (stale)

      const { result } = renderUseRouteCruise();

      expect(result.current.progressInfo.totalSegments).toBe(10);
    });
  });

  describe('hasRoute', () => {
    it('is false when no waypoints', () => {
      mockRouteState.waypoints = [];

      const { result } = renderUseRouteCruise();

      expect(result.current.hasRoute).toBe(false);
    });

    it('is false when only 1 waypoint', () => {
      mockRouteState.waypoints = [{ lat: 37.7749, lng: -122.4194 }];

      const { result } = renderUseRouteCruise();

      expect(result.current.hasRoute).toBe(false);
    });

    it('is true when 2 waypoints', () => {
      mockRouteState.waypoints = [
        { lat: 37.7749, lng: -122.4194 },
        { lat: 40.7128, lng: -74.0060 },
      ];

      const { result } = renderUseRouteCruise();

      expect(result.current.hasRoute).toBe(true);
    });

    it('is true when 3+ waypoints', () => {
      mockRouteState.waypoints = [
        { lat: 37.7749, lng: -122.4194 },
        { lat: 40.7128, lng: -74.0060 },
        { lat: 34.0522, lng: -118.2437 },
      ];

      const { result } = renderUseRouteCruise();

      expect(result.current.hasRoute).toBe(true);
    });
  });

  describe('setRouteMode', () => {
    it('allows toggling routeMode from false to true', () => {
      const { result } = renderUseRouteCruise();

      expect(result.current.routeMode).toBe(false);

      act(() => {
        result.current.setRouteMode(true);
      });

      expect(result.current.routeMode).toBe(true);
    });

    it('allows toggling routeMode from true to false', () => {
      const { result } = renderUseRouteCruise();

      act(() => {
        result.current.setRouteMode(true);
      });

      expect(result.current.routeMode).toBe(true);

      act(() => {
        result.current.setRouteMode(false);
      });

      expect(result.current.routeMode).toBe(false);
    });
  });

  describe('reactive updates', () => {
    it('updates waypoints when routeState changes', () => {
      const { result, rerender } = renderUseRouteCruise();

      expect(result.current.waypoints).toEqual([]);

      // Update routeState
      mockRouteState = {
        waypoints: [
          { lat: 37.7749, lng: -122.4194 },
          { lat: 40.7128, lng: -74.0060 },
        ],
        segments: [],
        loopMode: false,
        totalDistanceKm: 4132.5,
      };

      rerender();

      expect(result.current.waypoints).toHaveLength(2);
      expect(result.current.totalDistanceKm).toBe(4132.5);
    });

    it('updates loopMode when routeState changes', () => {
      const { result, rerender } = renderUseRouteCruise();

      expect(result.current.loopMode).toBe(false);

      mockRouteState = {
        ...mockRouteState,
        loopMode: true,
      };

      rerender();

      expect(result.current.loopMode).toBe(true);
    });

    it('updates isRouteCruising when routeStatus changes', () => {
      const { result, rerender } = renderUseRouteCruise();

      expect(result.current.isRouteCruising).toBe(false);

      mockRouteStatus = { state: 'running' };

      rerender();

      expect(result.current.isRouteCruising).toBe(true);
    });
  });

  describe('edge cases', () => {
    it('handles null routeState gracefully', () => {
      const { result } = renderUseRouteCruise({ routeState: null });

      expect(result.current.waypoints).toEqual([]);
      expect(result.current.segments).toEqual([]);
      expect(result.current.loopMode).toBe(false);
      expect(result.current.totalDistanceKm).toBe(0);
      expect(result.current.hasRoute).toBe(false);
    });

    it('handles undefined routeState gracefully', () => {
      const { result } = renderUseRouteCruise({ routeState: undefined });

      expect(result.current.waypoints).toEqual([]);
      expect(result.current.segments).toEqual([]);
      expect(result.current.loopMode).toBe(false);
      expect(result.current.totalDistanceKm).toBe(0);
    });

    it('handles partial routeState with missing fields', () => {
      const { result } = renderUseRouteCruise({
        routeState: { waypoints: [{ lat: 1, lng: 2 }] },
      });

      expect(result.current.waypoints).toHaveLength(1);
      expect(result.current.segments).toEqual([]);
      expect(result.current.loopMode).toBe(false);
    });

    it('exposes routeStatus in return value', () => {
      mockRouteStatus = { state: 'running', currentSegmentIndex: 1 };

      const { result } = renderUseRouteCruise();

      expect(result.current.routeStatus).toBe(mockRouteStatus);
    });
  });
});
