import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch } from '../../src/utils/api.js';

describe('apiFetch', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    localStorage.clear();
    mockFetch.mockResolvedValue(new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('should call fetch with the correct URL', async () => {
    await apiFetch('/test-endpoint');
    expect(mockFetch).toHaveBeenCalledWith('/test-endpoint', expect.anything());
  });

  it('should add Authorization header when credentials exist in localStorage', async () => {
    const credentials = 'test-user:test-password';
    localStorage.setItem('auth_credentials', credentials);

    await apiFetch('/test-endpoint');

    const fetchArgs = mockFetch.mock.calls[0];
    const init = fetchArgs[1];
    const headers = init.headers as Headers;

    expect(headers.get('Authorization')).toBe(`Basic ${credentials}`);
  });

  it('should not add Authorization header when credentials do not exist', async () => {
    await apiFetch('/test-endpoint');

    const fetchArgs = mockFetch.mock.calls[0];
    const init = fetchArgs[1];
    const headers = init.headers as Headers;

    expect(headers.has('Authorization')).toBe(false);
  });

  it('should preserve and merge existing headers', async () => {
    const credentials = 'test-user:test-password';
    localStorage.setItem('auth_credentials', credentials);

    await apiFetch('/test-endpoint', {
      headers: {
        'X-Custom-Header': 'custom-value',
      },
    });

    const fetchArgs = mockFetch.mock.calls[0];
    const init = fetchArgs[1];
    const headers = init.headers as Headers;

    expect(headers.get('X-Custom-Header')).toBe('custom-value');
    expect(headers.get('Authorization')).toBe(`Basic ${credentials}`);
  });

  it('should return the fetch response', async () => {
    const response = await apiFetch('/test-endpoint');
    const data = await response.json();
    expect(data).toEqual({ success: true });
    expect(response.status).toBe(200);
  });

  it('should handle 401 status code (optional logout logic placeholder)', async () => {
    mockFetch.mockResolvedValue(new Response(null, { status: 401 }));

    const response = await apiFetch('/test-endpoint');
    expect(response.status).toBe(401);
  });
});
