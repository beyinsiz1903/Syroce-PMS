import React, { useState, useEffect } from 'react';
import axios from 'axios';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { confirmDialog } from '@/lib/dialogs';

const DEFAULT_ROLE_OPTIONS = [
  { value: 'super_admin', label: 'Super Admin' },
  { value: 'admin', label: 'Yönetici' },
  { value: 'supervisor', label: 'Supervisor' },
  { value: 'front_desk', label: 'Resepsiyon' },
  { value: 'housekeeping', label: 'Housekeeping' },
];
const UserRoleManager = ({ user, tenant, onLogout, roleOptions }) => {
  const { t } = useTranslation();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [emailFilter, setEmailFilter] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (emailFilter) params.email_filter = emailFilter;
      
      const res = await axios.get('/admin/users', { params });
      setUsers(res.data?.users || []);
    } catch (err) {
      console.error('Failed to load users', err);
      setError('Kullanıcılar yüklenirken hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const handleUpdateRole = async (userId, newRole) => {
    if (!await confirmDialog({ message: `Bu kullanıcının role'ünü ${newRole} yapmak istediğinizden emin misiniz?` })) {
      return;
    }

    setUpdating(true);
    setError(null);
    setSuccess(null);
    
    try {
      const res = await axios.patch(`/admin/users/${userId}/role`, {
        role: newRole
      });
      
      setSuccess(res.data.message);
      await loadUsers(); // Reload list
    } catch (err) {
      console.error('Failed to update role', err);
      setError(err.response?.data?.detail || 'Role güncellenirken hata oluştu');
    } finally {
      setUpdating(false);
    }
  };

  const getRoleBadgeColor = (role) => {
    switch(role) {
      case 'super_admin': return 'bg-indigo-600 text-white';
      case 'admin': return 'bg-blue-600 text-white';
      case 'supervisor': return 'bg-green-600 text-white';
      case 'front_desk': return 'bg-yellow-600 text-white';
      default: return 'bg-gray-600 text-white';
    }
  };

  return (
    <>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-bold">👥 Kullanıcı Role Yönetimi</h1>
          <p className="text-gray-600">Tüm kullanıcıların role'lerini görüntüleyin ve güncelleyin (Super Admin)</p>
        </div>

        {error && (
          <div className="p-4 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
        )}

        {success && (
          <div className="p-4 rounded-md bg-green-50 text-green-700 text-sm">{success}</div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Filtreler</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4">
              <div className="flex-1">
                <Label>Email Ara</Label>
                <Input
                  placeholder="email@example.com"
                  value={emailFilter}
                  onChange={(e) => setEmailFilter(e.target.value)}
                />
              </div>
              <div className="flex items-end">
                <Button onClick={loadUsers} disabled={loading}>
                  🔍 Ara
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Kullanıcılar ({users.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8">{t("common.loading")}</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left">Email</th>
                      <th className="px-4 py-3 text-left">İsim</th>
                      <th className="px-4 py-3 text-left">Mevcut Role</th>
                      <th className="px-4 py-3 text-left">Tenant ID</th>
                      <th className="px-4 py-3 text-left">İşlemler</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b hover:bg-gray-50">
                        <td className="px-4 py-3">{u.email}</td>
                        <td className="px-4 py-3">{u.name}</td>
                        <td className="px-4 py-3">
                          <Badge className={getRoleBadgeColor(u.role)}>
                            {u.role}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-500">
                          {u.tenant_id?.substring(0, 8)}...
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-2">
                            {u.role !== 'super_admin' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleUpdateRole(u.id, 'super_admin')}
                                disabled={updating}
                                className="text-xs"
                              >
                                ⬆️ Super Admin Yap
                              </Button>
                            )}
                            {u.role === 'super_admin' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleUpdateRole(u.id, 'admin')}
                                disabled={updating}
                                className="text-xs"
                              >
                                ⬇️ Admin Yap
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-blue-50">
          <CardContent className="p-4">
            <h3 className="font-semibold text-sm mb-2">💡 Hızlı İpucu</h3>
            <p className="text-xs text-gray-700">
              Production'da demo@hotel.com kullanıcısını super_admin yapmak için:
              <br />
              1. Email filtresi: "demo@hotel.com"
              <br />
              2. Ara butonuna tıklayın
              <br />
              3. "⬆️ Super Admin Yap" butonuna tıklayın
              <br />
              4. Logout yapın ve tekrar login yapın
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
};

export default UserRoleManager;
