/**
 * WebSocket Client for Real-time Updates
 * Gracefully handles connection failures without blocking the app
 */
import React from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
const WEBSOCKET_URL = BACKEND_URL ? BACKEND_URL.replace('/api', '').replace(/\/+$/, '') : '';
// Backend mounts socket.io at app.mount("/ws", socket_app) with socketio_path="socket.io"
// → full URL is `${origin}/ws/socket.io/`. We must tell the client to use that path,
// otherwise it would default to `/socket.io/` and 404 against our reverse proxy.
const WEBSOCKET_PATH = '/ws/socket.io';

let ioModule = null;

class WebSocketManager {
  constructor() {
    this.socket = null;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 2; // Reduced from 5 to avoid console spam
    this.disabled = false;
    this._lastAuth = null;
  }

  _readAuthFromStorage() {
    try {
      const token = typeof localStorage !== 'undefined'
        ? localStorage.getItem('token')
        : null;
      if (!token) return {};
      return { token };
    } catch {
      return {};
    }
  }

  async connect() {
    // If disabled after max attempts, return a no-op socket (real-time updates unavailable)
    if (this.disabled) {
      return this._getNoopSocket();
    }

    if (this.socket?.connected) {
      return this.socket;
    }

    try {
      // Lazy import socket.io-client to avoid blocking initial load
      const { io } = await import('socket.io-client');

      const auth = this._readAuthFromStorage();
      this._lastAuth = auth;

      this.socket = io(WEBSOCKET_URL, {
        path: WEBSOCKET_PATH,
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 3000,
        reconnectionDelayMax: 10000,
        reconnectionAttempts: this.maxReconnectAttempts,
        timeout: 5000,
        autoConnect: true,
        auth,
      });

      this.setupEventHandlers();
      return this.socket;
    } catch (err) {
      // If socket.io fails to load, disable gracefully but warn loudly
      console.warn('[WebSocket] socket.io unavailable; real-time updates disabled.', err);
      this.disabled = true;
      return this._getNoopSocket();
    }
  }

  _getNoopSocket() {
    // No-op socket so callers don't crash; real-time features are simply inactive.
    return {
      connected: false,
      on: () => {},
      off: () => {},
      emit: () => {},
      disconnect: () => {},
    };
  }

  setupEventHandlers() {
    if (!this.socket) return;

    this.socket.on('connect', () => {
      this.reconnectAttempts = 0;
    });

    this.socket.on('disconnect', () => {});

    this.socket.on('connect_error', (err) => {
      this.reconnectAttempts++;
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        console.warn('[WebSocket] connection failed after retries; real-time updates disabled.', err?.message || err);
        this.disabled = true;
        if (this.socket) {
          this.socket.disconnect();
          this.socket = null;
        }
      }
    });

    this.socket.on('connection_established', (data) => {
      this.emit('connection_established', data);
    });

    // Dashboard updates
    this.socket.on('dashboard_update', (data) => {
      this.emit('dashboard_update', data);
    });

    // Booking updates
    this.socket.on('booking_update', (data) => {
      this.emit('booking_update', data);
    });

    // Room status updates
    this.socket.on('room_status_update', (data) => {
      this.emit('room_status_update', data);
    });

    // Notifications
    this.socket.on('notification', (data) => {
      this.emit('notification', data);
    });

    // Internal chat — new staff message arrived for me / my dept / broadcast
    this.socket.on('internal_message', (data) => {
      this.emit('internal_message', data);
    });

    // Internal chat live events (read receipts + typing)
    this.socket.on('internal_message_read', (data) => {
      this.emit('internal_message_read', data);
    });

    this.socket.on('internal_user_typing', (data) => {
      this.emit('internal_user_typing', data);
    });

    // Guest room requests — contentless ping; authorized clients re-fetch via
    // REST (no PII on the wire). Forwarded into the internal pub/sub so the
    // "Misafir Talepleri" panel can refresh instantly.
    this.socket.on('guest_requests:updated', (data) => {
      this.emit('guest_requests:updated', data);
    });

    this.socket.on('pong', () => {});
  }

  /** Force-reconnect with the freshest token from localStorage. Call this
   * after login so the server can authenticate the socket and enrol it in
   * tenant-scoped rooms. */
  reconnectWithFreshAuth() {
    if (this.disabled) return;
    if (this.socket) {
      try { this.socket.disconnect(); } catch { /* noop */ }
      this.socket = null;
    }
    this.reconnectAttempts = 0;
    return this.connect();
  }

  /**
   * Send a raw socket.io event to the server. Use for client→server
   * signals (e.g. typing indicators) where the WebSocketManager's
   * internal pub/sub is not appropriate.
   */
  socketEmit(event, data) {
    if (!this.socket?.connected) return false;
    try {
      this.socket.emit(event, data);
      return true;
    } catch {
      return false;
    }
  }

  joinRoom(room) {
    if (!this.socket?.connected) return;
    this.socket.emit('join_room', { room });
  }

  leaveRoom(room) {
    if (!this.socket?.connected) return;
    this.socket.emit('leave_room', { room });
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);

    return () => {
      const callbacks = this.listeners.get(event);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }
      }
    };
  }

  emit(event, data) {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.forEach(callback => callback(data));
    }
  }

  ping() {
    if (this.socket?.connected) {
      this.socket.emit('ping');
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.listeners.clear();
    }
  }

  isConnected() {
    return this.socket?.connected || false;
  }
}

// Export singleton instance
export const websocket = new WebSocketManager();

// React hook for WebSocket
export function useWebSocket(room = null) {
  const [isConnected, setIsConnected] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;

    const init = async () => {
      const socket = await websocket.connect();
      if (cancelled) return;

      const checkConnection = () => {
        setIsConnected(websocket.isConnected());
      };

      socket.on('connect', checkConnection);
      socket.on('disconnect', checkConnection);
      checkConnection();

      if (room) {
        websocket.joinRoom(room);
      }
    };

    init();

    return () => {
      cancelled = true;
      if (room) {
        websocket.leaveRoom(room);
      }
    };
  }, [room]);

  return {
    isConnected,
    socket: websocket,
    joinRoom: websocket.joinRoom.bind(websocket),
    leaveRoom: websocket.leaveRoom.bind(websocket),
    on: websocket.on.bind(websocket),
    emit: websocket.emit.bind(websocket),
    socketEmit: websocket.socketEmit.bind(websocket),
  };
}

export default websocket;
