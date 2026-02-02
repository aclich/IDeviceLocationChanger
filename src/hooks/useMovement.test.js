import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMovement } from './useMovement.js';

// Mock coordinateCalculator
vi.mock('../utils/coordinateCalculator', () => ({
  moveLocation: vi.fn((lat, lon) => [lat + 0.0001, lon + 0.0001]),
  directionFromOffset: vi.fn(() => 0),
  speedMultiplier: vi.fn(() => 1),
  bearingTo: vi.fn(() => 45),
  distanceBetween: vi.fn(() => 1.0), // 1km by default
}));

import { distanceBetween } from '../utils/coordinateCalculator';

describe('useMovement', () => {
  let mockSetLocation;

  beforeEach(() => {
    vi.useFakeTimers();
    mockSetLocation = vi.fn().mockResolvedValue({});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('cruise mode', () => {
    it('starts cruise mode with target', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };
      const target = { latitude: 25.1, longitude: 121.1 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.startCruise(target);
      });

      expect(result.current.isMoving).toBe(true);
      expect(result.current.cruiseTarget).toEqual(target);
    });

    it('stops cruise mode and clears target when stopCruise is called', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };
      const target = { latitude: 25.1, longitude: 121.1 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.startCruise(target);
      });

      expect(result.current.cruiseTarget).toEqual(target);

      await act(async () => {
        result.current.stopCruise();
      });

      expect(result.current.isMoving).toBe(false);
      expect(result.current.cruiseTarget).toBe(null);
    });

    it('clears cruiseTarget when reaching destination', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };
      const target = { latitude: 25.0001, longitude: 121.0001 }; // Very close

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      // Start far away
      distanceBetween.mockReturnValue(1.0); // 1km away

      await act(async () => {
        result.current.startCruise(target);
      });

      expect(result.current.isMoving).toBe(true);
      expect(result.current.cruiseTarget).toEqual(target);

      // Simulate arrival - distance is now less than threshold (0.005 km = 5m)
      distanceBetween.mockReturnValue(0.003); // 3 meters - below ARRIVAL_THRESHOLD_KM

      // Advance timer to trigger movement loop
      await act(async () => {
        vi.advanceTimersByTime(500);
        await Promise.resolve();
      });

      // BUG: cruiseTarget should be null after arrival, but currently it's not
      // This test documents the expected behavior after the fix
      expect(result.current.isMoving).toBe(false);
      expect(result.current.cruiseTarget).toBe(null); // This will fail until bug is fixed
    });

    it('does not start cruise without location', async () => {
      const { result } = renderHook(() =>
        useMovement({ location: null, setLocation: mockSetLocation })
      );

      const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});

      await act(async () => {
        const started = result.current.startCruise({ latitude: 25.1, longitude: 121.1 });
        expect(started).toBe(false);
      });

      expect(result.current.isMoving).toBe(false);
      consoleWarn.mockRestore();
    });

    it('does not start cruise without target', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});

      await act(async () => {
        const started = result.current.startCruise(null);
        expect(started).toBe(false);
      });

      expect(result.current.isMoving).toBe(false);
      consoleWarn.mockRestore();
    });
  });

  describe('speed control', () => {
    it('updates speed within valid range', async () => {
      const { result } = renderHook(() =>
        useMovement({ location: null, setLocation: mockSetLocation })
      );

      expect(result.current.speed).toBe(5.0);

      await act(async () => {
        result.current.setSpeed(10);
      });

      expect(result.current.speed).toBe(10);
    });

    it('clamps speed to minimum', async () => {
      const { result } = renderHook(() =>
        useMovement({ location: null, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.setSpeed(0);
      });

      expect(result.current.speed).toBe(1);
    });

    it('clamps speed to maximum', async () => {
      const { result } = renderHook(() =>
        useMovement({ location: null, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.setSpeed(100);
      });

      expect(result.current.speed).toBe(50);
    });
  });

  describe('joystick mode', () => {
    it('starts movement when joystick moves significantly', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.updateJoystick(10, 10, 50);
      });

      expect(result.current.isMoving).toBe(true);
    });

    it('stops movement when joystick released', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.updateJoystick(10, 10, 50);
      });

      expect(result.current.isMoving).toBe(true);

      await act(async () => {
        result.current.releaseJoystick();
      });

      expect(result.current.isMoving).toBe(false);
    });

    it('does not start joystick movement without location', async () => {
      const { result } = renderHook(() =>
        useMovement({ location: null, setLocation: mockSetLocation })
      );

      const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});

      await act(async () => {
        result.current.updateJoystick(10, 10, 50);
      });

      expect(result.current.isMoving).toBe(false);
      consoleWarn.mockRestore();
    });
  });

  describe('cleanup', () => {
    it('clears interval on unmount', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };
      const target = { latitude: 25.1, longitude: 121.1 };

      const { result, unmount } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.startCruise(target);
      });

      expect(result.current.isMoving).toBe(true);

      unmount();

      // Verify no errors occur after unmount
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });
    });
  });
});
