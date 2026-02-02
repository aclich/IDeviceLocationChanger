import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import reverseGeocode from './reverseGeocode';

describe('reverseGeocode', () => {
  let mockFetch;
  const originalNavigator = global.navigator;

  beforeEach(() => {
    mockFetch = vi.fn();
    global.fetch = mockFetch;
    // Mock navigator.language
    Object.defineProperty(global, 'navigator', {
      value: { language: 'zh-TW' },
      writable: true,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    global.navigator = originalNavigator;
  });

  it('should return formatted location name on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'Taiwan',
          city: 'Taipei',
          suburb: 'Zhongzheng',
        },
      }),
    });

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('Taiwan / Taipei / Zhongzheng');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('lat=24.9536'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept-Language': 'zh-TW',
          'User-Agent': 'LocationSimulator/1.0',
        }),
      })
    );
  });

  it('should use navigator.language for Accept-Language header', async () => {
    Object.defineProperty(global, 'navigator', {
      value: { language: 'ja-JP' },
      writable: true,
    });

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: { country: 'Japan', city: 'Tokyo' },
      }),
    });

    await reverseGeocode(35.6762, 139.6503);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept-Language': 'ja-JP',
        }),
      })
    );
  });

  it('should fallback to "en" if navigator.language is not available', async () => {
    Object.defineProperty(global, 'navigator', {
      value: { language: undefined },
      writable: true,
    });

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: { country: 'United States', city: 'New York' },
      }),
    });

    await reverseGeocode(40.7128, -74.0060);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept-Language': 'en',
        }),
      })
    );
  });

  it('should handle response with only country and city', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'Japan',
          city: 'Tokyo',
        },
      }),
    });

    const result = await reverseGeocode(35.6762, 139.6503);

    expect(result).toBe('Japan / Tokyo');
  });

  it('should handle response with only country', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'Antarctica',
        },
      }),
    });

    const result = await reverseGeocode(-82.8628, 135.0000);

    expect(result).toBe('Antarctica');
  });

  it('should use alternative address fields when primary not available', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'France',
          municipality: 'Paris',
          neighbourhood: 'Le Marais',
        },
      }),
    });

    const result = await reverseGeocode(48.8566, 2.3522);

    expect(result).toBe('France / Paris / Le Marais');
  });

  it('should use village for district when available', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'Thailand',
          county: 'Phuket',
          village: 'Patong',
        },
      }),
    });

    const result = await reverseGeocode(7.8804, 98.2920);

    expect(result).toBe('Thailand / Phuket / Patong');
  });

  it('should fallback to coordinates on API error', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    });

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('24.953600, 121.551800');
  });

  it('should fallback to coordinates on network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('24.953600, 121.551800');
  });

  it('should handle API error response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        error: 'Unable to geocode',
      }),
    });

    const result = await reverseGeocode(0, 0);

    expect(result).toBe('0.000000, 0.000000');
  });

  it('should return "Unknown Location" for empty address', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {},
      }),
    });

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('Unknown Location');
  });

  it('should return "Unknown Location" for null address', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: null,
      }),
    });

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('Unknown Location');
  });

  it('should use display_name as last resort', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          display_name: 'Some obscure place, middle of nowhere',
        },
      }),
    });

    const result = await reverseGeocode(24.9536, 121.5518);

    expect(result).toBe('Some obscure place, middle of nowhere');
  });

  it('should include correct URL parameters', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: { country: 'Test' },
      }),
    });

    await reverseGeocode(24.9536, 121.5518);

    const url = mockFetch.mock.calls[0][0];
    expect(url).toContain('lat=24.9536');
    expect(url).toContain('lon=121.5518');
    expect(url).toContain('format=json');
    expect(url).toContain('zoom=14');
  });

  it('should handle negative coordinates correctly', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        address: {
          country: 'Brazil',
          city: 'Rio de Janeiro',
        },
      }),
    });

    const result = await reverseGeocode(-22.9068, -43.1729);

    expect(result).toBe('Brazil / Rio de Janeiro');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('lat=-22.9068'),
      expect.any(Object)
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('lon=-43.1729'),
      expect.any(Object)
    );
  });
});
