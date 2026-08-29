import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErrorBoundary } from '@/components/ErrorBoundary';

const CHUNK_ERROR = 'Dynamically imported module is invalid (chunk load)';

function BrokenComponent({ message }) {
  throw new Error(message);
}

describe('ErrorBoundary stale chunk recovery', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    window.__syroceIsChunkError = (message) => message?.includes('Dynamically imported module is invalid');
    window.__syroceChunkReloadOnce = vi.fn(() => false);
    window.__syroceForceFreshReload = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    delete window.__syroceIsChunkError;
    delete window.__syroceChunkReloadOnce;
    delete window.__syroceForceFreshReload;
  });

  it('loads the current application version instead of retrying an invalid lazy module', () => {
    render(
      <ErrorBoundary>
        <BrokenComponent message={CHUNK_ERROR} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Uygulamanın yeni sürümü yüklenemedi')).toBeInTheDocument();
    expect(window.__syroceChunkReloadOnce).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: 'Güncel sürümü yükle' }));

    expect(window.__syroceForceFreshReload).toHaveBeenCalledOnce();
  });

  it('loads the current version for Chromium React.lazy default-export errors', () => {
    window.__syroceIsChunkError = (message) =>
      message?.includes("Cannot read properties of undefined (reading 'default')");

    render(
      <ErrorBoundary>
        <BrokenComponent message="Cannot read properties of undefined (reading 'default')" />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Uygulamanın yeni sürümü yüklenemedi')).toBeInTheDocument();
    expect(window.__syroceChunkReloadOnce).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: 'Güncel sürümü yükle' }));
    expect(window.__syroceForceFreshReload).toHaveBeenCalledOnce();
  });

  it('keeps the ordinary retry path for non-chunk render failures', () => {
    render(
      <ErrorBoundary>
        <BrokenComponent message="ordinary render failure" />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Beklenmeyen bir hata oluştu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tekrar dene' })).toBeInTheDocument();
    expect(window.__syroceForceFreshReload).not.toHaveBeenCalled();
  });
});
