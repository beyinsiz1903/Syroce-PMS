import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { IdCard } from 'lucide-react';

const ALLOWED_ROLES = ['front_desk', 'frontdesk', 'supervisor', 'admin', 'super_admin'];

export const ID_PHOTO_REASON_OPTIONS = [
  { value: 'police_check', label: 'Polis denetimi' },
  { value: 'checkin_verification', label: 'Check-in doğrulaması' },
  { value: 'complaint_review', label: 'Şikayet incelemesi' },
  { value: 'identity_mismatch', label: 'Kimlik bilgisi tutarsızlığı' },
  { value: 'other', label: 'Diğer (aşağıya yazın)' },
];

function readUserFromStorage() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null');
  } catch {
    return null;
  }
}

export function canUserViewIdPhoto(user) {
  if (!user) return false;
  const role = user?.role;
  const roles = Array.isArray(user?.roles) ? user.roles : [];
  const all = [role, ...roles].filter(Boolean);
  return all.some((r) => ALLOWED_ROLES.includes(String(r)));
}

const IdPhotoViewerButton = ({
  bookingId,
  guestName,
  user,
  onlineCheckinCompleted,
  idPhotoUploaded,
  size = 'sm',
  variant = 'outline',
  className = 'border-blue-300 text-blue-700 hover:bg-blue-50',
  label = 'Kimlik fotoğrafını görüntüle',
  loadingLabel = 'Yükleniyor…',
  hideWhenUnavailable = true,
  hideWhenNotPermitted = true,
  testId,
}) => {
  const effectiveUser = useMemo(() => user ?? readUserFromStorage(), [user]);
  const canView = useMemo(() => canUserViewIdPhoto(effectiveUser), [effectiveUser]);

  // KVKK reason prompt state — opens before any /id-photo request.
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reasonChoice, setReasonChoice] = useState(ID_PHOTO_REASON_OPTIONS[0].value);
  const [reasonNote, setReasonNote] = useState('');

  // Photo viewer state — shown after reason is submitted.
  const [open, setOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    return () => {
      if (photoUrl) {
        try { URL.revokeObjectURL(photoUrl); } catch (_) { /* noop */ }
      }
    };
  }, [photoUrl]);

  if (!bookingId) return null;
  if (hideWhenNotPermitted && !canView) return null;
  if (hideWhenUnavailable && (onlineCheckinCompleted === false || idPhotoUploaded === false)) {
    return null;
  }

  const closeModal = () => {
    if (photoUrl) {
      try { URL.revokeObjectURL(photoUrl); } catch (_) { /* noop */ }
    }
    setPhotoUrl(null);
    setMeta(null);
    setLoading(false);
    setOpen(false);
  };

  const closeReasonPrompt = () => {
    setReasonOpen(false);
    setReasonChoice(ID_PHOTO_REASON_OPTIONS[0].value);
    setReasonNote('');
  };

  const buildReasonText = () => {
    const selected = ID_PHOTO_REASON_OPTIONS.find((o) => o.value === reasonChoice);
    const note = (reasonNote || '').trim();
    if (reasonChoice === 'other') {
      return note;
    }
    if (!selected) return note;
    return note ? `${selected.label} — ${note}` : selected.label;
  };

  // Resepsiyonist butona basınca önce KVKK gerekçe modali açılır.
  // Gerekçe onaylanmadan /id-photo isteği atılmaz.
  const requestPhoto = () => {
    if (!canView) {
      toast.error('Kimlik fotoğrafını görüntüleme yetkiniz yok');
      return;
    }
    setReasonChoice(ID_PHOTO_REASON_OPTIONS[0].value);
    setReasonNote('');
    setReasonOpen(true);
  };

  const fetchPhoto = async (reasonText) => {
    setOpen(true);
    setLoading(true);
    setMeta({ guestName, reason: reasonText });
    try {
      const statusRes = await axios.get(`/checkin/online/${bookingId}`, {
        headers: { 'Cache-Control': 'no-store' },
      });
      const checkin = statusRes.data?.checkin;
      if (!checkin?.id) {
        toast.info('Bu rezervasyon için online check-in kaydı yok');
        closeModal();
        return;
      }
      if (!checkin.id_photo_uploaded || !checkin.id_photo?.photo_id) {
        toast.info('Bu misafir kimlik fotoğrafı yüklememiş');
        closeModal();
        return;
      }
      // Şifrelenmiş fotoğrafı blob olarak çek (cache devre dışı).
      // Gerekçe query string olarak gönderilir; backend boşsa 400 döner.
      const photoRes = await axios.get(
        `/checkin/online/${checkin.id}/id-photo`,
        {
          responseType: 'blob',
          params: { reason: reasonText },
          headers: { 'Cache-Control': 'no-store', Pragma: 'no-cache' },
        },
      );
      const url = URL.createObjectURL(photoRes.data);
      setPhotoUrl(url);
      setMeta({
        guestName,
        checkinId: checkin.id,
        contentType: checkin.id_photo?.content_type,
        sha256: checkin.id_photo?.sha256,
        reason: reasonText,
      });
    } catch (e) {
      const status = e?.response?.status;
      if (status === 400) {
        toast.error('Görüntüleme için gerekçe zorunludur');
      } else if (status === 403) {
        toast.error('Kimlik fotoğrafını görüntüleme yetkiniz yok');
      } else if (status === 404) {
        toast.info('Kimlik fotoğrafı bulunamadı');
      } else {
        toast.error('Kimlik fotoğrafı yüklenemedi');
      }
      closeModal();
    } finally {
      setLoading(false);
    }
  };

  const submitReasonAndOpen = () => {
    const reasonText = buildReasonText();
    if (!reasonText) {
      toast.error('Lütfen bir gerekçe seçin veya yazın');
      return;
    }
    if (reasonText.length > 500) {
      toast.error('Gerekçe metni 500 karakteri geçemez');
      return;
    }
    closeReasonPrompt();
    fetchPhoto(reasonText);
  };

  return (
    <>
      <Button
        size={size}
        variant={variant}
        className={className}
        onClick={requestPhoto}
        disabled={loading}
        data-testid={testId || `btn-view-id-photo-${bookingId}`}
      >
        <IdCard className="w-4 h-4 mr-2" />
        {loading ? loadingLabel : label}
      </Button>
      <Dialog open={reasonOpen} onOpenChange={(v) => { if (!v) closeReasonPrompt(); }}>
        <DialogContent className="max-w-md" data-testid="dialog-id-photo-reason">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <IdCard className="w-5 h-5 text-blue-600" />
              Görüntüleme Gerekçesi
            </DialogTitle>
            <DialogDescription>
              KVKK amaç sınırlandırması gereği kimlik fotoğrafını açma sebebinizi
              belirtmeniz gerekir. Bu gerekçe denetim kaydına yazılır.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <RadioGroup
              value={reasonChoice}
              onValueChange={setReasonChoice}
              data-testid="radio-id-photo-reason"
            >
              {ID_PHOTO_REASON_OPTIONS.map((opt) => (
                <div key={opt.value} className="flex items-center gap-2">
                  <RadioGroupItem
                    value={opt.value}
                    id={`reason-${opt.value}-${bookingId}`}
                    data-testid={`radio-id-photo-reason-${opt.value}`}
                  />
                  <Label
                    htmlFor={`reason-${opt.value}-${bookingId}`}
                    className="cursor-pointer"
                  >
                    {opt.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
            <div className="space-y-1">
              <Label
                htmlFor={`reason-note-${bookingId}`}
                className="text-xs text-gray-600"
              >
                {reasonChoice === 'other'
                  ? 'Gerekçe (zorunlu)'
                  : 'Ek not (opsiyonel)'}
              </Label>
              <Textarea
                id={`reason-note-${bookingId}`}
                value={reasonNote}
                onChange={(e) => setReasonNote(e.target.value)}
                placeholder="Örn: Polis ekibi kimlik teyidi istiyor"
                rows={2}
                maxLength={400}
                data-testid="input-id-photo-reason-note"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={closeReasonPrompt}
              data-testid="btn-id-photo-reason-cancel"
            >
              Vazgeç
            </Button>
            <Button
              onClick={submitReasonAndOpen}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="btn-id-photo-reason-confirm"
            >
              Görüntüle
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={open} onOpenChange={(v) => { if (!v) closeModal(); }}>
        <DialogContent className="max-w-2xl" data-testid="dialog-id-photo">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <IdCard className="w-5 h-5 text-blue-600" />
              Misafir Kimlik Fotoğrafı
              {meta?.guestName && (
                <span className="text-sm font-normal text-gray-500">
                  — {meta.guestName}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex items-center justify-center min-h-[200px] bg-gray-50 rounded">
            {loading ? (
              <div className="flex flex-col items-center gap-2 py-8">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
                <p className="text-sm text-gray-500">Şifreli fotoğraf çözülüyor…</p>
              </div>
            ) : photoUrl ? (
              <img
                src={photoUrl}
                alt="Misafir kimlik fotoğrafı"
                className="max-h-[70vh] max-w-full object-contain"
                data-testid="img-id-photo"
              />
            ) : (
              <p className="text-sm text-gray-500 py-8">Fotoğraf yüklenemedi.</p>
            )}
          </div>
          {photoUrl && (
            <div className="text-xs text-gray-500 space-y-1">
              {meta?.reason && (
                <p data-testid="text-id-photo-reason">
                  <strong>Gerekçe:</strong> {meta.reason}
                </p>
              )}
              <p>
                Bu görüntüleme denetim kaydına yazıldı. Fotoğraf önbelleğe alınmaz;
                pencereyi kapattığınızda bellekten silinir.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default IdPhotoViewerButton;
