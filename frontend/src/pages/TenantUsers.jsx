import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import UserProvisionDialog from '@/components/UserProvisionDialog';

function TenantUserList() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision(value => value + 1);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError('');
    // Never request the platform-wide /admin/users list or a caller-chosen tenant.
    axios.get('/admin/tenant-users', { signal: controller.signal }).then(({ data }) => {
      if (active) setUsers(data.users || []);
    }).catch(err => {
      if (!active) return;
      setUsers([]);
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Otel kullanıcıları yüklenemedi.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [revision]);
  const filtered = useMemo(() => users.filter(user =>
    [user.name, user.email, user.role].some(value => String(value || '').toLocaleLowerCase('tr-TR').includes(filter.toLocaleLowerCase('tr-TR')))
  ), [users, filter]);
  return <section className="p-6 space-y-4">
    <div className="flex flex-wrap gap-3 items-center justify-between">
      <div><h1 className="text-2xl font-semibold">Otel Kullanıcıları</h1>
        <p className="text-sm text-muted-foreground">Yalnızca oturum açtığınız otelin giriş hesapları. İK modülü gerektirmez.</p></div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={refresh} disabled={loading}>Yenile</Button>
        <UserProvisionDialog onCreated={refresh} disabled={loading || !!error} />
      </div>
    </div>
    <p className="text-sm text-muted-foreground">Yeni hesabın rolü otel paketine göre belirlenir. Süperadmin oluşturma ve platform geneli rol değişiklikleri bu ekranda yapılamaz.</p>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <Input aria-label="Kullanıcı ara" placeholder="Ad, e-posta veya rol ara" value={filter} onChange={e => setFilter(e.target.value)} />
    {loading ? <p role="status">Kullanıcılar yükleniyor…</p> : !error && <div className="overflow-x-auto rounded border">
      <table className="w-full text-sm">
        <thead><tr className="border-b bg-muted text-left">
          <th className="p-3">Ad Soyad</th><th className="p-3">E-posta</th><th className="p-3">Rol</th>
        </tr></thead>
        <tbody>{filtered.map(user => <tr key={user.id} className="border-b">
          <td className="p-3">{user.name || '—'}</td><td className="p-3">{user.email || '—'}</td><td className="p-3">{user.role}</td>
        </tr>)}</tbody>
      </table>
      {!filtered.length && <p className="p-3">Kullanıcı bulunamadı.</p>}
    </div>}
  </section>;
}

export default function TenantUsers({ user }) {
  // The standard protected route enforces authentication, not admin status.
  // Reject here before mounting any list/provisioning effects; API gates remain authoritative.
  if (!['admin', 'super_admin'].includes(user?.role) && !user?.roles?.includes('super_admin')) {
    return <p role="alert" className="p-6">Bu ekran yalnızca otel yöneticilerine açıktır.</p>;
  }
  return <TenantUserList key={`${user.tenant_id}:${user.id}`} />;
}
