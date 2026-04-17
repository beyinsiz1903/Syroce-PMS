import { lazy } from "react";

const _cache = new WeakMap();

export function lazyWithPreload(factory) {
  const Component = lazy(factory);
  Component.preload = () => {
    if (_cache.has(factory)) return _cache.get(factory);
    const promise = factory().catch((err) => {
      _cache.delete(factory);
      throw err;
    });
    _cache.set(factory, promise);
    return promise;
  };
  return Component;
}
