import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// A response belongs to both a session and a request. Neither a signed-out
// account's late response nor an older refresh may replace the current list.
export default function usePendingActions({ api, path, enabled = true, sessionKey = '' }) {
  const context = useMemo(() => ({ api, path, enabled, sessionKey }), [api, path, enabled, sessionKey]);
  const current = useRef(context);
  current.current = context;
  const request = useRef(0);
  const [state, setState] = useState({ context, data: null, error: null, loading: enabled });

  const reload = useCallback(async () => {
    if (current.current !== context || !context.enabled) return;
    const id = ++request.current;
    setState(previous => ({ context, data: previous.context === context ? previous.data : null, error: null, loading: true }));
    try {
      const { data } = await context.api.get(context.path);
      if (current.current === context && request.current === id) setState({ context, data, error: null, loading: false });
    } catch (error) {
      if (current.current === context && request.current === id) setState(previous => ({ ...previous, error, loading: false }));
    }
  }, [context]);

  useEffect(() => {
    reload();
    return () => { request.current += 1; };
  }, [reload]);

  const visible = state.context === context && enabled ? state : { data: null, error: null, loading: enabled };
  return { data: visible.data, error: visible.error, loading: visible.loading, reload };
}
