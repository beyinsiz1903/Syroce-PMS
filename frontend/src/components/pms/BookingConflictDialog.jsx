import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, ExternalLink, User as UserIcon, Bed, Calendar } from 'lucide-react';

function formatDate(value) {
  if (!value) return '—';
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
    return d.toLocaleDateString('tr-TR', { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return String(value).slice(0, 10);
  }
}

/**
 * Surfaces a structured booking conflict (HTTP 409) to front-desk staff.
 *
 * Props:
 *   conflict: { message, conflictingBookingId, conflictType, conflictWindow }
 *   open: boolean
 *   onClose: () => void
 *   onPickAlternative?: (room) => void — optional; when provided, "Bu odaya
 *     ata" buttons appear next to suggested rooms. The parent decides what
 *     to do (e.g. patch the form's room_id and resubmit).
 */
export default function BookingConflictDialog({
  conflict,
  open,
  onClose,
  onPickAlternative,
}) {
  const navigate = useNavigate();
  const [blocker, setBlocker] = useState(null);
  const [blockerLoading, setBlockerLoading] = useState(false);
  const [alternatives, setAlternatives] = useState([]);
  const [altLoading, setAltLoading] = useState(false);

  // Load conflicting-booking detail + alternative rooms when dialog opens.
  useEffect(() => {
    if (!open || !conflict) {
      setBlocker(null);
      setAlternatives([]);
      return;
    }
    let cancelled = false;
    const id = conflict.conflictingBookingId;

    if (id) {
      setBlockerLoading(true);
      axios
        .get(`/pms/reservations/${id}/full-detail`)
        .then((res) => {
          if (cancelled) return;
          const data = res.data || {};
          setBlocker({
            id,
            guestName: data.guest?.name || data.booking?.guest_name || '—',
            roomNumber: data.room?.room_number || data.booking?.room_number || '—',
            checkIn: data.booking?.check_in,
            checkOut: data.booking?.check_out,
            status: data.booking?.status,
          });
        })
        .catch(() => {
          if (cancelled) return;
          // Permission/visibility may block this read; fall back to minimal info.
          setBlocker({
            id,
            guestName: null,
            roomNumber: conflict.conflictWindow?.room_id || '—',
            checkIn: conflict.conflictWindow?.check_in,
            checkOut: conflict.conflictWindow?.check_out,
          });
        })
        .finally(() => {
          if (!cancelled) setBlockerLoading(false);
        });

      // Alternative rooms for the same window (re-uses the existing
      // available-rooms endpoint scoped to the blocker booking).
      setAltLoading(true);
      axios
        .get(`/bookings/${id}/available-rooms`)
        .then((res) => {
          if (cancelled) return;
          setAlternatives(res.data?.available_rooms?.slice(0, 6) || []);
        })
        .catch(() => {
          if (!cancelled) setAlternatives([]);
        })
        .finally(() => {
          if (!cancelled) setAltLoading(false);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [open, conflict]);

  if (!conflict) return null;

  const handleViewOther = () => {
    if (!conflict.conflictingBookingId) return;
    onClose?.();
    navigate(`/app/pms?edit=${conflict.conflictingBookingId}#bookings`);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent className="max-w-lg" data-testid="booking-conflict-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-amber-700">
            <AlertTriangle className="w-5 h-5" />
            Oda bu tarihlerde dolu
          </DialogTitle>
          <DialogDescription>
            {conflict.message}
          </DialogDescription>
        </DialogHeader>

        <div className="border border-amber-200 bg-amber-50/60 rounded-md p-3 text-sm space-y-2">
          <div className="text-xs uppercase tracking-wide text-amber-700 font-medium">
            Çakışan rezervasyon
          </div>
          {blockerLoading ? (
            <div className="text-slate-500">Yükleniyor…</div>
          ) : (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <UserIcon className="w-4 h-4 text-slate-500" />
                <span className="font-medium text-slate-900" data-testid="conflict-blocker-guest">
                  {blocker?.guestName || 'Misafir bilgisi alınamadı'}
                </span>
                {blocker?.status && (
                  <Badge variant="outline" className="text-xs">{blocker.status}</Badge>
                )}
              </div>
              <div className="flex items-center gap-2 text-slate-700">
                <Bed className="w-4 h-4 text-slate-500" />
                <span data-testid="conflict-blocker-room">Oda {blocker?.roomNumber ?? '—'}</span>
              </div>
              <div className="flex items-center gap-2 text-slate-700">
                <Calendar className="w-4 h-4 text-slate-500" />
                <span data-testid="conflict-blocker-dates">
                  {formatDate(blocker?.checkIn || conflict.conflictWindow?.check_in)}
                  {' → '}
                  {formatDate(blocker?.checkOut || conflict.conflictWindow?.check_out)}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Alternative rooms for the same window */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wide text-slate-500 font-medium">
            Aynı tarihler için boş odalar
          </div>
          {altLoading ? (
            <div className="text-sm text-slate-500">Aranıyor…</div>
          ) : alternatives.length === 0 ? (
            <div className="text-sm text-slate-500" data-testid="conflict-alternatives-empty">
              Bu tarihler için uygun başka oda bulunamadı.
            </div>
          ) : (
            <ul className="divide-y border rounded-md" data-testid="conflict-alternatives-list">
              {alternatives.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center justify-between px-3 py-2 text-sm"
                  data-testid={`conflict-alt-${r.id}`}
                >
                  <div className="min-w-0">
                    <div className="font-medium text-slate-900 truncate">
                      Oda {r.room_number}
                      <span className="ml-2 text-xs text-slate-500">{r.room_type}</span>
                      {r.is_same_type && (
                        <Badge variant="secondary" className="ml-2 text-[10px]">aynı tip</Badge>
                      )}
                    </div>
                    {r.price_per_night > 0 && (
                      <div className="text-xs text-slate-500">{r.price_per_night} / gece</div>
                    )}
                  </div>
                  {onPickAlternative && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => onPickAlternative(r)}
                      data-testid={`conflict-alt-pick-${r.id}`}
                    >
                      Bu odayı seç
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Kapat
          </Button>
          {conflict.conflictingBookingId && (
            <Button
              type="button"
              onClick={handleViewOther}
              data-testid="conflict-view-other"
            >
              <ExternalLink className="w-4 h-4 mr-1" />
              Diğer rezervasyonu aç
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
