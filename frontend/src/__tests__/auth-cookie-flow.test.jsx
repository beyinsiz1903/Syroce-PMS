import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { render, waitFor, screen } from '@testing-library/react';
import App from '../App';

// Mock the axios module
vi.mock('axios', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
      defaults: {
        headers: { common: {} },
        baseURL: '',
        withCredentials: true
      },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }
  };
});

// Mock hooks that would crash the test
vi.mock('@/hooks/usePushNotifications', () => ({ default: vi.fn() }));

describe('Auth Cookie Flow in App.jsx', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(), // Deprecated
        removeListener: vi.fn(), // Deprecated
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('should wait for /auth/me to verify session if token_ts is present', async () => {
    // Set the cookie session flag
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ name: 'Test User' }));
    
    // Mock a successful backend verification
    axios.get.mockResolvedValueOnce({ data: { id: 'u1', name: 'Fresh User' } });
    
    expect(localStorage.getItem('token')).toBeNull(); // No token in localStorage
    
    // Call the effect logic directly via a wrapper or assume render works if we mock enough.
    // For this security test, we want to ensure axios.get is called
    try {
      render(<App />);
    } catch(e) {
      // ignore render crashes due to missing providers, we only care about the useEffect side effect
    }
    
    // App should call /auth/me because token_ts exists
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
    });
  });

  it('should clear token_ts if /auth/me fails', async () => {
    localStorage.setItem('token_ts', Date.now().toString());
    localStorage.setItem('user', JSON.stringify({ name: 'Test User' }));
    
    // Mock a failed backend verification (e.g. cookie expired)
    axios.get.mockRejectedValueOnce(new Error('401 Unauthorized'));
    
    try {
      render(<App />);
    } catch(e) {
      // ignore
    }
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/auth/me');
      // Auth storage should be cleared
      expect(localStorage.getItem('token_ts')).toBeNull();
      expect(localStorage.getItem('user')).toBeNull();
    });
  });
});
