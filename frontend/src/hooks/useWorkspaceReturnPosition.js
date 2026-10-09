import { useEffect } from 'react';
import { readExperiencePreference, writeExperiencePreference } from '@/lib/productExperience';

// Store only scroll offsets, scoped to the signed-in user and hotel. No guest
// search terms, profiles or query-string identifiers are persisted.
export function useWorkspaceReturnPosition(ref, pathname, scope, hash) {
  useEffect(() => {
    if (hash) return;
    const node = ref.current;
    if (!node) return;
    const positions = readExperiencePreference(scope, 'positions', {});
    const saved = positions[pathname] || { page: 0, panel: 0 };
    let restoring = true;
    const restore = () => {
      if (!restoring) return;
      node.scrollTop = saved.panel || 0;
      window.scrollTo(0, saved.page || 0);
    };
    const stop = () => { restoring = false; };
    const frame = requestAnimationFrame(restore);
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(restore) : null;
    observer?.observe(node);
    node.addEventListener('wheel', stop, { passive: true });
    node.addEventListener('touchstart', stop, { passive: true });
    window.addEventListener('keydown', stop);
    return () => {
      cancelAnimationFrame(frame); observer?.disconnect();
      node.removeEventListener('wheel', stop); node.removeEventListener('touchstart', stop); window.removeEventListener('keydown', stop);
      const recent = Object.entries(readExperiencePreference(scope, 'positions', {})).filter(([path]) => path !== pathname).slice(-29);
      writeExperiencePreference(scope, 'positions', { ...Object.fromEntries(recent), [pathname]: { page: window.scrollY, panel: node.scrollTop } });
    };
  }, [pathname, scope, hash, ref]);
}
