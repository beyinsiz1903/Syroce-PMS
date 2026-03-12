import { useState, useEffect, useRef, useCallback } from 'react';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * Custom hook for WebSocket real-time admin updates.
 * Automatically reconnects on disconnect.
 */
export function useAdminWebSocket(tenantId) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const pingTimerRef = useRef(null);

  const connect = useCallback(() => {
    if (!tenantId) return;

    // Build ws URL from API
    const wsUrl = API.replace(/^http/, 'ws') + `/api/channel-manager/v2/ws/admin-updates?tenant_id=${tenantId}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        // Ping every 30s
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'pong') return;
          setLastEvent(data);
          setEvents(prev => [data, ...prev].slice(0, 100));
        } catch {}
      };

      ws.onclose = () => {
        setConnected(false);
        clearInterval(pingTimerRef.current);
        // Reconnect after 3s
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimerRef.current = setTimeout(connect, 5000);
    }
  }, [tenantId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimerRef.current);
      clearInterval(pingTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { connected, events, lastEvent, clearEvents };
}
