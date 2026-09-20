import { useEffect } from 'react';
import axios from 'axios';

// Session refresh is bounded and read-only; permission revocation is enforced
// independently by the API on every request.
export default function useUserAccessRefresh(user, setUser, onAccessChanged) {
  useEffect(() => {
    if (!user?.id) return;
    let stopped = false;
    let pending = false;
    const refresh = async () => {
      if (stopped || pending || document.visibilityState === 'hidden') return;
      pending = true;
      try {
        const { data } = await axios.get('/auth/me');
        if (stopped || data.id !== user.id || data.tenant_id !== user.tenant_id) return;
        const keys = ['role', 'roles', 'module_scopes', 'page_access', 'effective_permissions', 'granted_permissions'];
        if (keys.some(key => JSON.stringify(user[key]) !== JSON.stringify(data[key]))) {
          onAccessChanged();
          localStorage.setItem('user', JSON.stringify(data));
          setUser(data);
        }
      } catch { /* Request authorization remains fail-closed on the server. */ }
      finally { pending = false; }
    };
    refresh();
    const interval = setInterval(refresh, 60000);
    window.addEventListener('focus', refresh);
    return () => { stopped = true; clearInterval(interval); window.removeEventListener('focus', refresh); };
  }, [user, setUser, onAccessChanged]);
}
