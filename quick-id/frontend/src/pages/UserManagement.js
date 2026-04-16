import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { api } from '../lib/api';
import { useAuth } from '../lib/AuthContext';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import PasswordStrength from '../components/PasswordStrength';
import { Plus, Edit3, Trash2, Key, Shield, Loader2, Unlock } from 'lucide-react';

export default function UserManagement() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [form, setForm] = useState({ email: '', password: '', name: '', role: 'reception' });
  const [saving, setSaving] = useState(false);
  const [resetDialog, setResetDialog] = useState(null);
  const [newPassword, setNewPassword] = useState('');

  useEffect(() => { loadUsers(); }, []);

  const loadUsers = async () => {
    try {
      const data = await api.getUsers();
      setUsers(data.users || []);
    } catch (err) { toast.error('Kullanıcılar yüklenemedi'); }
    finally { setLoading(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editingUser) {
        await api.updateUser(editingUser.id, { name: form.name, role: form.role });
        toast.success('Kullanıcı güncellendi');
      } else {
        if (!form.email || !form.password || !form.name) { toast.error('Tüm alanları doldurun'); setSaving(false); return; }
        await api.createUser(form);
        toast.success('Kullanıcı oluşturuldu');
      }
      setDialogOpen(false);
      setEditingUser(null);
      setForm({ email: '', password: '', name: '', role: 'reception' });
      loadUsers();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Bu kullanıcıyı silmek istediğinize emin misiniz?')) return;
    try {
      await api.deleteUser(id);
      toast.success('Kullanıcı silindi');
      loadUsers();
    } catch (err) { toast.error(err.message); }
  };

  const handleResetPassword = async () => {
    if (!newPassword || newPassword.length < 8) { toast.error('En az 8 karakter girin'); return; }
    try {
      await api.resetUserPassword(resetDialog, newPassword);
      toast.success('Şifre sıfırlandı');
      setResetDialog(null);
      setNewPassword('');
    } catch (err) {
      if (err.errors) {
        toast.error(err.errors.join(', '));
      } else {
        toast.error(err.message);
      }
    }
  };

  const handleUnlockUser = async (userId) => {
    try {
      await api.unlockUser(userId);
      toast.success('Hesap kilidi açıldı');
    } catch (err) { toast.error(err.message); }
  };

  const openEdit = (u) => {
    setEditingUser(u);
    setForm({ email: u.email, password: '', name: u.name, role: u.role });
    setDialogOpen(true);
  };

  const openCreate = () => {
    setEditingUser(null);
    setForm({ email: '', password: '', name: '', role: 'reception' });
    setDialogOpen(true);
  };

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('tr-TR') : '—';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Kullanıcı Yönetimi</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{users.length} kullanıcı</p>
        </div>
        <Button onClick={openCreate} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white" data-testid="add-user-button">
          <Plus className="w-4 h-4 mr-2" /> Yeni Kullanıcı
        </Button>
      </div>

      <Card className="bg-white">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-[hsl(var(--secondary))]">
                <TableHead>Ad</TableHead>
                <TableHead>E-posta</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Durum</TableHead>
                <TableHead>Kayıt Tarihi</TableHead>
                <TableHead className="w-32">İşlem</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map(u => (
                <TableRow key={u.id} className="h-12">
                  <TableCell className="font-medium">{u.name}</TableCell>
                  <TableCell className="text-sm">{u.email}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={u.role === 'admin' ? 'bg-[var(--brand-sky-soft)] text-[var(--brand-sky)] border-[var(--brand-sky)]' : 'bg-[var(--brand-success-soft)] text-[var(--brand-success)] border-[#A7F3D0]'}>
                      <Shield className="w-3 h-3 mr-1" />
                      {u.role === 'admin' ? 'Admin' : 'Resepsiyon'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={u.is_active !== false ? 'status-checked-in' : 'status-pending'}>
                      {u.is_active !== false ? 'Aktif' : 'Pasif'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDate(u.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(u)}>
                        <Edit3 className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setResetDialog(u.id); setNewPassword(''); }}>
                        <Key className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-amber-600" onClick={() => handleUnlockUser(u.id)} title="Hesap kilidini aç">
                        <Unlock className="w-3.5 h-3.5" />
                      </Button>
                      {u.email !== currentUser?.email && (
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[var(--brand-danger)]" onClick={() => handleDelete(u.id)}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingUser ? 'Kullanıcı Düzenle' : 'Yeni Kullanıcı'}</DialogTitle>
            <DialogDescription>Kullanıcı bilgilerini girin</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {!editingUser && (
              <div className="space-y-1.5">
                <Label>E-posta</Label>
                <Input value={form.email} onChange={e => setForm(p => ({...p, email: e.target.value}))} placeholder="ornek@otel.com" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Ad Soyad</Label>
              <Input value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} placeholder="Ad Soyad" />
            </div>
            {!editingUser && (
              <div className="space-y-1.5">
                <Label>Şifre</Label>
                <Input type="password" value={form.password} onChange={e => setForm(p => ({...p, password: e.target.value}))} placeholder="••••••" />
                <PasswordStrength password={form.password} showRules={true} />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Rol</Label>
              <Select value={form.role} onValueChange={v => setForm(p => ({...p, role: v}))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="reception">Resepsiyon</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>İptal</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              {editingUser ? 'Güncelle' : 'Oluştur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={!!resetDialog} onOpenChange={() => setResetDialog(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Şifre Sıfırla</DialogTitle>
            <DialogDescription>Yeni şifre belirleyin</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>Yeni Şifre</Label>
            <Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Yeni şifre" />
            <PasswordStrength password={newPassword} showRules={true} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetDialog(null)}>İptal</Button>
            <Button onClick={handleResetPassword} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">Sıfırla</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
