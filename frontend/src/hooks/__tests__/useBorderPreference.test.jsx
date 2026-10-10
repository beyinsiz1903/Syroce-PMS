import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BORDER_PREFERENCE_KEY, setBorderPreference, useBorderPreference } from '../useBorderPreference';

beforeEach(() => {
  localStorage.removeItem(BORDER_PREFERENCE_KEY);
  setBorderPreference(false);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('defaults to soft borders and synchronizes mounted theme menus', () => {
  const first = renderHook(useBorderPreference);
  const second = renderHook(useBorderPreference);
  expect(first.result.current[0]).toBe(false);
  act(() => first.result.current[1](true));
  expect(second.result.current[0]).toBe(true);
  expect(document.documentElement).toHaveAttribute('data-prominent-borders');
  expect(localStorage.getItem(BORDER_PREFERENCE_KEY)).toBe('true');
  act(() => second.result.current[1](false));
  expect(first.result.current[0]).toBe(false);
  expect(document.documentElement).not.toHaveAttribute('data-prominent-borders');
});

it('restores saved preference on remount', () => {
  setBorderPreference(true);
  const first = renderHook(useBorderPreference);
  first.unmount();
  const next = renderHook(useBorderPreference);
  expect(next.result.current[0]).toBe(true);
});

it('follows storage changes from another tab and storage clearing', () => {
  const hook = renderHook(useBorderPreference);
  act(() => {
    localStorage.setItem(BORDER_PREFERENCE_KEY, 'true');
    window.dispatchEvent(new window.StorageEvent('storage', { key: BORDER_PREFERENCE_KEY }));
  });
  expect(hook.result.current[0]).toBe(true);
  act(() => {
    localStorage.removeItem(BORDER_PREFERENCE_KEY);
    window.dispatchEvent(new window.StorageEvent('storage', { key: null }));
  });
  expect(hook.result.current[0]).toBe(false);
});

it('works for the session if storage writes are blocked', () => {
  const hook = renderHook(useBorderPreference);
  vi.spyOn(window.Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  act(() => setBorderPreference(true));
  expect(hook.result.current[0]).toBe(true);
  act(() => setBorderPreference(false));
  expect(hook.result.current[0]).toBe(false);
});
