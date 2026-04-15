import { useState, useEffect, useRef, useCallback } from 'react';

const API = import.meta.env.VITE_BACKEND_URL || '';

export function useNativeWebSocket(path, { enabled = true, maxEvents = 100, reconnectDelay = 3000, pingInterval = 30000 } = {}) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const pingTimerRef = useRef(null);
  const activeRef = useRef(false);

  const connect = useCallback(() => {
    if (!path || !enabled || !activeRef.current) return;

    const wsUrl = API.replace(/^http/, 'ws') + path;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, pingInterval);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'pong') return;
          setLastEvent(data);
          setEvents(prev => [data, ...prev].slice(0, maxEvents));
        } catch {
          /* ignore non-JSON messages */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        clearInterval(pingTimerRef.current);
        if (activeRef.current) {
          reconnectTimerRef.current = setTimeout(connect, reconnectDelay);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      if (activeRef.current) {
        reconnectTimerRef.current = setTimeout(connect, reconnectDelay + 2000);
      }
    }
  }, [path, enabled, maxEvents, reconnectDelay, pingInterval]);

  useEffect(() => {
    activeRef.current = true;
    connect();
    return () => {
      activeRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      clearInterval(pingTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { connected, events, lastEvent, clearEvents };
}
