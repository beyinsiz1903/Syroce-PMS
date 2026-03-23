import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Users, Trash2, UserPlus, ShieldCheck } from 'lucide-react';
import { ROLE_LABELS } from './tenantConstants';

const TeamManagementModal = ({ open, onOpenChange, tenant }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', email: '', phone: '', password: '', role: 'front_desk' });
  const [saving, setSaving] = useState(false);
  const [editingRole, setEditingRole] = useState(null);

  const tenantId = tenant?.id;

  const loadTeam = async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/team`);
      setUsers(res.data?.users || []);
    } catch {
      setError('Ekip yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && tenantId) {
      loadTeam();
      setShowAdd(false);
      setError(null);
    }
  }, [open, tenantId]);

  const handleAddMember = async () => {
    if (!addForm.name || !addForm.email || !addForm.password) {
      setError('Ad, e-posta ve şifre zorunlu');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await axios.post(`/admin/tenants/${tenantId}/team`, addForm);
      setShowAdd(false);
      setAddForm({ name: '', email: '', phone: '', password: '', role: 'front_desk' });
      await loadTeam();
    } catch (err) {
      setError(err.response?.data?.detail || 'Üye eklenemedi');
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (userId, userName) => {
    if (!window.confirm(`${userName} silinecek. Emin misiniz?`)) return;
    try {
      await axios.delete(`/admin/tenants/${tenantId}/team/${userId}`);
      await loadTeam();
    } catch (err) {
      setError(err.response?.data?.detail || 'Silinemedi');
    }
  };

  const handleRoleChange = async (userId, newRole) => {
    try {
      await axios.patch(`/admin/tenants/${tenantId}/team/${userId}/role`, { role: newRole });
      setEditingRole(null);
      await loadTeam();
    } catch (err) {
      setError(err.response?.data?.detail || 'Rol güncellenemedi');
    }
  };

  const allRoles = Object.keys(ROLE_LABELS);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-600" />
            Ekip Yönetimi — {tenant?.property_name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">{users.length} kullanıcı</span>
            <Button data-testid="team-add-btn" size="sm" variant="outline" onClick={() => setShowAdd(!showAdd)}>
              <UserPlus className="w-4 h-4 mr-1" /> Üye Ekle
            </Button>
          </div>

          {showAdd && (
            <div className="border rounded-lg p-3 bg-blue-50/50 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Ad *</Label>
                  <input data-testid="team-add-name" className="w-full border rounded px-2 py-1.5 text-sm" value={addForm.name} onChange={(e) => setAddForm((p) => ({ ...p, name: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">E-posta *</Label>
                  <input data-testid="team-add-email" type="email" className="w-full border rounded px-2 py-1.5 text-sm" value={addForm.email} onChange={(e) => setAddForm((p) => ({ ...p, email: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Şifre *</Label>
                  <input data-testid="team-add-password" type="password" className="w-full border rounded px-2 py-1.5 text-sm" value={addForm.password} onChange={(e) => setAddForm((p) => ({ ...p, password: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Telefon</Label>
                  <input data-testid="team-add-phone" className="w-full border rounded px-2 py-1.5 text-sm" value={addForm.phone} onChange={(e) => setAddForm((p) => ({ ...p, phone: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Rol</Label>
                  <select data-testid="team-add-role" className="w-full border rounded px-2 py-1.5 text-sm" value={addForm.role} onChange={(e) => setAddForm((p) => ({ ...p, role: e.target.value }))}>
                    {allRoles.filter(r => r !== 'super_admin').map((r) => (
                      <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => setShowAdd(false)}>İptal</Button>
                <Button data-testid="team-add-submit" size="sm" onClick={handleAddMember} disabled={saving}>{saving ? 'Ekleniyor...' : 'Ekle'}</Button>
              </div>
            </div>
          )}

          {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

          {loading ? (
            <div className="text-center py-6 text-gray-400 text-sm">Yükleniyor...</div>
          ) : (
            <div className="divide-y">
              {users.map((u) => (
                <div key={u.id} className="flex items-center justify-between py-2.5 px-1">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-600">
                      {(u.name || '?')[0].toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">{u.name}</p>
                      <p className="text-xs text-gray-400">{u.email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {editingRole === u.id ? (
                      <select
                        className="border rounded px-2 py-1 text-xs"
                        value={u.role}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        onBlur={() => setEditingRole(null)}
                        autoFocus
                      >
                        {allRoles.map((r) => (
                          <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                        ))}
                      </select>
                    ) : (
                      <button
                        data-testid={`team-role-${u.id}`}
                        className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 flex items-center gap-1"
                        onClick={() => u.role !== 'super_admin' && setEditingRole(u.id)}
                        disabled={u.role === 'super_admin'}
                      >
                        <ShieldCheck className="w-3 h-3" />
                        {ROLE_LABELS[u.role] || u.role}
                      </button>
                    )}
                    {u.role !== 'super_admin' && (
                      <button
                        data-testid={`team-remove-${u.id}`}
                        className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition"
                        onClick={() => handleRemove(u.id, u.name)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default TeamManagementModal;
