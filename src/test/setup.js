import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock window.backend for tests
global.window = global.window || {};

// Reset mocks between tests
beforeEach(() => {
  vi.clearAllMocks();
  delete window.backend;
});
