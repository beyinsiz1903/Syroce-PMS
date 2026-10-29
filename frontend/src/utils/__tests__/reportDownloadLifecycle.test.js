// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { saveReportFile } from '../reportExports';

function browserFixture() {
  const timers = new Map();
  const callbacks = [];
  const links = [];
  const owner = {};
  const urlApi = {
    createObjectURL: vi.fn(() => `blob:report-${urlApi.createObjectURL.mock.calls.length}`),
    revokeObjectURL: vi.fn(function () { expect(this).toBe(urlApi); }),
  };
  const browser = {
    URL: urlApi,
    setTimeout: vi.fn(function (callback, delay) {
      expect(this).toBe(browser);
      expect(delay).toBe(1000);
      const id = callbacks.push(callback);
      timers.set(id, callback);
      return id;
    }),
    clearTimeout: vi.fn(function (id) { expect(this).toBe(browser); timers.delete(id); }),
    document: {
      body: { appendChild: vi.fn() },
      createElement: vi.fn(tag => {
        expect(tag).toBe('a');
        const link = { click: vi.fn(), remove: vi.fn() };
        links.push(link);
        return link;
      }),
    },
    owner,
  };
  return { browser, timers, callbacks, links, urlApi };
}

describe('Report download resource ownership without any global window', () => {
  it('saves the correct filename, removes the anchor and revokes after the grace period', () => {
    expect(typeof window).toBe('undefined');
    const { browser, callbacks, links, timers, urlApi } = browserFixture();
    const onRelease = vi.fn();
    const blob = new Blob(['isolated report']);
    const release = saveReportFile(blob, 'misafir-raporu.xlsx', browser, onRelease);
    expect(urlApi.createObjectURL).toHaveBeenCalledExactlyOnceWith(blob);
    expect(links[0]).toMatchObject({ href: 'blob:report-1', download: 'misafir-raporu.xlsx' });
    expect(links[0].click).toHaveBeenCalledOnce();
    expect(links[0].remove).toHaveBeenCalledOnce();
    expect(urlApi.revokeObjectURL).not.toHaveBeenCalled();
    callbacks[0]();
    expect(timers.size).toBe(0);
    expect(urlApi.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:report-1');
    expect(onRelease).toHaveBeenCalledExactlyOnceWith(release);
  });

  it('captures the original revoke function rather than a later replaced browser API', () => {
    const { browser, callbacks, urlApi } = browserFixture();
    saveReportFile(new Blob(['a']), 'a.xlsx', browser);
    const revoke = urlApi.revokeObjectURL;
    browser.URL = null;
    urlApi.revokeObjectURL = () => { throw new Error('later API must not own this URL'); };
    callbacks[0]();
    expect(revoke).toHaveBeenCalledExactlyOnceWith('blob:report-1');
  });

  it('early release cancels its timer and ignores an already queued duplicate callback', () => {
    const { browser, callbacks, timers, urlApi } = browserFixture();
    const release = saveReportFile(new Blob(['a']), 'a.xlsx', browser);
    release();
    release();
    callbacks[0]();
    expect(timers.size).toBe(0);
    expect(browser.clearTimeout).toHaveBeenCalledExactlyOnceWith(1);
    expect(urlApi.revokeObjectURL).toHaveBeenCalledOnce();
  });

  it('keeps concurrent downloads separate', () => {
    const { browser, callbacks, timers, urlApi } = browserFixture();
    const first = saveReportFile(new Blob(['a']), 'a.xlsx', browser);
    saveReportFile(new Blob(['b']), 'b.xlsx', browser);
    first();
    expect(timers.size).toBe(1);
    callbacks[1]();
    expect(urlApi.revokeObjectURL.mock.calls).toEqual([['blob:report-1'], ['blob:report-2']]);
  });

  it.each(['click', 'schedule'])('releases the URL and anchor immediately when %s fails', stage => {
    const { browser, links, timers, urlApi } = browserFixture();
    if (stage === 'click') {
      browser.document.createElement.mockImplementation(() => {
        const link = { click: vi.fn(() => { throw new Error('blocked click'); }), remove: vi.fn() };
        links.push(link);
        return link;
      });
    } else {
      browser.setTimeout.mockImplementation(() => { throw new Error('closed timer owner'); });
    }
    expect(() => saveReportFile(new Blob(['a']), 'a.xlsx', browser)).toThrow();
    expect(timers.size).toBe(0);
    expect(urlApi.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:report-1');
    expect(links[0].remove).toHaveBeenCalledOnce();
  });
});
