import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, money, setCsrf } from './api';

afterEach(() => { vi.unstubAllGlobals(); setCsrf(''); });

describe('expense presentation and browser requests', () => {
  it('formats minor units without treating yen as cents', () => {
    expect(money(34900, 'INR')).toContain('349.00');
    expect(money(100, 'JPY')).toContain('100');
    expect(money(100, 'JPY')).not.toContain('1.00');
  });

  it('recovers CSRF after a module reload before submitting a mutation', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'test-challenge' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await api('/auth/logout', { method: 'POST' });
    expect(fetch.mock.calls[0][0]).toBe('/api/auth/config');
    expect(fetch.mock.calls[1][1].headers.get('X-CSRF-Token')).toBe('test-challenge');
    expect(fetch.mock.calls[1][1].credentials).toBe('same-origin');
  });

  it('leaves multipart content type to the browser boundary encoder', async () => {
    setCsrf('test-challenge');
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const data = new FormData(); data.append('file', new Blob(['test']), 'sample.txt');
    await api('/receipts', { method: 'POST', body: data });
    expect(fetch.mock.calls[0][1].headers.has('Content-Type')).toBe(false);
    expect(fetch.mock.calls[0][1].body).toBe(data);
  });
});
