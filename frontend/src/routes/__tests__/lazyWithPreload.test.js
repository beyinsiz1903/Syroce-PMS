import { describe, expect, it } from 'vitest';

import {
  INVALID_CHUNK_MODULE_MSG,
  lazyWithPreload,
} from '../lazyWithPreload';

describe('lazyWithPreload', () => {
  it('rejects resolved modules without a default export as a chunk error', async () => {
    const Component = lazyWithPreload(() => Promise.resolve({ named: () => null }));

    await expect(Component.preload()).rejects.toThrow(INVALID_CHUNK_MODULE_MSG);
  });

  it('accepts a valid default component export', async () => {
    const DefaultComponent = () => null;
    const Component = lazyWithPreload(() => Promise.resolve({ default: DefaultComponent }));

    await expect(Component.preload()).resolves.toEqual({ default: DefaultComponent });
  });
});
