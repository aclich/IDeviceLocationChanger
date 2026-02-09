import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMovement } from './useMovement.js';

// Mock coordinateCalculator
vi.mock('../utils/coordinateCalculator', () => ({
  moveLocation: vi.fn((lat, lon) => [lat + 0.0001, lon + 0.0001]),
  directionFromOffset: vi.fn(() => 0),
  speedMultiplier: vi.fn(() => 1),
}));

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

  // Note: Cruise mode has been moved to the backend (useBackend hook).
  // See backend/test_cruise.py for cruise mode tests.

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

    it('does not move when joystick is near center', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.updateJoystick(0.5, 0.5, 50); // Very small movement
      });

      expect(result.current.isMoving).toBe(false);
    });

    it('calls setLocation during movement', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      await act(async () => {
        result.current.updateJoystick(10, 10, 50);
      });

      // Advance timer to trigger movement loop
      await act(async () => {
        vi.advanceTimersByTime(300);
        await Promise.resolve();
      });

      expect(mockSetLocation).toHaveBeenCalled();
    });
  });

  describe('cleanup', () => {
    it('clears interval on unmount', async () => {
      const location = { latitude: 25.0, longitude: 121.0 };

      const { result, unmount } = renderHook(() =>
        useMovement({ location, setLocation: mockSetLocation })
      );

      // Start joystick movement
      await act(async () => {
        result.current.updateJoystick(10, 10, 50);
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
