import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Building2, Plus, Edit2, Trash2, Users, UserPlus, ChevronDown, ChevronRight,
  Phone, Mail, Percent, FileText, Loader2, Eye, EyeOff, ToggleLeft, ToggleRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import Layout from '@/components/Layout';

const AgencyManagement = ({ user, tenant, onLogout }) => {
  const [agencies, setAgencies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedAgency, setExpandedAgency] = useState(null);
  const [agencyUsers, setAgencyUsers] = useState({});

  // Agency form
  const [showAgencyForm, setShowAgencyForm] = useState(false);
  const [editingAgency, setEditingAgency] = useState(null);
  const [agencyForm, setAgencyForm] = useState({
    name: '', contact_name: '', contact_email: '', contact_phone: '', commission_rate: 10, notes: '',
  });

  // User form
  const [showUserForm, setShowUserForm] = useState(false);
  const [userFormAgencyId, setUserFormAgencyId] = useState(null);
  const [userForm, setUserForm] = useState({ name: '', email: '', password: '', role: 'agency_agent' });

  const [saving, setSaving] = useState(false);

  const fetchAgencies = async () => {
    try {
      const { data } = await axios.get('/agencies');
      setAgencies(data);
    } catch {
      toast.error('Acenteler yuklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const fetchAgencyUsers = async (agencyId) => {
    try {
      const { data } = await axios.get(`/agencies/${agencyId}/users`);
      setAgencyUsers(prev => ({ ...prev, [agencyId]: data }));
    } catch {
      toast.error('Kullanicilar yuklenemedi');
    }
  };

  useEffect(() => { fetchAgencies(); }, []);

  const handleToggleExpand = (agencyId) => {
    if (expandedAgency === agencyId) {
      setExpandedAgency(null);
    } else {
      setExpandedAgency(agencyId);
      if (!agencyUsers[agencyId]) fetchAgencyUsers(agencyId);
    }
  };

  const openAgencyForm = (agency = null) => {
    if (agency) {
      setEditingAgency(agency);
      setAgencyForm({
        name: agency.name, contact_name: agency.contact_name || '',
        contact_email: agency.contact_email || '', contact_phone: agency.contact_phone || '',
        commission_rate: agency.commission_rate || 10, notes: agency.notes || '',
      });
    } else {
      setEditingAgency(null);
      setAgencyForm({ name: '', contact_name: '', contact_email: '', contact_phone: '', commission_rate: 10, notes: '' });
    }
    setShowAgencyForm(true);
  };

  const handleSaveAgency = async () => {
    if (!agencyForm.name.trim()) return toast.error('Acente adi gerekli');
    setSaving(true);
    try {
      if (editingAgency) {
        await axios.put(`/agencies/${editingAgency.id}`, agencyForm);
        toast.success('Acente guncellendi');
      } else {
        await axios.post('/agencies', agencyForm);
        toast.success('Acente olusturuldu');
      }
      setShowAgencyForm(false);
      fetchAgencies();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Hata olustu');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async (agency) => {
    const newStatus = agency.status === 'active' ? 'inactive' : 'active';
    try {
      await axios.put(`/agencies/${agency.id}`, { status: newStatus });
      toast.success(newStatus === 'active' ? 'Acente aktif edildi' : 'Acente devre disi birakildi');
      fetchAgencies();
    } catch {
      toast.error('Durum degistirilemedi');
    }
  };

  const handleDeleteAgency = async (agency) => {
    if (!confirm(`"${agency.name}" acentesini silmek istediginize emin misiniz?`)) return;
    try {
      await axios.delete(`/agencies/${agency.id}`);
      toast.success('Acente silindi');
      fetchAgencies();
    } catch {
      toast.error('Acente silinemedi');
    }
  };

  const openUserForm = (agencyId) => {
    setUserFormAgencyId(agencyId);
    setUserForm({ name: '', email: '', password: '', role: 'agency_agent' });
    setShowUserForm(true);
  };

  const handleSaveUser = async () => {
    if (!userForm.name.trim() || !userForm.email.trim() || !userForm.password) {
      return toast.error('Ad, e-posta ve sifre gerekli');
    }
    setSaving(true);
    try {
      await axios.post(`/agencies/${userFormAgencyId}/users`, userForm);
      toast.success('Kullanici olusturuldu');
      setShowUserForm(false);
      fetchAgencyUsers(userFormAgencyId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Hata olustu');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteUser = async (userId, agencyId) => {
    if (!confirm('Bu kullaniciyi silmek istediginize emin misiniz?')) return;
    try {
      await axios.delete(`/agencies/users/${userId}`);
      toast.success('Kullanici silindi');
      fetchAgencyUsers(agencyId);
    } catch {
      toast.error('Kullanici silinemedi');
    }
  };

  const content = (
    <div className="p-6 space-y-6 max-w-5xl mx-auto" data-testid="agency-management">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900" data-testid="agency-management-title">Acente Yonetimi</h1>
          <p className="text-slate-500 text-sm mt-1">Bolgesel acentelerinizi yonetin, kullanici ekleyin</p>
        </div>
        <Button onClick={() => openAgencyForm()} data-testid="add-agency-btn" className="gap-2">
          <Plus size={16} /> Yeni Acente
        </Button>
      </div>

      {/* Agency List */}
      {loading ? (
        <div className="flex justify-center py-20"><Loader2 className="animate-spin text-slate-400" size={32} /></div>
      ) : agencies.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-slate-400">
            <Building2 size={48} className="mx-auto mb-4 opacity-40" />
            <p className="text-lg font-medium">Henuz acente eklenmemis</p>
            <p className="text-sm mt-1">Yeni bir bolgesel acente eklemek icin butona tiklayin</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {agencies.map(agency => (
            <Card key={agency.id} className="overflow-hidden" data-testid={`agency-card-${agency.id}`}>
              <div
                className="flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-slate-50 transition"
                onClick={() => handleToggleExpand(agency.id)}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm">
                    {agency.name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="font-semibold text-slate-800">{agency.name}</div>
                    <div className="text-xs text-slate-500 flex items-center gap-3 mt-0.5">
                      {agency.contact_name && <span>{agency.contact_name}</span>}
                      {agency.contact_phone && <span className="flex items-center gap-1"><Phone size={10} />{agency.contact_phone}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={agency.status === 'active' ? 'default' : 'secondary'} className="text-xs">
                    {agency.status === 'active' ? 'Aktif' : 'Pasif'}
                  </Badge>
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Percent size={12} />{agency.commission_rate}%
                  </span>
                  {agency.published_content && (
                    <Badge variant="outline" className="text-xs text-blue-600 border-blue-200">Icerik Yayinda</Badge>
                  )}
                  {expandedAgency === agency.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </div>
              </div>

              {expandedAgency === agency.id && (
                <div className="border-t bg-slate-50 px-5 py-4 space-y-4">
                  {/* Agency details */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div><span className="text-slate-400">E-posta:</span> <span className="text-slate-700">{agency.contact_email || '-'}</span></div>
                    <div><span className="text-slate-400">Telefon:</span> <span className="text-slate-700">{agency.contact_phone || '-'}</span></div>
                    <div><span className="text-slate-400">Komisyon:</span> <span className="text-slate-700">%{agency.commission_rate}</span></div>
                    <div><span className="text-slate-400">Notlar:</span> <span className="text-slate-700">{agency.notes || '-'}</span></div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 flex-wrap">
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); openAgencyForm(agency); }} data-testid={`edit-agency-${agency.id}`}>
                      <Edit2 size={14} className="mr-1" /> Duzenle
                    </Button>
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleToggleStatus(agency); }}>
                      {agency.status === 'active' ? <><ToggleRight size={14} className="mr-1" /> Devre Disi Birak</> : <><ToggleLeft size={14} className="mr-1" /> Aktif Et</>}
                    </Button>
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); openUserForm(agency.id); }} data-testid={`add-user-${agency.id}`}>
                      <UserPlus size={14} className="mr-1" /> Kullanici Ekle
                    </Button>
                    <Button size="sm" variant="destructive" onClick={(e) => { e.stopPropagation(); handleDeleteAgency(agency); }}>
                      <Trash2 size={14} className="mr-1" /> Sil
                    </Button>
                  </div>

                  {/* Users */}
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-2">
                      <Users size={14} /> Kullanicilar
                    </h4>
                    {(agencyUsers[agency.id] || []).length === 0 ? (
                      <p className="text-xs text-slate-400">Henuz kullanici eklenmemis</p>
                    ) : (
                      <div className="space-y-2">
                        {(agencyUsers[agency.id] || []).map(u => (
                          <div key={u.id} className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border text-sm">
                            <div className="flex items-center gap-3">
                              <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">
                                {u.name?.charAt(0)?.toUpperCase() || '?'}
                              </div>
                              <div>
                                <span className="font-medium text-slate-800">{u.name}</span>
                                <span className="text-slate-400 ml-2 text-xs">{u.email}</span>
                              </div>
                              <Badge variant="outline" className="text-xs">{u.role === 'agency_admin' ? 'Admin' : 'Ajan'}</Badge>
                            </div>
                            <Button size="sm" variant="ghost" className="text-red-500 h-7" onClick={() => handleDeleteUser(u.id, agency.id)}>
                              <Trash2 size={13} />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Agency Form Dialog */}
      <Dialog open={showAgencyForm} onOpenChange={setShowAgencyForm}>
        <DialogContent className="max-w-lg" data-testid="agency-form-dialog">
          <DialogHeader>
            <DialogTitle>{editingAgency ? 'Acente Duzenle' : 'Yeni Acente'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Acente Adi *</Label>
              <Input value={agencyForm.name} onChange={e => setAgencyForm(p => ({ ...p, name: e.target.value }))} data-testid="agency-name-input" placeholder="Orn: Antalya Turizm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Yetkili Kisi</Label>
                <Input value={agencyForm.contact_name} onChange={e => setAgencyForm(p => ({ ...p, contact_name: e.target.value }))} placeholder="Ad Soyad" />
              </div>
              <div>
                <Label>Komisyon (%)</Label>
                <Input type="number" value={agencyForm.commission_rate} onChange={e => setAgencyForm(p => ({ ...p, commission_rate: parseFloat(e.target.value) || 0 }))} data-testid="commission-rate-input" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>E-posta</Label>
                <Input value={agencyForm.contact_email} onChange={e => setAgencyForm(p => ({ ...p, contact_email: e.target.value }))} placeholder="info@acente.com" />
              </div>
              <div>
                <Label>Telefon</Label>
                <Input value={agencyForm.contact_phone} onChange={e => setAgencyForm(p => ({ ...p, contact_phone: e.target.value }))} placeholder="+90..." />
              </div>
            </div>
            <div>
              <Label>Notlar</Label>
              <Input value={agencyForm.notes} onChange={e => setAgencyForm(p => ({ ...p, notes: e.target.value }))} placeholder="Ek bilgiler..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAgencyForm(false)}>Iptal</Button>
            <Button onClick={handleSaveAgency} disabled={saving} data-testid="save-agency-btn">
              {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              {editingAgency ? 'Guncelle' : 'Olustur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* User Form Dialog */}
      <Dialog open={showUserForm} onOpenChange={setShowUserForm}>
        <DialogContent className="max-w-md" data-testid="user-form-dialog">
          <DialogHeader>
            <DialogTitle>Acente Kullanicisi Ekle</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Ad Soyad *</Label>
              <Input value={userForm.name} onChange={e => setUserForm(p => ({ ...p, name: e.target.value }))} data-testid="user-name-input" />
            </div>
            <div>
              <Label>E-posta *</Label>
              <Input value={userForm.email} onChange={e => setUserForm(p => ({ ...p, email: e.target.value }))} data-testid="user-email-input" />
            </div>
            <div>
              <Label>Sifre *</Label>
              <Input type="password" value={userForm.password} onChange={e => setUserForm(p => ({ ...p, password: e.target.value }))} data-testid="user-password-input" />
            </div>
            <div>
              <Label>Rol</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={userForm.role}
                onChange={e => setUserForm(p => ({ ...p, role: e.target.value }))}
              >
                <option value="agency_agent">Acente Ajani</option>
                <option value="agency_admin">Acente Admin</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUserForm(false)}>Iptal</Button>
            <Button onClick={handleSaveUser} disabled={saving} data-testid="save-user-btn">
              {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Olustur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );

  return <Layout user={user} tenant={tenant} onLogout={onLogout}>{content}</Layout>;
};

export default AgencyManagement;
