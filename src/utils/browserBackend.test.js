import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('browserBackend', () => {
  beforeEach(() => {
    vi.resetModules();
    delete window.backend;
  });

  describe('BACKEND_URL', () => {
    it('uses default URL when VITE_BACKEND_URL is not set', async () => {
      vi.stubEnv('VITE_BACKEND_URL', '');

      const { default: browserBackend } = await import('./browserBackend.js');

      // Test by checking what URL checkHealth would use
      // We mock fetch to capture the URL
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true });

      await browserBackend.checkHealth();

      expect(fetchSpy).toHaveBeenCalledWith('http://127.0.0.1:8765/health');
      fetchSpy.mockRestore();
    });

    it('uses custom URL from VITE_BACKEND_URL environment variable', async () => {
      vi.stubEnv('VITE_BACKEND_URL', 'http://custom-host:9000');

      const { default: browserBackend } = await import('./browserBackend.js');

      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true });

      await browserBackend.checkHealth();

      expect(fetchSpy).toHaveBeenCalledWith('http://custom-host:9000/health');
      fetchSpy.mockRestore();
    });
  });

  describe('isBrowserMode', () => {
    it('returns true when window.backend does not exist', async () => {
      delete window.backend;

      const { isBrowserMode } = await import('./browserBackend.js');

      expect(isBrowserMode()).toBe(true);
    });

    it('returns true when window.backend.isBrowserMode is true', async () => {
      window.backend = { isBrowserMode: true };

      const { isBrowserMode } = await import('./browserBackend.js');

      expect(isBrowserMode()).toBe(true);
    });

    it('returns false when window.backend exists without isBrowserMode flag (Electron)', async () => {
      window.backend = { send: vi.fn(), onEvent: vi.fn() };

      const { isBrowserMode } = await import('./browserBackend.js');

      expect(isBrowserMode()).toBe(false);
    });
  });

  describe('initBrowserBackend', () => {
    it('initializes window.backend when it does not exist', async () => {
      delete window.backend;

      const { initBrowserBackend } = await import('./browserBackend.js');
      const result = initBrowserBackend();

      expect(result).toBe(true);
      expect(window.backend).toBeDefined();
      expect(window.backend.isBrowserMode).toBe(true);
      expect(typeof window.backend.send).toBe('function');
      expect(typeof window.backend.onEvent).toBe('function');
      expect(typeof window.backend.checkHealth).toBe('function');
    });

    it('does not override existing window.backend (Electron mode)', async () => {
      const electronBackend = { send: vi.fn(), onEvent: vi.fn() };
      window.backend = electronBackend;

      const { initBrowserBackend } = await import('./browserBackend.js');
      const result = initBrowserBackend();

      expect(result).toBe(false);
      expect(window.backend).toBe(electronBackend);
    });
  });

  describe('checkHealth', () => {
    it('returns true when backend responds with ok', async () => {
      const { default: browserBackend } = await import('./browserBackend.js');

      vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true });

      const result = await browserBackend.checkHealth();

      expect(result).toBe(true);
    });

    it('returns false when backend responds with error', async () => {
      const { default: browserBackend } = await import('./browserBackend.js');

      vi.spyOn(global, 'fetch').mockResolvedValue({ ok: false });

      const result = await browserBackend.checkHealth();

      expect(result).toBe(false);
    });

    it('returns false when fetch throws an error', async () => {
      const { default: browserBackend } = await import('./browserBackend.js');

      vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network error'));

      const result = await browserBackend.checkHealth();

      expect(result).toBe(false);
    });
  });

  describe('send', () => {
    it('sends JSON-RPC request to /rpc endpoint', async () => {
      const { default: browserBackend } = await import('./browserBackend.js');

      const mockResponse = { result: { devices: [] } };
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await browserBackend.send('listDevices', { filter: 'all' });

      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/rpc'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: expect.stringContaining('"method":"listDevices"'),
        })
      );
      expect(result).toEqual(mockResponse);
    });

    it('throws error when response is not ok', async () => {
      const { default: browserBackend } = await import('./browserBackend.js');

      vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: false,
        status: 500,
      });

      await expect(browserBackend.send('listDevices')).rejects.toThrow('HTTP error: 500');
    });
  });
});
