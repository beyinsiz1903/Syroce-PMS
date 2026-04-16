import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';

import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { StatusBadge, DocTypeBadge } from '../components/StatusBadges';
import AuditTrail from '../components/AuditTrail';
import { api } from '../lib/api';
import {
  ArrowLeft,
  Edit3,
  Save,
  X,
  LogIn,
  LogOut,
  Trash2,
  User,
  CreditCard,
  Calendar,
  MapPin,
  Globe,
  Loader2,
  FileText,
  Camera,
  DoorOpen,
} from 'lucide-react';

const DOC_TYPES = [
  { value: 'tc_kimlik', label: 'TC Kimlik' },
  { value: 'passport', label: 'Pasaport' },
  { value: 'drivers_license', label: 'Ehliyet' },
  { value: 'old_nufus_cuzdani', label: 'Eski Nüfus Cüzdanı' },
  { value: 'other', label: 'Diğer' },
];

export default function GuestDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [guest, setGuest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [photoCapturing, setPhotoCapturing] = useState(false);
  const [guestPhoto, setGuestPhoto] = useState(null);
  const [roomAssigning, setRoomAssigning] = useState(false);

  useEffect(() => {
    loadGuest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadGuest = async () => {
    try {
      const data = await api.getGuest(id);
      setGuest(data.guest);
      setEditData(data.guest);
    } catch (err) {
      toast.error('Misafir bulunamadı');
      navigate('/guests');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates = {};
      const editableFields = ['first_name', 'last_name', 'id_number', 'birth_date', 'gender', 'nationality', 'document_type', 'document_number', 'birth_place', 'expiry_date', 'issue_date', 'notes', 'mother_name', 'father_name', 'address'];
      editableFields.forEach(f => {
        if (editData[f] !== guest[f]) updates[f] = editData[f];
      });
      
      if (Object.keys(updates).length > 0) {
        const result = await api.updateGuest(id, updates);
        setGuest(result.guest);
        toast.success('Bilgiler güncellendi');
      }
      setEditing(false);
    } catch (err) {
      toast.error('Güncelleme hatası');
    } finally {
      setSaving(false);
    }
  };

  const handleCheckin = async () => {
    try {
      const result = await api.checkinGuest(id);
      setGuest(result.guest);
      toast.success('Check-in yapıldı!');
    } catch (err) {
      toast.error('Check-in hatası');
    }
  };

  const handleCheckout = async () => {
    try {
      const result = await api.checkoutGuest(id);
      setGuest(result.guest);
      toast.success('Check-out yapıldı!');
    } catch (err) {
      toast.error('Check-out hatası');
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Bu misafiri silmek istediğinize emin misiniz?')) return;
    try {
      await api.deleteGuest(id);
      toast.success('Misafir silindi');
      navigate('/guests');
    } catch (err) {
      toast.error('Silme hatası');
    }
  };

  const handlePhotoCapture = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoCapturing(true);
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const data = await api.uploadGuestPhoto(id, reader.result);
          if (data.success) {
            toast.success('Fotoğraf kaydedildi');
            setGuestPhoto(reader.result);
            loadGuest();
          } else {
            toast.error('Fotoğraf yüklenemedi');
          }
        } catch (err) {
          toast.error(err.message || 'Fotoğraf yükleme hatası');
        }
        setPhotoCapturing(false);
      };
      reader.readAsDataURL(file);
    } catch (err) {
      toast.error('Dosya okuma hatası');
      setPhotoCapturing(false);
    }
  };

  const handleAutoAssignRoom = async () => {
    setRoomAssigning(true);
    try {
      const data = await api.autoAssignRoom(id);
      if (data.success) {
        toast.success(`Oda ${data.room?.room_number} atandı!`);
        loadGuest();
      } else {
        toast.error(data.detail || 'Müsait oda bulunamadı');
      }
    } catch (err) {
      toast.error(err.message || 'Oda atama hatası');
    }
    setRoomAssigning(false);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return new Date(dateStr).toLocaleString('tr-TR', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
    } catch { return dateStr; }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!guest) return null;

  const InfoRow = ({ icon: Icon, label, value, field, type = 'text' }) => (
    <div className="flex items-start gap-3 py-2.5 border-b border-[hsl(var(--border))] last:border-0">
      <Icon className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
        {editing && field ? (
          type === 'select-doc' ? (
            <Select value={editData[field] || ''} onValueChange={v => setEditData(prev => ({ ...prev, [field]: v }))}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DOC_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : type === 'select-gender' ? (
            <Select value={editData[field] || ''} onValueChange={v => setEditData(prev => ({ ...prev, [field]: v }))}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="M">Erkek</SelectItem>
                <SelectItem value="F">Kadın</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <Input
              type={type}
              value={editData[field] || ''}
              onChange={e => setEditData(prev => ({ ...prev, [field]: e.target.value }))}
              className="h-8 text-sm"
            />
          )
        ) : (
          <p className="text-sm font-medium text-[var(--brand-ink)]">{value || '—'}</p>
        )}
      </div>
    </div>
  );

  const originalData = guest.original_extracted_data;

  return (
    <div className="space-y-4" data-testid="guest-detail-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/guests')}>
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {guest.first_name} {guest.last_name}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <StatusBadge status={guest.status} />
              <DocTypeBadge type={guest.document_type} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {!editing ? (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Edit3 className="w-4 h-4 mr-1" /> Düzenle
            </Button>
          ) : (
            <>
              <Button size="sm" onClick={handleSave} disabled={saving} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">
                {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
                Kaydet
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setEditing(false); setEditData(guest); }}>
                <X className="w-4 h-4 mr-1" /> İptal
              </Button>
            </>
          )}
          {guest.status !== 'checked_in' && (
            <Button size="sm" onClick={handleCheckin} className="bg-[var(--brand-success)] hover:bg-[#0D6B63] text-white" data-testid="guest-checkin-button">
              <LogIn className="w-4 h-4 mr-1" /> Check-in
            </Button>
          )}
          {guest.status === 'checked_in' && (
            <Button size="sm" variant="outline" onClick={handleCheckout} data-testid="guest-checkout-button">
              <LogOut className="w-4 h-4 mr-1" /> Check-out
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleDelete} className="text-[var(--brand-danger)] hover:bg-[var(--brand-danger-soft)]">
            <Trash2 className="w-4 h-4 mr-1" /> Sil
          </Button>
          <label className="cursor-pointer">
            <Button variant="outline" size="sm" asChild disabled={photoCapturing}>
              <span>
                {photoCapturing ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Camera className="w-4 h-4 mr-1" />}
                Fotoğraf
              </span>
            </Button>
            <input type="file" accept="image/*" capture="user" className="hidden" onChange={handlePhotoCapture} disabled={photoCapturing} />
          </label>
          {!guest.room_number && (
            <Button variant="outline" size="sm" onClick={handleAutoAssignRoom} disabled={roomAssigning}>
              {roomAssigning ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <DoorOpen className="w-4 h-4 mr-1" />}
              Oda Ata
            </Button>
          )}
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left Column */}
        <div className="space-y-4">
          {/* Profile Card */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <User className="w-4 h-4 text-[var(--brand-sky)]" />
                Kişisel Bilgiler
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-0">
              <InfoRow icon={User} label="Ad" value={guest.first_name} field="first_name" />
              <InfoRow icon={User} label="Soyad" value={guest.last_name} field="last_name" />
              <InfoRow icon={CreditCard} label="Kimlik No" value={guest.id_number} field="id_number" />
              <InfoRow icon={Calendar} label="Doğum Tarihi" value={guest.birth_date} field="birth_date" type="date" />
              <InfoRow icon={User} label="Cinsiyet" value={guest.gender === 'M' ? 'Erkek' : guest.gender === 'F' ? 'Kadın' : guest.gender} field="gender" type="select-gender" />
              <InfoRow icon={Globe} label="Uyruk" value={guest.nationality} field="nationality" />
              <InfoRow icon={MapPin} label="Doğum Yeri" value={guest.birth_place} field="birth_place" />
              {guest.room_number && (
                <InfoRow icon={DoorOpen} label="Oda No" value={guest.room_number} />
              )}
              {(guest.has_photo || guestPhoto) && (
                <div className="flex items-center gap-3 py-2.5 border-b border-[hsl(var(--border))]">
                  <Camera className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs text-muted-foreground mb-0.5">Fotoğraf</p>
                    <Badge variant="outline" className="text-green-600 border-green-200 bg-green-50">Çekildi</Badge>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Document Card */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[var(--brand-sky)]" />
                Belge Bilgileri
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-0">
              <InfoRow icon={CreditCard} label="Belge Türü" value={DOC_TYPES.find(d => d.value === guest.document_type)?.label || guest.document_type} field="document_type" type="select-doc" />
              <InfoRow icon={CreditCard} label="Belge No" value={guest.document_number} field="document_number" />
              <InfoRow icon={Calendar} label="Veriliş Tarihi" value={guest.issue_date} field="issue_date" type="date" />
              <InfoRow icon={Calendar} label="Geçerlilik Tarihi" value={guest.expiry_date} field="expiry_date" type="date" />
            </CardContent>
          </Card>

          {/* Original AI Extraction Data */}
          {originalData && (
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[var(--brand-amber)]" />
                    AI Çıkarım Verileri
                  </CardTitle>
                  <Button variant="ghost" size="sm" onClick={() => setShowOriginal(!showOriginal)} className="text-xs">
                    {showOriginal ? 'Gizle' : 'Göster'}
                  </Button>
                </div>
              </CardHeader>
              {showOriginal && (
                <CardContent>
                  <div className="space-y-1.5 text-xs">
                    {Object.entries(originalData).filter(([k]) => !['is_valid', 'notes', 'document_number'].includes(k) && originalData[k]).map(([key, value]) => {
                      const currentValue = guest[key];
                      const isDifferent = currentValue && value && currentValue !== value;
                      return (
                        <div key={key} className="flex items-center gap-2">
                          <span className="text-muted-foreground min-w-[100px] capitalize">
                            {key.replace(/_/g, ' ')}:
                          </span>
                          <span className={isDifferent ? 'line-through text-[var(--brand-danger)]' : 'text-[var(--brand-ink)]'}>
                            {value}
                          </span>
                          {isDifferent && (
                            <span className="text-[var(--brand-success)] font-medium">
                              → {currentValue}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              )}
            </Card>
          )}
        </div>

        {/* Right Column */}
        <div className="space-y-4">
          {/* Timeline */}
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Zaman Çizelgesi</CardTitle>
            </CardHeader>
            <CardContent data-testid="guest-scan-timeline">
              <div className="space-y-3">
                {guest.check_out_at && (
                  <div className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full bg-[var(--brand-info)] mt-1.5" />
                    <div>
                      <p className="text-sm font-medium">Check-out</p>
                      <p className="text-xs text-muted-foreground">{formatDate(guest.check_out_at)}</p>
                    </div>
                  </div>
                )}
                {guest.check_in_at && (
                  <div className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full bg-[var(--brand-success)] mt-1.5" />
                    <div>
                      <p className="text-sm font-medium">Check-in</p>
                      <p className="text-xs text-muted-foreground">{formatDate(guest.check_in_at)}</p>
                    </div>
                  </div>
                )}
                {guest.updated_at && guest.updated_at !== guest.created_at && (
                  <div className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full bg-[var(--brand-warning)] mt-1.5" />
                    <div>
                      <p className="text-sm font-medium">Güncellendi</p>
                      <p className="text-xs text-muted-foreground">{formatDate(guest.updated_at)}</p>
                    </div>
                  </div>
                )}
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-[var(--brand-sky)] mt-1.5" />
                  <div>
                    <p className="text-sm font-medium">Kayıt Oluşturuldu</p>
                    <p className="text-xs text-muted-foreground">{formatDate(guest.created_at)}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Notes */}
          {(guest.notes || editing) && (
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Notlar</CardTitle>
              </CardHeader>
              <CardContent>
                {editing ? (
                  <Textarea
                    value={editData.notes || ''}
                    onChange={e => setEditData(prev => ({ ...prev, notes: e.target.value }))}
                    rows={3}
                    placeholder="Not ekleyin..."
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">{guest.notes || 'Not yok'}</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Audit Trail */}
          <AuditTrail guestId={id} />
        </div>
      </div>
    </div>
  );
}
