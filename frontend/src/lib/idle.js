export const runIdle = (fn, { timeout = 4000 } = {}) => {
  if (typeof window === 'undefined') {
    fn();
    return () => {};
  }
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(fn, { timeout });
    return () => window.cancelIdleCallback?.(id);
  }
  const t = setTimeout(fn, Math.min(timeout, 1500));
  return () => clearTimeout(t);
};
