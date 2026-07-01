/**
 * Shared WebSocket Hook — Abstraction for all real-time data subscriptions.
 * Provides connection management, auto-reconnect, and event dispatching.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { io } from "socket.io-client";

const RAW_URL = import.meta.env.VITE_BACKEND_URL || "";
const WS_URL = RAW_URL.replace(/\/api$/, "");

export function useOperationalSocket(namespace = "/", events = {}) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const [staleMs, setStaleMs] = useState(0);
  const socketRef = useRef(null);
  const lastEventTimeRef = useRef(Date.now());

  useEffect(() => {
    const socket = io(`${WS_URL}${namespace}`, {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
      timeout: 10000,
    });

    socketRef.current = socket;

    socket.on("connect", () => {
      setConnected(true);
      lastEventTimeRef.current = Date.now();
    });

    socket.on("disconnect", () => setConnected(false));

    // Register custom event handlers
    Object.entries(events).forEach(([event, handler]) => {
      socket.on(event, (data) => {
        lastEventTimeRef.current = Date.now();
        setLastEvent({ event, data, time: Date.now() });
        handler(data);
      });
    });

    // Stale timer
    const staleInterval = setInterval(() => {
      setStaleMs(Date.now() - lastEventTimeRef.current);
    }, 2000);

    return () => {
      clearInterval(staleInterval);
      socket.removeAllListeners();
      socket.disconnect();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [namespace]);

  const emit = useCallback((event, data) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit(event, data);
    }
  }, []);

  return {
    connected,
    lastEvent,
    staleMs,
    isStale: staleMs > 15000,
    emit,
    socket: socketRef.current,
  };
}

export default useOperationalSocket;
